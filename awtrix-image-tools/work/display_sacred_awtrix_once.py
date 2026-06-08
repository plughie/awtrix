#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
import argparse


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Display the sacred square animation once, then exit.")
    parser.add_argument("--source", choices=["saved-bars", "stream"], default="saved-bars")
    parser.add_argument("--method", choices=["http", "mqtt"], default="http")
    parser.add_argument("--display", default="192.168.8.99")
    parser.add_argument("--broker", default="192.168.8.139")
    parser.add_argument("--prefix", default="awtrix")
    parser.add_argument("--direction", choices=["vertical", "horizontal"], default="vertical")
    parser.add_argument("--seconds", default="8")
    parser.add_argument("--fps", default="5")
    parser.add_argument("--series-count", default="8")
    parser.add_argument("--app-prefix", default="sacred_square_bar")
    args = parser.parse_args()

    mode = "run-series" if args.source == "saved-bars" else "stream"
    command = [
        sys.executable,
        str(ROOT / "send_sacred_awtrix.py"),
        "--method",
        args.method,
        "--mode",
        mode,
        "--direction",
        args.direction,
        "--seconds",
        args.seconds,
        "--fps",
        args.fps,
        "--display",
        args.display,
        "--broker",
        args.broker,
        "--prefix",
        args.prefix,
        "--series-count",
        args.series_count,
        "--app-prefix",
        args.app_prefix,
        "--preview",
        "outputs/sacred_awtrix_vertical_preview.png",
    ]
    raise SystemExit(subprocess.call(command, cwd=ROOT.parent))


if __name__ == "__main__":
    main()
