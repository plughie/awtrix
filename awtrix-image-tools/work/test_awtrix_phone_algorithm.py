#!/usr/bin/env python3
import argparse
import http.client
import json
import math
import time
import urllib.parse


WIDTH = 32
FRAME_HEIGHT = 8
BAR_SIZE = 4


class Awtrix:
    def __init__(self, host):
        self.host = host

    def request(self, method, path, payload=None):
        body = None if payload is None else payload.encode("utf-8")
        headers = {"Connection": "close"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection(self.host, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read().decode("utf-8", "replace")
            if response.status >= 400:
                raise RuntimeError(f"{method} {path} returned {response.status}: {data}")
            return data
        finally:
            conn.close()

    def get_json(self, path):
        return json.loads(self.request("GET", path))

    def post(self, path, payload):
        return self.request("POST", path, payload)


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


def phone_pixels(height):
    pixels = []
    for row in range(height):
        for column in range(WIDTH):
            red = min(255, row * 255 // max(1, height - 1))
            green = min(255, column * 255 // (WIDTH - 1))
            blue = 64
            pixels.append((red << 16) | (green << 8) | blue)
    return pixels


def rows(pixels, y, height):
    out = []
    for row in range(y, y + height):
        if row < 0 or row >= len(pixels) // WIDTH:
            out.extend([0] * WIDTH)
            continue
        start = row * WIDTH
        out.extend(pixels[start : start + WIDTH])
    return out


def make_frames(height, direction):
    pixels = phone_pixels(height)
    if direction in {"left-to-right", "right-to-left"}:
        frame_count = max(1, math.ceil(WIDTH / BAR_SIZE))
        indices = range(frame_count) if direction == "left-to-right" else reversed(range(frame_count))
        return [columns(pixels, height, index * BAR_SIZE, WIDTH, FRAME_HEIGHT) for index in indices]

    frame_count = max(1, math.ceil(height / BAR_SIZE))
    indices = range(frame_count) if direction == "top-to-bottom" else reversed(range(frame_count))
    frames = []
    for index in indices:
        y = index * BAR_SIZE
        frames.append(rows(pixels, y, FRAME_HEIGHT))
    return frames


def columns(pixels, image_height, x, width, height):
    out = []
    for row in range(height):
        for column in range(x, x + width):
            if row >= image_height or column < 0 or column >= WIDTH:
                out.append(0)
            else:
                out.append(pixels[row * WIDTH + column])
    return out


def frame_payload(frame, duration):
    return json.dumps(
        {
            "draw": [{"db": [0, 0, WIDTH, FRAME_HEIGHT, frame]}],
            "duration": duration,
            "lifetime": duration + 2,
            "noScroll": True,
            "save": False,
        },
        separators=(",", ":"),
    )


def print_loop(label, loop, app_name):
    matches = [name for name in loop if name in cleanup_names(app_name)]
    print(f"{label}: total={len(loop)} cleanup_matches={matches}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--display", default="192.168.8.99")
    parser.add_argument("--name", default="image_to_awtrix")
    parser.add_argument("--height", type=int, default=56)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument(
        "--direction",
        choices=["top-to-bottom", "bottom-to-top", "left-to-right", "right-to-left"],
        default="top-to-bottom",
    )
    args = parser.parse_args()

    awtrix = Awtrix(args.display)
    frames = make_frames(args.height, args.direction)
    delay = args.seconds / len(frames)
    app_duration = max(1, math.ceil(args.seconds) + 1)

    for name in cleanup_names(args.name):
        awtrix.post(custom_path(name), "")
    time.sleep(0.5)
    print_loop("after_precleanup", awtrix.get_json("/api/loop"), args.name)

    awtrix.post(custom_path(args.name), frame_payload(frames[0], app_duration))
    awtrix.post("/api/switch", json.dumps({"name": args.name}, separators=(",", ":")))

    for frame in frames:
        awtrix.post(custom_path(args.name), frame_payload(frame, app_duration))
        time.sleep(delay)

    print_loop("after_run", awtrix.get_json("/api/loop"), args.name)
    awtrix.post("/api/nextapp", "")
    time.sleep(1)
    for name in cleanup_names(args.name):
        awtrix.post(custom_path(name), "")
    time.sleep(1)
    final_loop = awtrix.get_json("/api/loop")
    print_loop("after_cleanup", final_loop, args.name)
    if any(name in final_loop for name in cleanup_names(args.name)):
        raise SystemExit("cleanup failed")


if __name__ == "__main__":
    main()
