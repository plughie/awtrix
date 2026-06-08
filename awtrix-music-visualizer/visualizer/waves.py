"""Joy Division / Unknown Pleasures style waveform landscape.

Stacked waveform lines scrolling upward. Peaks extend high into the space
above, creating overlapping mountain silhouettes. Draw commands are kept
minimal by using line segments and skipping occlusion fill (the aesthetic
works fine without it on a tiny 32x8 display — overlapping lines just
cross over each other which looks great).
"""

from __future__ import annotations

import math
import time

import numpy as np

WIDTH = 32
HEIGHT = 8

_NUM_ROWS = 5
_history: list[np.ndarray] = []
_last_push_time: float = 0.0
_SCROLL_INTERVAL = 0.18


def render_waves(bands: np.ndarray, scheme: str) -> list[dict]:
    """Render the Unknown Pleasures waveform landscape."""
    global _last_push_time

    t = time.monotonic()
    n = len(bands)

    # Build waveform from bands. Apply some smoothing for fluid look.
    raw = np.interp(np.linspace(0, n - 1, WIDTH), np.arange(n), bands)
    # Gentle sine carrier so even silent parts have some waviness.
    carrier = np.sin(np.linspace(0, math.pi * 2.5, WIDTH) + t * 1.8) * 0.06
    wave = np.clip(raw + carrier, 0.0, 1.0)

    # Push new row on interval.
    if t - _last_push_time >= _SCROLL_INTERVAL:
        _last_push_time = t
        _history.insert(0, wave.copy())
        if len(_history) > _NUM_ROWS:
            _history.pop()

    # Color.
    colors = {
        "outrun": "#FF00AA", "ocean": "#00DDFF", "neon": "#00FF88",
        "fire": "#FF8800", "matrix": "#00FF00", "sunset": "#FF6600",
        "ice": "#AADDFF", "forest": "#44DD22",
    }
    color = colors.get(scheme, "#FFFFFF")

    draw: list[dict] = []
    num_rows = len(_history)
    if num_rows == 0:
        return [{"dp": [0, 0, "#000000"]}]

    # Row baselines spread across the display height.
    # Newest row at bottom (y=7), oldest near top.
    # Spacing of ~1.5px gives overlap room.
    for row_idx in range(num_rows - 1, -1, -1):
        wave_data = _history[row_idx]

        # Baseline Y for this row: newest=7, going up.
        base_y = HEIGHT - 1 - int(round(row_idx * 1.5))
        if base_y < 0:
            continue

        # Max peak displacement: up to 5 pixels above baseline.
        # Front (newer) rows get full height, back rows get less.
        max_disp = 5.0 * (1.0 - row_idx * 0.12)

        # Compute wave Y positions.
        y_per_x: list[int] = []
        for x in range(WIDTH):
            amp = float(wave_data[x])
            disp = int(round(amp * max_disp))
            wy = max(0, base_y - disp)
            y_per_x.append(wy)

        # Draw as connected line segments (merge adjacent same-y pixels).
        seg_start = 0
        for x in range(1, WIDTH + 1):
            if x < WIDTH and y_per_x[x] == y_per_x[x - 1]:
                continue
            sy = y_per_x[seg_start]
            if 0 <= sy < HEIGHT:
                draw.append({"dl": [seg_start, sy, x - 1, sy, color]})
            seg_start = x

    if not draw:
        draw.append({"dp": [0, 0, "#000000"]})

    return draw
