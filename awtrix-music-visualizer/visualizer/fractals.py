"""Fractal/procedural visualizations for the 32x8 matrix.

Audio-reactive: band amplitudes drive parameters of the patterns.
Vectorized with numpy for speed. Rendered as 2px-wide blocks to keep
payload small enough for the ESP32 to handle at reasonable frame rates.
"""

from __future__ import annotations

import colorsys
import time

import numpy as np

WIDTH = 32
HEIGHT = 8

# Precompute pixel coordinate grids.
_X = np.arange(WIDTH, dtype=np.float32)
_Y = np.arange(HEIGHT, dtype=np.float32)
_XX, _YY = np.meshgrid(_X, _Y)  # shape (8, 32)


def _hsv_to_rgb_array(h: np.ndarray, s: np.ndarray, v: np.ndarray):
    """Vectorized HSV to RGB. All inputs shape (H, W), values 0..1."""
    h = h % 1.0
    i = (h * 6.0).astype(np.int32)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6

    r = np.where(i == 0, v, np.where(i == 1, q, np.where(i == 2, p,
        np.where(i == 3, p, np.where(i == 4, t, v)))))
    g = np.where(i == 0, t, np.where(i == 1, v, np.where(i == 2, v,
        np.where(i == 3, q, np.where(i == 4, p, p)))))
    b = np.where(i == 0, p, np.where(i == 1, p, np.where(i == 2, t,
        np.where(i == 3, v, np.where(i == 4, v, q)))))

    return (np.clip(r * 255, 0, 255).astype(np.uint8),
            np.clip(g * 255, 0, 255).astype(np.uint8),
            np.clip(b * 255, 0, 255).astype(np.uint8))


def _pixels_to_draw(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> list[dict]:
    """Convert RGB arrays (H,W) to AWTRIX df commands at 4x2 pixel blocks.

    Renders at effective 8x4 resolution (8 columns, 4 rows of blocks),
    each block being 4px wide x 2px tall. This keeps total command count
    at 32 max, well within what the ESP32 can handle.
    """
    draw: list[dict] = []
    block_w = 4
    block_h = 2
    for by in range(0, HEIGHT, block_h):
        for bx in range(0, WIDTH, block_w):
            # Sample the center of the block.
            sy = min(by + block_h // 2, HEIGHT - 1)
            sx = min(bx + block_w // 2, WIDTH - 1)
            rv, gv, bv = int(r[sy, sx]), int(g[sy, sx]), int(b[sy, sx])
            if rv < 8 and gv < 8 and bv < 8:
                continue
            draw.append({"df": [bx, by, block_w, block_h, f"#{rv:02X}{gv:02X}{bv:02X}"]})
    return draw


def render_plasma(bands: np.ndarray, scheme: str) -> list[dict]:
    """Audio-reactive plasma: sine-wave interference pattern (vectorized)."""
    t = time.monotonic()
    n = len(bands)
    bass = float(np.mean(bands[: n // 4]))
    mid = float(np.mean(bands[n // 4: n * 3 // 4]))
    treble = float(np.mean(bands[n * 3 // 4:]))
    energy = float(np.mean(bands))

    freq1 = 0.3 + bass * 0.4
    freq2 = 0.2 + mid * 0.3
    phase1 = t * (1.0 + energy * 2.0)
    phase2 = t * 0.7 + treble * 3.0

    v1 = np.sin(_XX * freq1 + phase1)
    v2 = np.sin(_YY * freq2 + phase2)
    v3 = np.sin((_XX * freq1 + _YY * freq2 + t * 1.5) * 0.5)
    dist = np.sqrt((_XX - 16) ** 2 + (_YY - 4) ** 2)
    v4 = np.sin(dist * 0.3 + t + bass * 4)
    v = (v1 + v2 + v3 + v4) / 4.0
    v = (v + 1.0) * 0.5  # 0..1

    # Map to HSV based on scheme.
    hue = (v + t * 0.1 + energy * 0.3) % 1.0
    brightness = np.full_like(v, 0.3 + energy * 0.7)
    sat = np.full_like(v, 0.9)

    if scheme == "outrun":
        hue = 0.7 + v * 0.2 + energy * 0.1
    elif scheme == "fire":
        hue = v * 0.12
        brightness = 0.2 + v * 0.8
    elif scheme == "ocean":
        hue = 0.45 + v * 0.15
    elif scheme == "matrix":
        hue = np.full_like(v, 0.33)
        brightness = v * (0.3 + energy * 0.7)
    elif scheme == "neon":
        hue = 0.85 + v * 0.5
    elif scheme == "ice":
        hue = 0.55 + v * 0.1
        brightness = 0.4 + v * 0.6
    elif scheme == "sunset":
        hue = 0.08 + v * 0.12
    elif scheme == "forest":
        hue = 0.25 + v * 0.1

    r, g, b = _hsv_to_rgb_array(
        np.asarray(hue, dtype=np.float32),
        np.asarray(sat, dtype=np.float32),
        np.clip(np.asarray(brightness, dtype=np.float32), 0, 1),
    )
    return _pixels_to_draw(r, g, b)


def render_julia(bands: np.ndarray, scheme: str) -> list[dict]:
    """Audio-reactive Julia set (vectorized)."""
    t = time.monotonic()
    n = len(bands)
    bass = float(np.mean(bands[: n // 4]))
    mid = float(np.mean(bands[n // 4: n * 3 // 4]))
    energy = float(np.mean(bands))

    angle = t * 0.5 + bass * 2.0
    radius = 0.7 + mid * 0.15
    c_re = radius * np.cos(angle)
    c_im = radius * np.sin(angle) * 0.5

    max_iter = 10

    # Map pixels to complex plane.
    z_re = (_XX - WIDTH / 2) / (WIDTH / 3.5)
    z_im = (_YY - HEIGHT / 2) / (HEIGHT / 2.5)

    # Iterate.
    iteration = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    mask = np.ones((HEIGHT, WIDTH), dtype=bool)

    for i in range(max_iter):
        new_re = z_re * z_re - z_im * z_im + c_re
        new_im = 2.0 * z_re * z_im + c_im
        z_re = np.where(mask, new_re, z_re)
        z_im = np.where(mask, new_im, z_im)
        escaped = (z_re * z_re + z_im * z_im) > 4.0
        iteration = np.where(mask & escaped, i, iteration)
        mask = mask & ~escaped

    # Normalize iteration count.
    frac = iteration / max_iter
    hue_offset = t * 0.05 + energy * 0.3

    if scheme == "outrun":
        hue = 0.7 + frac * 0.25 + hue_offset
    elif scheme == "fire":
        hue = frac * 0.12
    elif scheme == "ocean":
        hue = 0.5 + frac * 0.15 + hue_offset
    elif scheme == "neon":
        hue = 0.85 + frac * 0.4 + hue_offset
    elif scheme == "matrix":
        hue = np.full_like(frac, 0.33)
    elif scheme == "sunset":
        hue = 0.05 + frac * 0.15 + hue_offset
    elif scheme == "forest":
        hue = 0.25 + frac * 0.12 + hue_offset
    else:
        hue = frac * 0.8 + hue_offset

    brightness = np.clip(0.4 + frac * 0.6 + energy * 0.3, 0, 1)
    # Black out interior points (never escaped).
    brightness = np.where(mask, 0.0, brightness)

    r, g, b = _hsv_to_rgb_array(
        np.asarray(hue, dtype=np.float32) % 1.0,
        np.full((HEIGHT, WIDTH), 0.85, dtype=np.float32),
        np.asarray(brightness, dtype=np.float32),
    )
    return _pixels_to_draw(r, g, b)
