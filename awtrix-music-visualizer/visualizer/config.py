"""Configuration loading for the visualizer."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeviceConfig:
    ip: str = "192.168.1.50"
    transport: str = "http"  # "http" | "mqtt"
    app_name: str = "visualizer"


@dataclass
class MqttConfig:
    host: str = "192.168.1.10"
    port: int = 1883
    username: str = ""
    password: str = ""
    prefix: str = "awtrix"


@dataclass
class AudioConfig:
    device: str = ""
    loopback: bool = True
    samplerate: int = 44100
    blocksize: int = 1024


@dataclass
class RenderConfig:
    enabled: bool = True  # master toggle — when false, visualizer goes idle
    bands: int = 16
    mode: str = "draw"  # "bar" | "draw"
    fps: int = 20
    smoothing: float = 0.5
    min_freq: float = 60.0
    max_freq: float = 16000.0
    gain: float = 1.6
    scheme: str = "spectrum"  # "spectrum" | "fire" | "solid"
    solid_color: str = "#00FFAA"
    peak_dots: bool = True
    idle_seconds: float = 5.0  # switch to clock after this many seconds of silence
    idle_app: str = "Time"  # app to show when idle (built-in: Time, Date, etc.)
    overlay_text: str = ""  # text to knock out (negative) from the spectrum
    overlay_color: str = "#000000"  # color of the knocked-out text
    color_cycle: bool = False  # animate the color palette (smooth rotation)
    color_cycle_speed: float = 1.0  # rotations per 10 seconds (higher = faster)
    fractal_type: str = "plasma"  # "plasma" or "julia" (used when mode = "fractal")


@dataclass
class Config:
    device: DeviceConfig = field(default_factory=DeviceConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    render: RenderConfig = field(default_factory=RenderConfig)


def _merge(dc, data: dict):
    """Return a dataclass instance overriding defaults with provided keys."""
    known = {f for f in dc.__dataclass_fields__}
    filtered = {k: v for k, v in data.items() if k in known}
    return dc(**filtered)


def load_config(path: str | Path = "config.toml") -> Config:
    path = Path(path)
    # Fall back to the bundled example if the user hasn't created config.toml yet.
    if not path.exists():
        example = path.with_name("config.example.toml")
        if example.exists():
            path = example
        else:
            return Config()

    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    return Config(
        device=_merge(DeviceConfig, raw.get("device", {})),
        mqtt=_merge(MqttConfig, raw.get("mqtt", {})),
        audio=_merge(AudioConfig, raw.get("audio", {})),
        render=_merge(RenderConfig, raw.get("render", {})),
    )
