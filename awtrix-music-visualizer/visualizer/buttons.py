"""MQTT listener for AWTRIX physical button presses.

Subscribes to the button topics and maps presses to actions:
- Left button:  cycle color scheme
- Middle button: toggle enabled on/off
- Right button: cycle render mode
"""

from __future__ import annotations

import threading

from .config import Config
from .web import live_settings, _save_to_config

# Available modes and schemes to cycle through.
MODES = ["draw", "horizontal", "ltr", "waves", "mario", "mario_underground", "dancer", "fractal"]
SCHEMES = ["spectrum", "outrun", "fire", "ocean", "forest", "ice", "neon", "sunset", "matrix"]


def _cycle(current: str, options: list[str]) -> str:
    """Return the next option in the list, wrapping around."""
    try:
        idx = options.index(current)
    except ValueError:
        idx = -1
    return options[(idx + 1) % len(options)]


def _on_button(button: str):
    """Handle a button press."""
    if button == "L":
        # Cycle color scheme.
        current = live_settings.get("scheme", "spectrum")
        new_scheme = _cycle(current, SCHEMES)
        live_settings["scheme"] = new_scheme
        _save_to_config()

    elif button == "M":
        # Toggle enabled.
        current = live_settings.get("enabled", True)
        live_settings["enabled"] = not current
        _save_to_config()

    elif button == "R":
        # Cycle render mode.
        current = live_settings.get("mode", "draw")
        new_mode = _cycle(current, MODES)
        live_settings["mode"] = new_mode
        _save_to_config()


def start_button_listener(cfg: Config) -> threading.Thread | None:
    """Start an MQTT subscriber for button events. Returns the thread or None."""
    if not cfg.mqtt.host:
        return None

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return None

    # Build the button topic pattern.
    # Topics look like: <prefix>/<mac>/<id>_btnL/stat_t
    prefix = cfg.mqtt.prefix
    # Subscribe to all button topics under the prefix.
    topic = f"{prefix}/+/+_btn+/stat_t"
    # Simpler: subscribe to everything and filter in the callback.
    wild_topic = f"{prefix}/#"

    def on_connect(client, userdata, flags, rc, properties=None):
        client.subscribe(wild_topic)

    def on_message(client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        # Only react to "ON" (press), not "OFF" (release).
        if payload != "ON":
            return
        # Determine which button from the topic name.
        if "_btnL/" in topic:
            _on_button("L")
        elif "_btnM/" in topic:
            _on_button("M")
        elif "_btnR/" in topic:
            _on_button("R")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id="awtrix-vis-buttons"
    )
    if cfg.mqtt.username:
        client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(cfg.mqtt.host, cfg.mqtt.port, keepalive=60)
    except Exception:
        return None

    client.loop_start()
    return threading.Thread()  # Return a dummy; the paho loop is its own thread.
