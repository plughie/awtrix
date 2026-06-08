"""Dancing stick figure mode for the 32x8 matrix.

A more detailed stick figure with a 2px head, torso, distinct arms and legs.
Multiple dance move styles cycle based on the beat. Steps across the screen
one pixel per beat, bouncing off edges.
"""

from __future__ import annotations

import math
import time

import numpy as np

WIDTH = 32
HEIGHT = 8
FLOOR_Y = 7
COLOR = "#FFFFFF"

_state = {
    "x": 16,
    "direction": 1,
    "last_bass": 0.0,
    "beat_cooldown": 0.0,
    "beat_count": 0,  # tracks total beats for cycling moves
}

BEAT_THRESHOLD = 0.35
BEAT_COOLDOWN = 0.15


def _px(draw: list, x: int, y: int, color: str = COLOR):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        draw.append({"dp": [x, y, color]})


def _line(draw: list, x0: int, y0: int, x1: int, y1: int, color: str = COLOR):
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    steps = max(dx, dy, 1)
    for i in range(steps + 1):
        t = i / steps
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        _px(draw, x, y, color)


def render_dancer(bands: np.ndarray, scheme: str) -> list[dict]:
    """Render a dancing stick figure with varied moves."""
    t = time.monotonic()
    n = len(bands)
    bass = float(np.mean(bands[: n // 4]))
    mid = float(np.mean(bands[n // 4: n * 3 // 4]))
    treble = float(np.mean(bands[n * 3 // 4:]))
    energy = float(np.mean(bands))

    # Beat detection.
    prev_bass = _state["last_bass"]
    _state["last_bass"] = bass
    is_beat = (
        bass > BEAT_THRESHOLD
        and bass > prev_bass + 0.05
        and (t - _state["beat_cooldown"]) > BEAT_COOLDOWN
    )
    if is_beat:
        _state["beat_cooldown"] = t
        _state["beat_count"] += 1
        _state["x"] += _state["direction"]
        if _state["x"] >= WIDTH - 4:
            _state["x"] = WIDTH - 4
            _state["direction"] = -1
        elif _state["x"] <= 3:
            _state["x"] = 3
            _state["direction"] = 1

    cx = _state["x"]
    beat_count = _state["beat_count"]
    # Cycle through 5 dance move styles every 8 beats.
    move = (beat_count // 8) % 5

    draw: list[dict] = []

    # Body bounce on beat.
    bounce = 1 if is_beat else 0

    # Key positions (bottom-up). Figure is 7px tall.
    # Feet: y=7, Knees: y=6, Hips: y=5, Torso: y=4-3, Shoulders: y=3, Head: y=1-2
    hip_y = 5 - bounce
    shoulder_y = 3 - bounce
    head_y = 1 - bounce + int(round(treble * 0.4))

    # === HEAD (2px wide for more human look) ===
    _px(draw, cx, max(0, head_y))
    _px(draw, cx + 1, max(0, head_y))

    # === TORSO (shoulder to hip) ===
    _line(draw, cx, shoulder_y, cx, hip_y)

    # === DANCE MOVES ===
    phase = t * 5.0

    if move == 0:
        # "The Groove" — arms pump up/down, legs wide stance shuffle.
        arm_pump = math.sin(phase + mid * 4) * 0.8
        # Left arm: up when pump positive.
        la_y = shoulder_y + int(round((1.0 - arm_pump) * 1.5))
        _line(draw, cx - 1, shoulder_y, cx - 2, min(FLOOR_Y - 1, la_y))
        # Right arm: opposite phase.
        ra_y = shoulder_y + int(round((1.0 + arm_pump) * 1.5))
        _line(draw, cx + 1, shoulder_y, cx + 3, min(FLOOR_Y - 1, ra_y))
        # Legs: alternating wide stance.
        leg_off = int(round(math.sin(phase) * 1.5))
        _line(draw, cx, hip_y, cx - 1 + leg_off, FLOOR_Y)
        _line(draw, cx, hip_y, cx + 1 - leg_off, FLOOR_Y)

    elif move == 1:
        # "The Point" — one arm points up to sky, other on hip. Legs kick.
        # Pointing arm.
        _line(draw, cx + 1, shoulder_y, cx + 3, max(0, shoulder_y - 2))
        # Hip arm.
        _px(draw, cx - 1, hip_y)
        # Kick leg.
        kick = int(round(math.sin(phase * 1.2) * 2))
        _line(draw, cx, hip_y, cx + kick, FLOOR_Y)
        _line(draw, cx, hip_y, cx - 1, FLOOR_Y)

    elif move == 2:
        # "The Robot" — stiff angular arms, march legs.
        arm_angle = int(round(math.sin(phase * 0.8) * 2))
        # Arms at right angles.
        _line(draw, cx - 1, shoulder_y, cx - 2, shoulder_y)
        _px(draw, cx - 2, shoulder_y + 1 + abs(arm_angle) % 2)
        _line(draw, cx + 1, shoulder_y, cx + 2, shoulder_y)
        _px(draw, cx + 2, shoulder_y + 1 + (abs(arm_angle) + 1) % 2)
        # March legs — one forward, one back.
        march = int(round(math.sin(phase) * 1))
        _line(draw, cx, hip_y, cx + march, FLOOR_Y)
        _line(draw, cx, hip_y, cx - march, FLOOR_Y)

    elif move == 3:
        # "The Wave" — both arms do a wave motion, hips sway.
        sway = int(round(math.sin(phase * 0.6) * 1))
        # Arms do a wave (different phase each).
        la_h = shoulder_y - 1 + int(round(math.sin(phase) * 1.2))
        ra_h = shoulder_y - 1 + int(round(math.sin(phase + 1.5) * 1.2))
        _line(draw, cx - 1, shoulder_y, cx - 2, max(0, la_h))
        _line(draw, cx + 1, shoulder_y, cx + 3, max(0, ra_h))
        # Legs with hip sway.
        _line(draw, cx + sway, hip_y, cx - 1 + sway, FLOOR_Y)
        _line(draw, cx + sway, hip_y, cx + 1 + sway, FLOOR_Y)

    elif move == 4:
        # "The Moonwalk" — one foot slides back while the other stays planted,
        # body leans slightly back, arms swing opposite to legs.
        slide_phase = (phase * 0.7) % (math.pi * 2)
        slide = math.sin(slide_phase)  # -1..1

        # Front foot planted, back foot slides.
        front_x = cx + int(round(slide * 1.5))
        back_x = cx - int(round(slide * 1.5))
        # Front leg bent (foot on ground, knee forward).
        _line(draw, cx, hip_y, front_x, FLOOR_Y)
        # Back leg straight and extended behind (the slide).
        _line(draw, cx, hip_y, back_x, FLOOR_Y)
        # Toe tip of back foot on ground.
        _px(draw, back_x, FLOOR_Y)

        # Body leans slightly in slide direction.
        lean = int(round(slide * 0.5))

        # Arms swing opposite to legs (smooth).
        _line(draw, cx - 1 + lean, shoulder_y, cx - 2 - int(round(slide)), shoulder_y + 1)
        _line(draw, cx + 1 + lean, shoulder_y, cx + 2 + int(round(slide)), shoulder_y + 1)

    # === SPARKLES on high energy ===
    if energy > 0.5:
        num = int((energy - 0.3) * 6)
        for i in range(num):
            angle = t * 3.5 + i * (math.pi * 2 / max(num, 1))
            dist = 3.5 + math.sin(t * 2 + i) * 1.5
            sx = cx + int(round(math.cos(angle) * dist))
            sy = 3 + int(round(math.sin(angle) * dist * 0.4))
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                _px(draw, sx, sy, "#FFFF44")

    if not draw:
        draw.append({"dp": [0, 0, "#000000"]})

    return draw
