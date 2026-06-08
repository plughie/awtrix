"""Turn frequency bands into AWTRIX custom-app JSON payloads.

The TC001 matrix is 32 pixels wide and 8 pixels tall.
"""

from __future__ import annotations

import colorsys
import time

import numpy as np

from .config import RenderConfig
from .dancer import render_dancer
from .fractals import render_julia, render_plasma
from .mario import render_mario, render_mario_underground
from .waves import render_waves

WIDTH = 32
HEIGHT = 8


def _hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    """Linearly interpolate between two RGB tuples."""
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return _hex(r, g, b)


def _gradient(stops: list[tuple[int, int, int]], t: float) -> str:
    """Multi-stop gradient. t in 0..1 maps across all stops evenly."""
    t = max(0.0, min(1.0, t))
    n = len(stops) - 1
    idx = min(int(t * n), n - 1)
    local_t = (t * n) - idx
    return _lerp_color(stops[idx], stops[idx + 1], local_t)


# --- Color schemes ---
# Each takes (index, level, num_bands) and returns a hex color string.

def _scheme_spectrum(index: float, level: float, num_bands: int) -> str:
    hue = (1.0 - index / max(1, num_bands - 1)) * 0.66
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return _hex(int(r * 255), int(g * 255), int(b * 255))


def _scheme_fire(index: float, level: float, num_bands: int) -> str:
    r, g, b = colorsys.hsv_to_rgb(0.12 * level, 1.0, min(1.0, 0.3 + level))
    return _hex(int(r * 255), int(g * 255), int(b * 255))


def _scheme_outrun(index: float, level: float, num_bands: int) -> str:
    stops = [(0, 0, 180), (80, 0, 255), (180, 0, 255), (255, 0, 180), (255, 0, 100)]
    return _gradient(stops, index / max(1, num_bands - 1))


def _scheme_ocean(index: float, level: float, num_bands: int) -> str:
    stops = [(0, 20, 80), (0, 80, 130), (0, 180, 200), (0, 255, 220), (150, 255, 255)]
    return _gradient(stops, index / max(1, num_bands - 1))


def _scheme_forest(index: float, level: float, num_bands: int) -> str:
    stops = [(0, 60, 20), (0, 140, 50), (30, 200, 60), (120, 230, 30), (200, 255, 0)]
    return _gradient(stops, index / max(1, num_bands - 1))


def _scheme_ice(index: float, level: float, num_bands: int) -> str:
    stops = [(220, 240, 255), (100, 180, 255), (30, 80, 220), (10, 20, 140)]
    return _gradient(stops, 1.0 - level)


def _scheme_neon(index: float, level: float, num_bands: int) -> str:
    t = index / max(1, num_bands - 1)
    stops = [(255, 0, 200), (0, 255, 255), (255, 0, 200), (0, 255, 255)]
    return _gradient(stops, t)


def _scheme_sunset(index: float, level: float, num_bands: int) -> str:
    stops = [(255, 220, 0), (255, 140, 0), (255, 50, 0), (180, 0, 80), (100, 0, 150)]
    return _gradient(stops, index / max(1, num_bands - 1))


def _scheme_matrix(index: float, level: float, num_bands: int) -> str:
    """Matrix: dark to bright green based on amplitude."""
    g = int(40 + level * 215)
    return _hex(0, g, 0)


SCHEMES: dict[str, callable] = {
    "spectrum": _scheme_spectrum,
    "fire": _scheme_fire,
    "outrun": _scheme_outrun,
    "ocean": _scheme_ocean,
    "forest": _scheme_forest,
    "ice": _scheme_ice,
    "neon": _scheme_neon,
    "sunset": _scheme_sunset,
    "matrix": _scheme_matrix,
}


class Renderer:
    def __init__(self, cfg: RenderConfig):
        self.cfg = cfg
        self.bands = cfg.bands
        self._peaks = np.zeros(self.bands, dtype=np.float32)
        # Width in pixels allotted to each band (draw mode).
        self._col_w = max(1, WIDTH // self.bands)
        self._start_time = time.monotonic()

    def _band_color(self, index: int | float, level: float) -> str:
        scheme = self.cfg.scheme
        if scheme == "solid":
            return self.cfg.solid_color
        fn = SCHEMES.get(scheme, _scheme_spectrum)

        if self.cfg.color_cycle:
            elapsed = time.monotonic() - self._start_time
            speed = self.cfg.color_cycle_speed
            phase = (elapsed * speed * 0.1 * self.bands) % self.bands
            shifted_index = (index + phase) % self.bands
            return fn(shifted_index, level, self.bands)

        return fn(index, level, self.bands)

    def render(self, bands: np.ndarray) -> dict:
        """Build an AWTRIX custom-app payload for the given band levels."""
        if self.cfg.mode == "bar":
            return self._render_bar(bands)
        if self.cfg.mode == "horizontal":
            return self._render_horizontal(bands)
        if self.cfg.mode == "ltr":
            return self._render_ltr(bands)
        if self.cfg.mode == "fractal":
            return self._render_fractal(bands)
        if self.cfg.mode == "dancer":
            return self._render_dancer(bands)
        if self.cfg.mode == "waves":
            return self._render_waves(bands)
        if self.cfg.mode == "mario":
            return self._render_mario(bands)
        if self.cfg.mode == "mario_underground":
            return self._render_mario_underground(bands)
        return self._render_draw(bands)

    def _render_bar(self, bands: np.ndarray) -> dict:
        # AWTRIX bar graph: up to 16 ints, autoscaled. Color is a single value.
        vals = [int(round(v * 100)) for v in bands[:16]]
        color = self.cfg.solid_color if self.cfg.scheme == "solid" else "#00FFAA"
        return {"bar": vals, "color": color, "autoscale": False, "duration": 9999}

    def _render_draw(self, bands: np.ndarray) -> dict:
        # Decay peak markers slowly.
        self._peaks = np.maximum(self._peaks - 0.04, 0.0)
        self._peaks = np.maximum(self._peaks, bands)

        draw: list[dict] = []
        for i in range(self.bands):
            level = float(np.clip(bands[i], 0.0, 1.0))
            h = int(round(level * HEIGHT))
            x = i * self._col_w
            # Keep bars within the matrix width.
            if x >= WIDTH:
                break
            w = min(self._col_w, WIDTH - x) - (1 if self._col_w > 1 else 0)
            w = max(1, w)

            if h > 0:
                color = self._band_color(i, level)
                # df: [x, y, w, h, color]; y is the top of the rectangle.
                draw.append({"df": [x, HEIGHT - h, w, h, color]})

            if self.cfg.peak_dots:
                peak_h = int(round(float(self._peaks[i]) * HEIGHT))
                if peak_h > 0:
                    py = HEIGHT - peak_h
                    draw.append({"dl": [x, py, x + w - 1, py, "#FFFFFF"]})

        # Overlay text knocked out of the spectrum (drawn on top in black).
        if self.cfg.overlay_text:
            # Center the text horizontally. AWTRIX font is ~5px wide per char.
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2  # push text down one pixel for better vertical centering
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        # An empty draw list would leave the previous frame; send a clearing pixel.
        if not draw:
            draw.append({"dp": [0, 0, "#000000"]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_fractal(self, bands: np.ndarray) -> dict:
        """Audio-reactive fractal/procedural pattern."""
        fractal_type = getattr(self.cfg, "fractal_type", "plasma")
        scheme = self.cfg.scheme if self.cfg.scheme != "solid" else "spectrum"

        if fractal_type == "julia":
            draw = render_julia(bands, scheme)
        else:
            draw = render_plasma(bands, scheme)

        # Overlay text on top.
        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_dancer(self, bands: np.ndarray) -> dict:
        """Dancing stick figure on a black background."""
        scheme = self.cfg.scheme if self.cfg.scheme != "solid" else "spectrum"
        draw = render_dancer(bands, scheme)

        # Overlay text on top.
        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_waves(self, bands: np.ndarray) -> dict:
        """Joy Division / Unknown Pleasures waveform landscape."""
        scheme = self.cfg.scheme if self.cfg.scheme != "solid" else "spectrum"
        draw = render_waves(bands, scheme)

        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_mario(self, bands: np.ndarray) -> dict:
        """Super Mario overworld themed spectrum."""
        draw = render_mario(bands, self.cfg.scheme)

        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_mario_underground(self, bands: np.ndarray) -> dict:
        """Super Mario underground themed spectrum."""
        draw = render_mario_underground(bands, self.cfg.scheme)

        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_horizontal(self, bands: np.ndarray) -> dict:
        """Horizontal bars growing outward from the center, one row per band.

        Uses up to 8 bands (one per pixel row). Each bar is mirrored:
        it extends left and right from the center column (x=15/16).
        """
        # Decay peak markers slowly.
        self._peaks = np.maximum(self._peaks - 0.04, 0.0)
        self._peaks = np.maximum(self._peaks, bands)

        draw: list[dict] = []
        center = WIDTH // 2  # 16
        max_half = center  # max extension in each direction (16px)

        # Use up to HEIGHT bands (8 rows); average if more bands configured.
        num_rows = min(self.bands, HEIGHT)
        row_h = max(1, HEIGHT // num_rows)

        for row in range(num_rows):
            # Map row to a band index (or average a range if bands > rows).
            if self.bands <= HEIGHT:
                level = float(np.clip(bands[row], 0.0, 1.0))
                band_idx = row
            else:
                # Average multiple bands into this row.
                lo = row * self.bands // num_rows
                hi = (row + 1) * self.bands // num_rows
                level = float(np.clip(np.mean(bands[lo:hi]), 0.0, 1.0))
                band_idx = (lo + hi) // 2

            half_w = int(round(level * max_half))
            y = row * row_h

            if half_w > 0:
                color = self._band_color(band_idx, level)
                # Left bar: grows from center to the left.
                lx = center - half_w
                draw.append({"df": [lx, y, half_w, row_h, color]})
                # Right bar: grows from center to the right.
                draw.append({"df": [center, y, half_w, row_h, color]})

            # Peak dots as vertical lines at the peak extent.
            if self.cfg.peak_dots:
                peak_level = float(self._peaks[band_idx] if self.bands <= HEIGHT
                                   else np.mean(self._peaks[
                                       row * self.bands // num_rows:
                                       (row + 1) * self.bands // num_rows]))
                peak_half = int(round(float(np.clip(peak_level, 0, 1)) * max_half))
                if peak_half > 0:
                    # Left peak dot.
                    px_l = center - peak_half
                    draw.append({"dl": [px_l, y, px_l, y + row_h - 1, "#FFFFFF"]})
                    # Right peak dot.
                    px_r = center + peak_half - 1
                    draw.append({"dl": [px_r, y, px_r, y + row_h - 1, "#FFFFFF"]})

        # Overlay text.
        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        if not draw:
            draw.append({"dp": [0, 0, "#000000"]})

        return {"draw": draw, "duration": 9999, "noScroll": True}

    def _render_ltr(self, bands: np.ndarray) -> dict:
        """Left-to-right horizontal bars, one row per band.

        Each band gets a row. The bar starts at x=0 and extends right
        proportional to the band level (0 = nothing, 1 = full width).
        Low bands at top, high bands at bottom.
        """
        self._peaks = np.maximum(self._peaks - 0.04, 0.0)
        self._peaks = np.maximum(self._peaks, bands)

        draw: list[dict] = []
        num_rows = min(self.bands, HEIGHT)
        row_h = max(1, HEIGHT // num_rows)

        for row in range(num_rows):
            if self.bands <= HEIGHT:
                level = float(np.clip(bands[row], 0.0, 1.0))
                band_idx = row
            else:
                lo = row * self.bands // num_rows
                hi = (row + 1) * self.bands // num_rows
                level = float(np.clip(np.mean(bands[lo:hi]), 0.0, 1.0))
                band_idx = (lo + hi) // 2

            bar_w = int(round(level * WIDTH))
            y = row * row_h

            if bar_w > 0:
                color = self._band_color(band_idx, level)
                draw.append({"df": [0, y, bar_w, row_h, color]})

            if self.cfg.peak_dots:
                peak_level = float(self._peaks[band_idx] if self.bands <= HEIGHT
                                   else np.mean(self._peaks[
                                       row * self.bands // num_rows:
                                       (row + 1) * self.bands // num_rows]))
                peak_w = int(round(float(np.clip(peak_level, 0, 1)) * WIDTH))
                if peak_w > 0:
                    px = min(peak_w, WIDTH - 1)
                    draw.append({"dl": [px, y, px, y + row_h - 1, "#FFFFFF"]})

        # Overlay text.
        if self.cfg.overlay_text:
            text_w = len(self.cfg.overlay_text) * 5
            tx = max(0, (WIDTH - text_w) // 2)
            ty = 2
            draw.append({"dt": [tx, ty, self.cfg.overlay_text, self.cfg.overlay_color]})

        if not draw:
            draw.append({"dp": [0, 0, "#000000"]})

        return {"draw": draw, "duration": 9999, "noScroll": True}
