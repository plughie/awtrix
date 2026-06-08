#!/usr/bin/env python3
import argparse
import http.client
import json
import socket
import time


WIDTH = 32
HEIGHT = 8
PIXELS = [0] * (WIDTH * HEIGHT)


class AwtrixHttpClient:
    def __init__(self, host):
        self.conn = http.client.HTTPConnection(host, timeout=5)

    def request(self, method, path, payload=None):
        body = None if payload is None else payload.encode("utf-8")
        headers = {"Connection": "keep-alive"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        self.conn.request(method, path, body=body, headers=headers)
        response = self.conn.getresponse()
        data = response.read().decode("utf-8", "replace")
        if response.status >= 400:
            raise RuntimeError(f"{method} {path} returned {response.status}: {data}")
        return data

    def get_json(self, path):
        return json.loads(self.request("GET", path))

    def post(self, path, payload):
        return self.request("POST", path, payload)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def app_payload(duration):
    return json.dumps(
        {
            "draw": [{"db": [0, 0, WIDTH, HEIGHT, PIXELS]}],
            "duration": duration,
            "lifetime": 0,
            "noScroll": True,
            "save": True,
        },
        separators=(",", ":"),
    )


def sized_app_payload(duration, lit_pixels):
    pixels = [0x101010] * min(lit_pixels, WIDTH * HEIGHT)
    pixels.extend([0] * (WIDTH * HEIGHT - len(pixels)))
    return json.dumps(
        {
            "draw": [{"db": [0, 0, WIDTH, HEIGHT, pixels]}],
            "duration": duration,
            "lifetime": 0,
            "noScroll": True,
            "save": True,
        },
        separators=(",", ":"),
    )


def probe_names(loop, prefix):
    return sorted(name for name in loop if name.startswith(prefix))


def delete_probe_apps(http, prefix, max_attempts):
    http.post(f"/api/custom?name={prefix}", "")
    for index in range(1, max_attempts + 1):
        http.post(f"/api/custom?name={prefix}{index:03d}", "")


def main():
    parser = argparse.ArgumentParser(description="Empirically find the saved custom-app limit on an AWTRIX.")
    parser.add_argument("--display", default="192.168.8.99")
    parser.add_argument("--prefix", default="limit_probe_")
    parser.add_argument("--max-attempts", type=int, default=45)
    parser.add_argument("--duration", type=int, default=1)
    parser.add_argument("--lit-pixels", type=int, default=0)
    parser.add_argument("--known-crash-at", type=int, default=51)
    parser.add_argument("--guard-band", type=int, default=5)
    parser.add_argument("--cleanup-max", type=int, default=128)
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()

    guarded_max = max(0, args.known_crash_at - args.guard_band)
    if args.max_attempts > guarded_max:
        raise SystemExit(
            f"refusing to probe {args.max_attempts} apps: known crash at {args.known_crash_at}, "
            f"guarded maximum is {guarded_max}. Override with a smaller --known-crash-at/--guard-band only if intended."
        )

    payload = sized_app_payload(args.duration, args.lit_pixels)
    payload_bytes = len(payload.encode("utf-8"))
    with AwtrixHttpClient(args.display) as http:
        try:
            initial_loop = http.get_json("/api/loop")
            initial_stats = http.get_json("/api/stats")
        except (PermissionError, OSError, socket.timeout) as exc:
            raise SystemExit(f"could not reach AWTRIX at {args.display}: {exc}") from exc
        initial_non_probe = [name for name in initial_loop if not name.startswith(args.prefix)]
        print(f"initial apps: {len(initial_loop)} total, {len(initial_non_probe)} non-probe")
        print(f"initial free RAM: {initial_stats.get('ram', 'unknown')}")
        print(f"probe payload size: {payload_bytes} bytes")

        delete_probe_apps(http, args.prefix, args.cleanup_max)
        time.sleep(1)

        if args.cleanup_only:
            cleaned_loop = http.get_json("/api/loop")
            remaining = probe_names(cleaned_loop, args.prefix)
            print(f"cleanup remaining probe apps: {len(remaining)}")
            return

        accepted = []
        last_count = 0
        first_stall = None
        for index in range(1, args.max_attempts + 1):
            name = f"{args.prefix}{index:03d}"
            http.post(f"/api/custom?name={name}", payload)
            loop = http.get_json("/api/loop")
            stats = http.get_json("/api/stats")
            probes = probe_names(loop, args.prefix)
            if name in probes and len(probes) > last_count:
                accepted = probes
                last_count = len(probes)
                print(
                    f"accepted {name}: {last_count} probe apps, {len(loop)} total apps, "
                    f"free RAM {stats.get('ram', 'unknown')}, approx probe bytes {last_count * payload_bytes}"
                )
                continue

            first_stall = index
            print(
                f"stalled at {name}: {len(probes)} probe apps, {len(loop)} total apps, "
                f"free RAM {stats.get('ram', 'unknown')}, approx probe bytes {len(probes) * payload_bytes}"
            )
            break

        final_loop = http.get_json("/api/loop")
        final_probes = probe_names(final_loop, args.prefix)
        print(f"result probe apps accepted: {len(final_probes)}")
        print(f"result total apps listed: {len(final_loop)}")
        print(f"first failed/stalled attempt: {first_stall or 'none within max-attempts'}")

        if not args.no_cleanup:
            delete_probe_apps(http, args.prefix, args.cleanup_max)
            time.sleep(1)
            cleaned_loop = http.get_json("/api/loop")
            remaining = probe_names(cleaned_loop, args.prefix)
            print(f"cleanup remaining probe apps: {len(remaining)}")
        print(f"effective saved-app capacity including existing apps: {len(final_loop)}")


if __name__ == "__main__":
    main()
