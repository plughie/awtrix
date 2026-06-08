#!/usr/bin/env python3
import argparse
import http.client
import json
import time
import urllib.parse


WIDTH = 32
FRAME_HEIGHT = 8


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


def frame_pixels(frame_index):
    pixels = []
    colors = [0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF]
    for row in range(FRAME_HEIGHT):
        for column in range(WIDTH):
            if column < (frame_index + 1) * 8:
                pixels.append(colors[frame_index % len(colors)])
            else:
                pixels.append(0)
    return pixels


def frame_payload(frame_index, duration):
    return json.dumps(
        {
            "draw": [{"db": [0, 0, WIDTH, FRAME_HEIGHT, frame_pixels(frame_index)]}],
            "duration": duration,
            "lifetime": duration + 2,
            "noScroll": True,
            "save": False,
        },
        separators=(",", ":"),
    )


def custom_path(name):
    return f"/api/custom?name={urllib.parse.quote(name, safe='')}"


def switch_payload(name):
    return json.dumps({"name": name}, separators=(",", ":"))


def print_presence(label, loop, name):
    matches = [key for key in loop if key.startswith(name)]
    print(f"{label}: present={name in loop}, prefix_matches={matches}, total={len(loop)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--display", default="192.168.8.99")
    parser.add_argument("--name", default="codex_one_shot_cleanup_test")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--seconds", type=float, default=8)
    args = parser.parse_args()

    awtrix = Awtrix(args.display)
    duration = max(1, round(args.seconds / args.frames))
    delay = args.seconds / args.frames

    initial = awtrix.get_json("/api/loop")
    print_presence("initial", initial, args.name)

    # Start clean in case a prior test/app left a JSON file behind.
    awtrix.post(custom_path(args.name), "")
    time.sleep(0.5)
    after_predelete = awtrix.get_json("/api/loop")
    print_presence("after_predelete", after_predelete, args.name)

    awtrix.post(custom_path(args.name), frame_payload(0, duration))
    created = awtrix.get_json("/api/loop")
    print_presence("after_create", created, args.name)

    awtrix.post("/api/switch", switch_payload(args.name))
    for index in range(args.frames):
        awtrix.post(custom_path(args.name), frame_payload(index, duration))
        time.sleep(delay)

    after_run = awtrix.get_json("/api/loop")
    print_presence("after_run_before_nextapp", after_run, args.name)

    awtrix.post("/api/nextapp", "")
    time.sleep(1.0)
    after_nextapp = awtrix.get_json("/api/loop")
    print_presence("after_nextapp", after_nextapp, args.name)

    awtrix.post(custom_path(args.name), "")
    time.sleep(1.0)
    after_delete = awtrix.get_json("/api/loop")
    print_presence("after_delete", after_delete, args.name)

    if args.name in after_delete:
        raise SystemExit("cleanup failed: app still present after delete")


if __name__ == "__main__":
    main()
