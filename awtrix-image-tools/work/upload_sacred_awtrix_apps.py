#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
import argparse


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Upload eight saved AWTRIX apps as paired 32x4 bar windows.")
    parser.add_argument("--method", choices=["http", "mqtt"], default="http")
    parser.add_argument("--display", default="192.168.8.99")
    parser.add_argument("--broker", default="192.168.8.139")
    parser.add_argument("--prefix", default="awtrix")
    parser.add_argument("--direction", choices=["vertical", "horizontal"], default="vertical")
    parser.add_argument("--seconds", default="8")
    parser.add_argument("--series-count", default="8")
    parser.add_argument("--slice-height", default="4")
    parser.add_argument("--draw-y", default="0")
    parser.add_argument("--app-prefix", default="sacred_square_bar")
    args = parser.parse_args()

    command = [
        sys.executable,
        str(ROOT / "send_sacred_awtrix.py"),
        "--method",
        args.method,
        "--mode",
        "upload-series",
        "--direction",
        args.direction,
        "--seconds",
        args.seconds,
        "--series-count",
        args.series_count,
        "--slice-height",
        args.slice_height,
        "--draw-y",
        args.draw_y,
        "--pair-bars",
        "--app-prefix",
        args.app_prefix,
        "--display",
        args.display,
        "--broker",
        args.broker,
        "--prefix",
        args.prefix,
        "--preview",
        "outputs/sacred_awtrix_8bar_vertical_preview.png",
    ]
    raise SystemExit(subprocess.call(command, cwd=ROOT.parent))


if __name__ == "__main__":
    main()
