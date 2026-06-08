#!/usr/bin/env python3
import argparse
import http.client
import json
import math
import os
import select
import sys
import termios
import time
import tty
import urllib.parse
from pathlib import Path

from PIL import Image, ImageEnhance


APP_NAME = "image_to_awtrix"
WIDTH = 32
FRAME_HEIGHT = 8
BAR_SIZE = 4
SATURATION = 1.35
CONTRAST = 1.18


class KeyWatcher:
    def __init__(self, enabled=True):
        self.enabled = enabled and sys.stdin.isatty()
        self.original_settings = None
        self.stop_requested = False

    def __enter__(self):
        if self.enabled:
            self.original_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.enabled and self.original_settings is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_settings)

    def should_stop(self):
        if self.stop_requested:
            return True
        if not self.enabled:
            return False
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if readable:
            key = sys.stdin.read(1)
            self.stop_requested = key.lower() == "q"
        return self.stop_requested


class Awtrix:
    def __init__(self, host, timeout=10):
        self.host = normalize_host(host)
        self.timeout = timeout

    def request(self, method, path, payload=None):
        body = None if payload is None else payload.encode("utf-8")
        headers = {"Connection": "close"}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        conn = http.client.HTTPConnection(self.host, timeout=self.timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8", "replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"{method} {path} returned HTTP {response.status}: {data}")
            return data
        finally:
            conn.close()

    def get_json(self, path):
        return json.loads(self.request("GET", path))

    def post(self, path, payload=None):
        return self.request("POST", path, payload)


def normalize_host(value):
    host = os.path.expandvars(value.strip())
    if host.startswith("http://"):
        host = host[7:]
    elif host.startswith("https://"):
        host = host[8:]
    host = host.split("/", 1)[0]
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.strip()


def custom_path(name):
    return f"/api/custom?name={urllib.parse.quote(name, safe='')}"


def cleanup_names(app_name):
    names = [
        app_name,
        "image_to_awtrix_bar",
        "sacred_square",
        "sacred_square_bar",
    ]
    names.extend(f"image_to_awtrix_bar_{index}" for index in range(1, 9))
    names.extend(f"sacred_square_{index}" for index in range(1, 5))
    names.extend(f"sacred_square_bar_{index}" for index in range(1, 9))
    names.extend(f"_{index}" for index in range(1, 9))
    return sorted(set(names))


def get_stats_with_retry(awtrix, attempts=5):
    last_error = None
    for attempt in range(attempts):
        try:
            return awtrix.get_json("/api/stats")
        except Exception as error:
            last_error = error
            time.sleep(min(2.0, 0.35 * (attempt + 1)))
    raise RuntimeError(f"could not connect to AWTRIX at {awtrix.host}: {last_error}")


def loop_is_clean(awtrix, names):
    loop = awtrix.get_json("/api/loop")
    return not any(name in loop for name in names), loop


def cleanup_custom_apps(awtrix, app_name, quiet=False):
    names = cleanup_names(app_name)
    last_loop = None
    for _ in range(4):
        awtrix.post("/api/nextapp")
        time.sleep(0.8)
        for name in names:
            awtrix.post(custom_path(name))
        time.sleep(0.8)
        clean, last_loop = loop_is_clean(awtrix, names)
        if clean:
            if not quiet:
                print("cleanup complete")
            return
    raise RuntimeError(f"temporary AWTRIX app is still in rotation: {last_loop}")


def prepare_for_upload(awtrix, app_name, keep_in_rotation, connect_retries, quiet=False):
    stats = get_stats_with_retry(awtrix, attempts=connect_retries)
    if not quiet:
        print(f"connected to {stats.get('uid', awtrix.host)} at {stats.get('ip_address', awtrix.host)}")
    if not keep_in_rotation:
        cleanup_custom_apps(awtrix, app_name, quiet=quiet)
    get_stats_with_retry(awtrix, attempts=connect_retries)


def source_crop(image, center_square):
    if not center_square:
        return image

    side = min(image.width, image.height)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def image_to_pixels(path, center_square=False):
    image = Image.open(path).convert("RGB")
    cropped = source_crop(image, center_square)
    cropped = ImageEnhance.Color(cropped).enhance(SATURATION)
    cropped = ImageEnhance.Contrast(cropped).enhance(CONTRAST)
    scaled_height = max(FRAME_HEIGHT, round(cropped.height / cropped.width * WIDTH))
    scaled = cropped.resize((WIDTH, scaled_height), Image.Resampling.LANCZOS)
    data = scaled.get_flattened_data() if hasattr(scaled, "get_flattened_data") else scaled.getdata()
    pixels = [(r << 16) | (g << 8) | b for r, g, b in data]
    return pixels, scaled_height


def rows(pixels, image_height, y, height):
    values = []
    for row in range(y, y + height):
        if row < 0 or row >= image_height:
            values.extend([0] * WIDTH)
            continue
        start = row * WIDTH
        values.extend(pixels[start : start + WIDTH])
    return values


def columns(pixels, image_height, x, width, height):
    values = []
    for row in range(height):
        for column in range(x, x + width):
            if row < 0 or row >= image_height or column < 0 or column >= WIDTH:
                values.append(0)
            else:
                values.append(pixels[row * WIDTH + column])
    return values


def make_frames(pixels, image_height, direction):
    if direction in {"left-to-right", "right-to-left"}:
        frame_count = max(1, math.ceil(WIDTH / BAR_SIZE))
        indices = range(frame_count) if direction == "left-to-right" else reversed(range(frame_count))
        return [columns(pixels, image_height, index * BAR_SIZE, WIDTH, FRAME_HEIGHT) for index in indices]

    frame_count = max(1, math.ceil(image_height / BAR_SIZE))
    indices = range(frame_count) if direction == "top-to-bottom" else reversed(range(frame_count))
    return [rows(pixels, image_height, index * BAR_SIZE, FRAME_HEIGHT) for index in indices]


def frame_payload(frame, duration, lifetime, save):
    return json.dumps(
        {
            "draw": [{"db": [0, 0, WIDTH, FRAME_HEIGHT, frame]}],
            "duration": duration,
            "lifetime": lifetime,
            "noScroll": True,
            "save": save,
        },
        separators=(",", ":"),
    )


def sleep_until(target, key_watcher):
    while True:
        if key_watcher.should_stop():
            return False
        remaining = target - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(0.1, remaining))


def send_frames(awtrix, app_name, frames, seconds, direction, loop, keep_in_rotation, quiet=False):
    delay = seconds / len(frames)
    app_duration = 86400 if loop else max(1, math.ceil(seconds) + 1)
    app_lifetime = 0 if keep_in_rotation else app_duration + 2

    def payload(frame):
        return frame_payload(frame, app_duration, app_lifetime, keep_in_rotation)

    awtrix.post(custom_path(app_name), payload(frames[0]))
    awtrix.post("/api/switch", json.dumps({"name": app_name}, separators=(",", ":")))

    cycles = 0
    try:
        with KeyWatcher(enabled=loop) as key_watcher:
            if loop and not quiet and key_watcher.enabled:
                print("press q to stop and clean up")
            while True:
                cycles += 1
                start = time.monotonic()
                for index, frame in enumerate(frames):
                    if key_watcher.should_stop():
                        break
                    awtrix.post(custom_path(app_name), payload(frame))
                    target = start + (index + 1) * delay
                    if not sleep_until(target, key_watcher):
                        break
                if key_watcher.should_stop():
                    if not quiet:
                        print("\nstop requested")
                    break
                if not quiet:
                    print(f"cycle {cycles} complete ({direction}, {len(frames)} frames)")
                if not loop:
                    break
    except KeyboardInterrupt:
        if not quiet:
            print("\nstop requested")
    finally:
        if keep_in_rotation:
            awtrix.post("/api/nextapp")
            if not quiet:
                print(f"left {app_name} in AWTRIX rotation")
        else:
            cleanup_custom_apps(awtrix, app_name, quiet=quiet)


def save_preview(pixels, height, path):
    image = Image.new("RGB", (WIDTH, height))
    image.putdata([((value >> 16) & 255, (value >> 8) & 255, value & 255) for value in pixels])
    image.resize((WIDTH * 8, height * 8), Image.Resampling.NEAREST).save(path)


def main():
    parser = argparse.ArgumentParser(description="Send a cropped/scaled image to AWTRIX like the phone app.")
    parser.add_argument("image", nargs="?", help="source image path")
    parser.add_argument("--display", help="AWTRIX IP address or hostname; defaults to $AWTRIX_IP")
    parser.add_argument("--name", default=APP_NAME, help="temporary AWTRIX app name")
    parser.add_argument("--seconds", type=float, default=8, help="seconds per animation cycle")
    parser.add_argument(
        "--direction",
        choices=["top-to-bottom", "bottom-to-top", "left-to-right", "right-to-left"],
        default="top-to-bottom",
        help="animation direction",
    )
    parser.add_argument("--center-square", action="store_true", help="crop the center square before scaling")
    parser.add_argument("--loop", action="store_true", help="loop until q or Ctrl-C")
    parser.add_argument("--keep-in-rotation", action="store_true", help="save and leave the app in AWTRIX rotation")
    parser.add_argument("--clean", action="store_true", help="clear generated AWTRIX image apps and exit")
    parser.add_argument("--preview", help="write a nearest-neighbor preview PNG")
    parser.add_argument("--no-send", action="store_true", help="convert and print frame info without contacting AWTRIX")
    parser.add_argument("--connect-retries", type=int, default=5, help="AWTRIX connection attempts before failing")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.image is None and not args.clean:
        parser.print_help()
        raise SystemExit(2)

    display = args.display or os.environ.get("AWTRIX_IP")
    if not display:
        raise SystemExit("AWTRIX display not set. Use --display HOST or set AWTRIX_IP.")

    awtrix = Awtrix(display)
    if args.clean:
        try:
            stats = get_stats_with_retry(awtrix, attempts=args.connect_retries)
            if not args.quiet:
                print(f"connected to {stats.get('uid', awtrix.host)} at {stats.get('ip_address', awtrix.host)}")
            cleanup_custom_apps(awtrix, args.name, quiet=args.quiet)
            if not args.quiet:
                print(f"loop after cleanup: {awtrix.get_json('/api/loop')}")
            return
        except Exception as error:
            raise SystemExit(str(error))

    image_path = Path(args.image).expanduser()
    if not image_path.exists():
        raise SystemExit(f"image not found: {image_path}")
    if args.seconds <= 0:
        raise SystemExit("--seconds must be greater than 0")

    pixels, height = image_to_pixels(image_path, center_square=args.center_square)
    frames = make_frames(pixels, height, args.direction)

    if args.preview:
        save_preview(pixels, height, args.preview)

    if not args.quiet:
        crop_mode = "center square" if args.center_square else "full rectangle"
        print(f"converted {image_path} using {crop_mode}: 32x{height}, {len(frames)} frames")

    if args.no_send:
        return

    try:
        prepare_for_upload(awtrix, args.name, args.keep_in_rotation, args.connect_retries, quiet=args.quiet)
        send_frames(
            awtrix,
            args.name,
            frames,
            args.seconds,
            args.direction,
            args.loop,
            args.keep_in_rotation,
            quiet=args.quiet,
        )
    except Exception as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
