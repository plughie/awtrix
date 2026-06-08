"""Entry point: capture audio, analyze, render, and stream to AWTRIX.

Usage:
    python -m visualizer                 # run with config.toml
    python -m visualizer --list-devices  # list audio devices and exit
    python -m visualizer --config path   # use an alternate config file
    python -m visualizer --no-web        # disable the web UI
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from .audio import AudioStream, BandAnalyzer, list_devices
from .buttons import start_button_listener
from .config import load_config
from .render import Renderer
from .transport import make_transport
from .web import init_live_settings, live_settings, start_web_server

# RMS threshold below which audio is considered silence.
SILENCE_THRESHOLD = 0.001

WEB_PORT = 8888


def _apply_live_settings(analyzer: BandAnalyzer, renderer: Renderer):
    """Push live_settings changes into the analyzer and renderer."""
    s = live_settings

    # Analyzer params.
    if "gain" in s:
        analyzer.gain = float(s["gain"])
    if "smoothing" in s:
        analyzer.smoothing = float(np.clip(s["smoothing"], 0.0, 0.99))

    # Renderer params.
    renderer.cfg.mode = s.get("mode", renderer.cfg.mode)
    renderer.cfg.scheme = s.get("scheme", renderer.cfg.scheme)
    renderer.cfg.solid_color = s.get("solid_color", renderer.cfg.solid_color)
    renderer.cfg.peak_dots = bool(s.get("peak_dots", renderer.cfg.peak_dots))
    renderer.cfg.overlay_text = s.get("overlay_text", renderer.cfg.overlay_text)
    renderer.cfg.overlay_color = s.get("overlay_color", renderer.cfg.overlay_color)
    renderer.cfg.color_cycle = bool(s.get("color_cycle", renderer.cfg.color_cycle))
    renderer.cfg.color_cycle_speed = float(s.get("color_cycle_speed", renderer.cfg.color_cycle_speed))
    renderer.cfg.fractal_type = s.get("fractal_type", renderer.cfg.fractal_type)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AWTRIX music visualizer")
    parser.add_argument("--config", default="config.toml", help="path to config file")
    parser.add_argument(
        "--list-devices", action="store_true", help="list audio devices and exit"
    )
    parser.add_argument(
        "--no-web", action="store_true", help="disable the web control panel"
    )
    parser.add_argument(
        "--port", type=int, default=WEB_PORT, help="web UI port (default 8888)"
    )
    args = parser.parse_args(argv)

    if args.list_devices:
        print(list_devices())
        return 0

    cfg = load_config(args.config)

    analyzer = BandAnalyzer(cfg.audio, cfg.render)
    renderer = Renderer(cfg.render)
    transport = make_transport(cfg)

    # Initialize live settings from config and start web UI.
    init_live_settings(cfg.render, config_path=args.config)
    if not args.no_web:
        start_web_server(args.port)
        print(f"Web UI: http://localhost:{args.port}")

    # Listen for physical button presses via MQTT.
    start_button_listener(cfg)
    print("Buttons: L=scheme, M=enable/disable, R=mode")

    print(
        f"Streaming to {cfg.device.ip} via {cfg.device.transport} "
        f"as app '{cfg.device.app_name}' "
        f"({cfg.render.bands} bands, {cfg.render.mode} mode, {cfg.render.fps} fps)."
    )
    idle_timeout = cfg.render.idle_seconds
    idle_app = cfg.render.idle_app
    print(f"Idle: show '{idle_app}' after {idle_timeout}s of silence.")
    print("Press Ctrl+C to stop.")

    try:
        with AudioStream(cfg.audio) as stream:
            # Switch to our custom app so it's visible immediately.
            transport.switch_app(cfg.device.app_name)

            next_frame = time.monotonic()
            last_sound_time = time.monotonic()
            is_idle = False

            while True:
                samples = stream.read(timeout=0.1)
                if samples is None:
                    continue

                now = time.monotonic()

                # Apply any live setting changes from the web UI.
                _apply_live_settings(analyzer, renderer)
                target_fps = int(live_settings.get("fps", cfg.render.fps))
                # Cap fps for fractal mode to avoid overwhelming the ESP32.
                mode = live_settings.get("mode", cfg.render.mode)
                if mode == "fractal":
                    target_fps = min(target_fps, 10)
                frame_interval = 1.0 / max(1, target_fps)
                idle_timeout = float(live_settings.get("idle_seconds", cfg.render.idle_seconds))
                idle_app = str(live_settings.get("idle_app", cfg.render.idle_app))

                # Master enable toggle.
                enabled = bool(live_settings.get("enabled", True))
                if not enabled:
                    if not is_idle:
                        is_idle = True
                        transport.clear()
                        transport.switch_app(idle_app)
                    continue
                elif is_idle:
                    # Re-enabled: immediately switch back to the visualizer.
                    is_idle = False
                    last_sound_time = now
                    transport.switch_app(cfg.device.app_name)

                # Detect silence by RMS of the raw block.
                rms = float(np.sqrt(np.mean(samples ** 2)))
                if rms > SILENCE_THRESHOLD:
                    last_sound_time = now
                    if is_idle:
                        is_idle = False
                        transport.switch_app(cfg.device.app_name)

                # Check if we've been silent long enough to go idle.
                if not is_idle and (now - last_sound_time) >= idle_timeout:
                    is_idle = True
                    transport.switch_app(idle_app)

                # While idle, skip rendering to reduce network/CPU load.
                if is_idle:
                    continue

                bands = analyzer.process(
                    samples[:, 0] if samples.ndim > 1 else samples
                )
                payload = renderer.render(bands)

                if now >= next_frame:
                    transport.send(payload)
                    next_frame = now + frame_interval

    except KeyboardInterrupt:
        print("\nStopping, clearing display...")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        transport.close()
        return 1
    finally:
        transport.clear()
        transport.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
