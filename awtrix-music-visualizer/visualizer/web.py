"""Lightweight web UI for live parameter tuning.

Runs on a background thread using only the stdlib http.server. No extra deps.
The main loop reads from `live_settings` which this server updates via POST.
Settings are persisted to config.toml so they survive restarts.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, fields
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .config import RenderConfig

# Shared mutable state — the main loop reads these values each frame.
live_settings: dict[str, Any] = {}

# Path to config file, set by init_live_settings.
_config_path: Path | None = None

_HTML: str | None = None
_save_lock = threading.Lock()


def _get_html() -> str:
    global _HTML
    if _HTML is None:
        from pathlib import Path

        html_path = Path(__file__).parent / "ui.html"
        _HTML = html_path.read_text(encoding="utf-8")
    return _HTML


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: ARG002
        pass  # silence request logs

    def do_GET(self):
        if self.path == "/api/settings":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(live_settings).encode())
        else:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_get_html().encode("utf-8"))

    def do_POST(self):
        if self.path == "/api/settings":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                # Validate and coerce types based on RenderConfig fields.
                for key, value in data.items():
                    if key in _FIELD_TYPES:
                        expected = _FIELD_TYPES[key]
                        if expected is bool:
                            value = bool(value)
                        elif expected is int:
                            value = int(value)
                        elif expected is float:
                            value = float(value)
                        else:
                            value = str(value)
                    live_settings[key] = value
                _save_to_config()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
            except Exception as exc:
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.end_headers()
                self.wfile.write(str(exc).encode())
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# Build a type map from RenderConfig for validation.
_FIELD_TYPES: dict[str, type] = {f.name: f.type for f in fields(RenderConfig)}
# Resolve string type annotations to actual types.
_TYPE_MAP = {"int": int, "float": float, "bool": bool, "str": str}
_FIELD_TYPES = {k: _TYPE_MAP.get(v, str) for k, v in _FIELD_TYPES.items()}


def init_live_settings(render_cfg: RenderConfig, config_path: str = "config.toml") -> None:
    """Populate live_settings from the loaded config."""
    global _config_path
    _config_path = Path(config_path)
    live_settings.clear()
    live_settings.update(asdict(render_cfg))


def _save_to_config() -> None:
    """Write current live_settings back into the [render] section of config.toml."""
    if _config_path is None or not _config_path.exists():
        return

    with _save_lock:
        lines = _config_path.read_text(encoding="utf-8").splitlines(keepends=True)
        # Find the [render] section and update keys in place, or append missing ones.
        in_render = False
        render_start = -1
        render_end = len(lines)
        written_keys: set[str] = set()
        new_lines: list[str] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("["):
                if in_render:
                    # End of [render] section — insert any keys we haven't written yet.
                    for key, val in live_settings.items():
                        if key not in written_keys and key in _FIELD_TYPES:
                            new_lines.append(f"{key} = {_format_toml_value(val, key)}\n")
                    in_render = False
                if stripped == "[render]":
                    in_render = True
                    render_start = i
                new_lines.append(line)
                continue

            if in_render and "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                if key in live_settings and key in _FIELD_TYPES:
                    val = live_settings[key]
                    new_lines.append(f"{key} = {_format_toml_value(val, key)}\n")
                    written_keys.add(key)
                    continue

            new_lines.append(line)

        # If we were still in [render] at EOF, append remaining keys.
        if in_render:
            for key, val in live_settings.items():
                if key not in written_keys and key in _FIELD_TYPES:
                    new_lines.append(f"{key} = {_format_toml_value(val, key)}\n")

        _config_path.write_text("".join(new_lines), encoding="utf-8")


def _format_toml_value(val: Any, key: str) -> str:
    """Format a Python value as a TOML literal."""
    expected = _FIELD_TYPES.get(key, str)
    if expected is bool:
        return "true" if val else "false"
    if expected is int:
        return str(int(val))
    if expected is float:
        return str(float(val))
    # String — quote it.
    return f'"{val}"'


def start_web_server(port: int = 8888) -> threading.Thread:
    """Start the web UI server on a daemon thread. Returns the thread."""
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
