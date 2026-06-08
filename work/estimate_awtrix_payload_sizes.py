#!/usr/bin/env python3
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_sender():
    spec = importlib.util.spec_from_file_location("sender", ROOT / "send_sacred_awtrix.py")
    sender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sender)
    return sender


def describe(name, payloads):
    sizes = [len(payload.encode("utf-8")) for payload in payloads]
    print(f"{name}:")
    print(f"  apps: {len(sizes)}")
    print(f"  bytes/app min avg max: {min(sizes)} {sum(sizes) // len(sizes)} {max(sizes)}")
    print(f"  total payload bytes: {sum(sizes)}")


def main():
    sender = load_sender()
    strip, _ = sender.prepare_strip("vertical")

    four_full = [
        sender.saved_app_payload(frame, 2, 0)
        for frame in sender.make_saved_slices(strip, "vertical", 4, sender.HEIGHT)
    ]
    paired_bars = [
        sender.saved_app_payload(frame, 1, 0)
        for frame in sender.make_paired_bar_frames(strip, "vertical", 8, 4)
    ]
    black_probe = [sender.saved_app_payload(frame, 1, 0) for frame in sender.make_saved_slices(strip, "vertical", 1, sender.HEIGHT)]

    describe("4 full 32x8 sacred apps", four_full)
    describe("8 paired 32x4-bar sacred apps", paired_bars)
    describe("1 representative sacred 32x8 payload", black_probe)


if __name__ == "__main__":
    main()
