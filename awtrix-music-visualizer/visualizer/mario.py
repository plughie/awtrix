"""Super Mario Bros themed spectrum visualizers (overworld + underground).

Spectrum bars rendered as pipes/blocks rising from a ground line, themed
with authentic NES palettes. Overworld: blue sky, green pipes, brown ground.
Underground: black background, teal blocks, gold-trimmed ground.
"""

from __future__ import annotations

import time

import numpy as np

WIDTH = 32
HEIGHT = 8
GROUND_Y = 7

# Overworld palette.
_OVERWORLD = {
    "bg": "#5A93F5",
    "pipe": "#41B60B",
    "pipe_dark": "#2E7A08",
    "ground": "#BF4C11",
    "ground_dark": "#492F20",
    "block": "#CD8964",
    "block_light": "#E0A77A",
    "accent": "#FFFFFF",
}

# Underground palette.
_UNDERGROUND = {
    "bg": "#000101",
    "pipe": "#098B8D",
    "pipe_dark": "#164141",
    "ground": "#098B8D",
    "ground_dark": "#164141",
    "block": "#D38D19",
    "block_light": "#9CD2DE",
    "accent": "#9CD2DE",
}


def _fill_rect(draw: list, x: int, y: int, w: int, h: int, color: str):
    if w <= 0 or h <= 0:
        return
    draw.append({"df": [x, y, w, h, color]})


def _px(draw: list, x: int, y: int, color: str):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        draw.append({"dp": [x, y, color]})


def _render(bands: np.ndarray, pal: dict, underground: bool) -> list[dict]:
    t = time.monotonic()
    n = len(bands)
    energy = float(np.mean(bands))

    draw: list[dict] = []

    # Background.
    _fill_rect(draw, 0, 0, WIDTH, HEIGHT, pal["bg"])

    if not underground:
        # Overworld: scrolling cloud.
        cloud_x = WIDTH - int((t * 3) % (WIDTH + 6))
        for dx, dy in [(0, 0), (1, 0), (2, 0), (1, -1), (-1, 0)]:
            _px(draw, cloud_x + dx, 1 + dy, pal["accent"])
    else:
        # Underground: ceiling row of blocks along the top.
        for x in range(0, WIDTH, 2):
            _px(draw, x, 0, pal["ground_dark"])

    # Pipes/blocks: spectrum bars rising from ground.
    num_pipes = 8
    pipe_w = 3
    gap = 1
    total_w = num_pipes * (pipe_w + gap)
    start_x = max(0, (WIDTH - total_w) // 2)

    for p in range(num_pipes):
        lo = p * n // num_pipes
        hi = (p + 1) * n // num_pipes
        level = float(np.clip(np.mean(bands[lo:hi]), 0.0, 1.0))
        ph = int(round(level * 5))
        px = start_x + p * (pipe_w + gap)
        if ph <= 0:
            continue
        top_y = GROUND_Y - ph
        _fill_rect(draw, px, top_y, pipe_w, ph, pal["pipe"])
        # Top rim.
        _fill_rect(draw, px, top_y, pipe_w, 1, pal["pipe_dark"])
        # Dark right edge for depth.
        for yy in range(top_y, GROUND_Y):
            _px(draw, px + pipe_w - 1, yy, pal["pipe_dark"])

    # Ground row.
    _fill_rect(draw, 0, GROUND_Y, WIDTH, 1, pal["ground"])
    for x in range(0, WIDTH, 4):
        _px(draw, x, GROUND_Y, pal["ground_dark"])

    # Bouncing question block on high energy.
    if energy > 0.45:
        block_y = 1 - int(round((energy - 0.45) * 3))
        block_x = WIDTH // 2 - 1
        _fill_rect(draw, block_x, max(0, block_y), 2, 2, pal["block"])
        _px(draw, block_x, max(0, block_y), pal["block_light"])

    return draw


def render_mario(bands: np.ndarray, scheme: str) -> list[dict]:
    """Render the Mario overworld spectrum."""
    return _render(bands, _OVERWORLD, underground=False)


def render_mario_underground(bands: np.ndarray, scheme: str) -> list[dict]:
    """Render the Mario underground spectrum."""
    return _render(bands, _UNDERGROUND, underground=True)
