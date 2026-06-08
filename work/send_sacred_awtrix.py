#!/usr/bin/env python3
import argparse
import http.client
import json
import socket
import struct
import time
import urllib.parse

from PIL import Image, ImageEnhance


IMAGE_PATH = "/Users/duv/Desktop/sacred square.png"
APP_NAME = "sacred_square"
WIDTH = 32
HEIGHT = 8
STRIP_WIDTH = 128
STRIP_HEIGHT = 32


def encode_remaining_length(length):
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


def mqtt_string(value):
    data = value.encode("utf-8")
    return struct.pack("!H", len(data)) + data


class MqttClient:
    def __init__(self, host, port, client_id="codex-awtrix"):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.sock = None

    def __enter__(self):
        variable = mqtt_string(self.client_id)
        packet = (
            b"\x10"
            + encode_remaining_length(10 + len(variable))
            + mqtt_string("MQTT")
            + b"\x04\x02\x00\x3c"
            + variable
        )
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        self.sock.sendall(packet)
        response = self.sock.recv(4)
        if len(response) < 4 or response[0] != 0x20 or response[3] != 0:
            raise RuntimeError(f"MQTT CONNACK failed: {response!r}")
        return self

    def publish(self, topic, payload):
        payload = payload.encode("utf-8")
        publish_var = mqtt_string(topic)
        packet = b"\x30" + encode_remaining_length(len(publish_var) + len(payload)) + publish_var + payload
        self.sock.sendall(packet)

    def __exit__(self, exc_type, exc, tb):
        if self.sock:
            try:
                self.sock.sendall(b"\xe0\x00")
            finally:
                self.sock.close()


class AwtrixHttpClient:
    def __init__(self, host):
        self.host = host
        self.conn = http.client.HTTPConnection(host, timeout=5)

    def post(self, path, payload):
        data = payload.encode("utf-8")
        self.conn.request(
            "POST",
            path,
            body=data,
            headers={"Content-Type": "application/json", "Connection": "keep-alive"},
        )
        response = self.conn.getresponse()
        response.read()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def image_pixels(image):
    data = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    return [(r << 16) | (g << 8) | b for r, g, b in data]


def prepare_strip(direction):
    src = Image.open(IMAGE_PATH).convert("RGB")
    src = ImageEnhance.Color(src).enhance(1.35)
    src = ImageEnhance.Contrast(src).enhance(1.18)
    size = (WIDTH, STRIP_HEIGHT) if direction == "vertical" else (STRIP_WIDTH, HEIGHT)
    strip = src.resize(size, Image.Resampling.LANCZOS)
    preview = Image.new("RGB", size, "black")
    preview.paste(strip, (0, 0))
    return strip, preview


def frame_payload(frame, duration=8, draw_y=0):
    return json.dumps(
        {
            "draw": [{"db": [0, draw_y, frame.width, frame.height, image_pixels(frame)]}],
            "duration": duration,
            "lifetime": duration + 2,
            "noScroll": True,
        },
        separators=(",", ":"),
    )


def saved_app_payload(frame, duration, draw_y=0):
    return json.dumps(
        {
            "draw": [{"db": [0, draw_y, frame.width, frame.height, image_pixels(frame)]}],
            "duration": duration,
            "lifetime": 0,
            "noScroll": True,
            "save": True,
        },
        separators=(",", ":"),
    )


def frame_positions(strip, seconds, fps, direction):
    requested_steps = max(1, int(seconds * fps))
    max_x = strip.width - WIDTH
    max_y = strip.height - HEIGHT
    max_position = max_y if direction == "vertical" else max_x
    steps = min(requested_steps, max_position + 1)
    for i in range(steps):
        position = round(i / max(1, steps - 1) * max_position)
        yield position


def make_frames(strip, seconds, fps, direction):
    for position in frame_positions(strip, seconds, fps, direction):
        x = 0 if direction == "vertical" else position
        y = position if direction == "vertical" else 0
        yield strip.crop((x, y, x + WIDTH, y + HEIGHT))


def make_saved_slices(strip, direction, count, slice_height=HEIGHT):
    for i in range(count):
        if direction == "vertical":
            y = round(i * max(0, strip.height - slice_height) / max(1, count - 1))
            yield strip.crop((0, y, WIDTH, y + slice_height))
        else:
            x = round(i * max(0, strip.width - WIDTH) / max(1, count - 1))
            yield strip.crop((x, 0, x + WIDTH, slice_height))


def make_paired_bar_frames(strip, direction, count, slice_height):
    bars = list(make_saved_slices(strip, direction, count + 1, slice_height))
    for index in range(count):
        frame = Image.new("RGB", (WIDTH, slice_height * 2), "black")
        frame.paste(bars[index], (0, 0))
        frame.paste(bars[index + 1], (0, slice_height))
        yield frame


def run_saved_series(method, display, broker, port, prefix, app_prefix, count, seconds):
    per_app = seconds / count
    if method == "mqtt":
        with MqttClient(broker, port, "codex-awtrix-run-series") as mqtt:
            for index in range(1, count + 1):
                mqtt.publish(f"{prefix}/switch", json.dumps({"name": f"{app_prefix}_{index}"}))
                time.sleep(per_app)
            mqtt.publish(f"{prefix}/nextapp", "")
        return

    with AwtrixHttpClient(display) as http:
        for index in range(1, count + 1):
            http.post("/api/switch", json.dumps({"name": f"{app_prefix}_{index}"}))
            time.sleep(per_app)
        http.post("/api/nextapp", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["mqtt", "http"], default="mqtt")
    parser.add_argument("--mode", choices=["stream", "upload-series", "run-series"], default="stream")
    parser.add_argument("--broker", default="192.168.8.139")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--prefix", default="awtrix")
    parser.add_argument("--display", default="192.168.8.99")
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--fps", type=float, default=5)
    parser.add_argument("--direction", choices=["horizontal", "vertical"], default="horizontal")
    parser.add_argument("--series-count", type=int, default=4)
    parser.add_argument("--app-prefix", default=APP_NAME)
    parser.add_argument("--slice-height", type=int, default=HEIGHT)
    parser.add_argument("--draw-y", type=int, default=0)
    parser.add_argument("--pair-bars", action="store_true")
    parser.add_argument("--preview", default="outputs/sacred_awtrix_strip.png")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.mode == "run-series":
        run_saved_series(
            args.method,
            args.display,
            args.broker,
            args.port,
            args.prefix,
            args.app_prefix,
            args.series_count,
            args.seconds,
        )
        if not args.quiet:
            print(f"ran {args.series_count} saved apps in {args.seconds:.2f}s")
        return

    strip, preview = prepare_strip(args.direction)
    preview.resize((preview.width * 8, preview.height * 8), Image.Resampling.NEAREST).save(args.preview)
    slice_duration = max(1, round(args.seconds / args.series_count))

    if args.mode == "upload-series":
        frames = (
            list(make_paired_bar_frames(strip, args.direction, args.series_count, args.slice_height))
            if args.pair_bars
            else list(make_saved_slices(strip, args.direction, args.series_count, args.slice_height))
        )
        if args.method == "mqtt":
            with MqttClient(args.broker, args.port, "codex-awtrix-upload") as mqtt:
                mqtt.publish(f"{args.prefix}/custom/{args.app_prefix}_", "")
                time.sleep(0.5)
                for index, frame in enumerate(frames, start=1):
                    app_name = f"{args.app_prefix}_{index}"
                    payload = saved_app_payload(frame, slice_duration, args.draw_y)
                    mqtt.publish(f"{args.prefix}/custom/{app_name}", payload)
                    if not args.quiet:
                        print(f"uploaded {app_name}")
        else:
            with AwtrixHttpClient(args.display) as http:
                clear_path = f"/api/custom?name={urllib.parse.quote(args.app_prefix + '_')}"
                http.post(clear_path, "")
                time.sleep(0.5)
                for index, frame in enumerate(frames, start=1):
                    app_name = f"{args.app_prefix}_{index}"
                    payload = saved_app_payload(frame, slice_duration, args.draw_y)
                    custom_path = f"/api/custom?name={urllib.parse.quote(app_name)}"
                    http.post(custom_path, payload)
                    if not args.quiet:
                        print(f"uploaded {app_name}")
        return

    if args.method == "mqtt":
        custom_topic = f"{args.prefix}/custom/{APP_NAME}"
        switch_topic = f"{args.prefix}/switch"
        next_topic = f"{args.prefix}/nextapp"
        frames = [frame_payload(frame) for frame in make_frames(strip, args.seconds, args.fps, args.direction)]
        with MqttClient(args.broker, args.port, "codex-awtrix-stream") as mqtt:
            sent_at = time.monotonic()
            mqtt.publish(custom_topic, frames[0])
            mqtt.publish(switch_topic, json.dumps({"name": APP_NAME}))
            start = time.monotonic()
            frame_interval = args.seconds / len(frames)
            for n, payload in enumerate(frames):
                mqtt.publish(custom_topic, payload)
                target = start + (n + 1) * frame_interval
                time.sleep(max(0, target - time.monotonic()))
            mqtt.publish(next_topic, "")
            if not args.quiet:
                print(f"streamed {len(frames)} unique frames in {time.monotonic() - sent_at:.2f}s")
        return

    frames = [frame_payload(frame) for frame in make_frames(strip, args.seconds, args.fps, args.direction)]
    custom_path = f"/api/custom?name={urllib.parse.quote(APP_NAME)}"
    switch_path = "/api/switch"
    next_path = "/api/nextapp"
    with AwtrixHttpClient(args.display) as http:
        sent_at = time.monotonic()
        http.post(custom_path, frames[0])
        http.post(switch_path, json.dumps({"name": APP_NAME}))
        start = time.monotonic()
        frame_interval = args.seconds / len(frames)
        for n, payload in enumerate(frames):
            http.post(custom_path, payload)
            target = start + (n + 1) * frame_interval
            time.sleep(max(0, target - time.monotonic()))
        http.post(next_path, "")
        if not args.quiet:
            print(f"streamed {len(frames)} unique frames in {time.monotonic() - sent_at:.2f}s")


if __name__ == "__main__":
    main()
