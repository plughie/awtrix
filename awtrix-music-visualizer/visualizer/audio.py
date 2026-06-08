"""Audio capture and FFT band analysis.

Capture uses the `soundcard` library, which supports WASAPI loopback on
Windows (recording the system's speaker output). When device is set to "auto"
(or left empty), the capture automatically follows the Windows default output
device — if you switch from speakers to headset, the visualizer follows.
"""

from __future__ import annotations

import queue
import threading
import time

import numpy as np
import soundcard as sc

from .config import AudioConfig, RenderConfig


class BandAnalyzer:
    """Maps an FFT magnitude spectrum into log-spaced frequency bands."""

    # FFT size is independent of capture blocksize for low-latency + high
    # frequency resolution. We accumulate samples in a ring buffer.
    FFT_SIZE = 4096

    def __init__(self, audio_cfg: AudioConfig, render_cfg: RenderConfig):
        self.samplerate = audio_cfg.samplerate
        self.blocksize = audio_cfg.blocksize
        self.bands = render_cfg.bands
        self.gain = render_cfg.gain
        self.smoothing = float(np.clip(render_cfg.smoothing, 0.0, 0.99))

        fft_size = self.FFT_SIZE

        # Precompute the FFT bin edges for each band (log-spaced).
        freqs = np.fft.rfftfreq(fft_size, d=1.0 / self.samplerate)
        edges = np.logspace(
            np.log10(max(render_cfg.min_freq, 1.0)),
            np.log10(min(render_cfg.max_freq, self.samplerate / 2)),
            self.bands + 1,
        )
        self._bin_indices = [
            np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
            for i in range(self.bands)
        ]
        self._window = np.hanning(fft_size)
        self._smoothed = np.zeros(self.bands, dtype=np.float32)

        # Ring buffer for accumulating samples.
        self._buffer = np.zeros(fft_size, dtype=np.float32)
        self._buffer_primed = False

        # Per-band frequency weighting: boost higher bands to compensate for
        # the natural 1/f energy rolloff in music (pink noise compensation).
        centers = np.sqrt(edges[:-1] * edges[1:])  # geometric mean
        self._weights = (centers / centers[0]) ** 0.5  # sqrt for gentle curve
        self._weights = self._weights.astype(np.float32)

        # Rolling peak for normalization (adapts over time instead of per-frame).
        self._rolling_peak = 0.01

    def process(self, samples: np.ndarray) -> np.ndarray:
        """Return an array of `bands` values in 0..1."""
        if samples.ndim > 1:
            samples = samples.mean(axis=1)  # downmix to mono

        # On the first block, tile it to fill the entire buffer so the FFT
        # doesn't start from silence. This eliminates the startup delay.
        n = len(samples)
        if not self._buffer_primed:
            self._buffer_primed = True
            repeats = (self.FFT_SIZE // max(n, 1)) + 1
            self._buffer[:] = np.tile(samples, repeats)[: self.FFT_SIZE]
        elif n >= self.FFT_SIZE:
            self._buffer[:] = samples[-self.FFT_SIZE:]
        else:
            self._buffer[:-n] = self._buffer[n:]
            self._buffer[-n:] = samples

        spectrum = np.abs(np.fft.rfft(self._buffer * self._window))

        raw = np.empty(self.bands, dtype=np.float32)
        for i, idx in enumerate(self._bin_indices):
            raw[i] = spectrum[idx].mean() if idx.size else 0.0

        # Apply per-band frequency weighting (boost highs).
        raw *= self._weights

        # Log compression for perceptual scaling.
        raw = np.log1p(raw)

        # Rolling peak normalization: adapts over ~1-2 seconds instead of
        # resetting every frame (which crushes quiet bands).
        frame_peak = raw.max()
        if self._rolling_peak < 0.02:
            # First meaningful frame: seed the peak immediately.
            self._rolling_peak = max(frame_peak, 0.01)
        else:
            self._rolling_peak = max(
                frame_peak, self._rolling_peak * 0.97  # ~1.5s decay at 20fps
            )
        if self._rolling_peak > 1e-6:
            raw = raw / self._rolling_peak

        raw = np.clip(raw * self.gain, 0.0, 1.0)

        # Envelope follower: instant attack when rising, smooth release when
        # falling (a = release factor; higher = slower decay).
        a = self.smoothing
        rising = raw > self._smoothed
        self._smoothed = np.where(
            rising, raw, self._smoothed * a + raw * (1.0 - a)
        ).astype(np.float32)
        return self._smoothed.copy()


def _is_auto(device_str: str) -> bool:
    return device_str.strip().lower() in ("", "auto")


def _get_loopback_mic(speaker):
    """Get the loopback microphone for a given speaker."""
    return sc.get_microphone(speaker.name, include_loopback=True)


def _resolve_fixed_mic(cfg: AudioConfig):
    """Resolve a specific (non-auto) device."""
    target = cfg.device.strip().lower()

    if cfg.loopback:
        speakers = sc.all_speakers()
        chosen = next((s for s in speakers if target in s.name.lower()), None)
        if chosen is None:
            names = "\n  ".join(s.name for s in speakers)
            raise RuntimeError(
                f"No speaker matched '{cfg.device}'.\n"
                f"Available speakers:\n  {names}"
            )
        return _get_loopback_mic(chosen)

    mics = sc.all_microphones()
    mic = next((m for m in mics if target in m.name.lower()), None)
    if mic is None:
        names = "\n  ".join(m.name for m in mics)
        raise RuntimeError(
            f"No microphone matched '{cfg.device}'.\n"
            f"Available microphones:\n  {names}"
        )
    return mic


class AudioStream:
    """Captures audio on a background thread, following the active output device.

    When device is "auto" (or empty) and loopback is true, the stream
    periodically checks if the Windows default speaker changed and reopens
    the loopback capture on the new device automatically.
    """

    # How often to check for device changes (seconds).
    _DEVICE_POLL_INTERVAL = 2.0

    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._error: Exception | None = None
        self._auto = _is_auto(cfg.device) and cfg.loopback
        self._current_device_name: str = ""

    @property
    def device_name(self) -> str:
        return self._current_device_name or "(not started)"

    def _get_current_mic(self):
        """Return the mic to capture from right now."""
        if self._auto:
            spk = sc.default_speaker()
            self._current_device_name = spk.name
            return _get_loopback_mic(spk)
        else:
            mic = _resolve_fixed_mic(self.cfg)
            self._current_device_name = mic.name
            return mic

    def _run(self):
        try:
            while not self._stop.is_set():
                mic = self._get_current_mic()
                try:
                    with mic.recorder(
                        samplerate=self.cfg.samplerate,
                        blocksize=self.cfg.blocksize,
                    ) as recorder:
                        last_check = time.monotonic()
                        while not self._stop.is_set():
                            data = recorder.record(numframes=self.cfg.blocksize)
                            try:
                                self._queue.put_nowait(data)
                            except queue.Full:
                                try:
                                    self._queue.get_nowait()
                                    self._queue.put_nowait(data)
                                except queue.Empty:
                                    pass

                            # Periodically check if the default device changed.
                            if self._auto:
                                now = time.monotonic()
                                if now - last_check >= self._DEVICE_POLL_INTERVAL:
                                    last_check = now
                                    current_default = sc.default_speaker().name
                                    if current_default != self._current_device_name:
                                        # Device changed — break out to reconnect.
                                        break
                except Exception:
                    # If a device disappears mid-capture (e.g. USB headset
                    # unplugged), wait briefly and retry with the new default.
                    if self._stop.is_set():
                        return
                    time.sleep(0.5)
        except Exception as exc:
            self._error = exc

    def __enter__(self) -> "AudioStream":
        self._stop.clear()
        # Resolve once now so device_name is available immediately.
        try:
            mic = self._get_current_mic()
            _ = mic  # just sets _current_device_name
        except Exception:
            pass
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def read(self, timeout: float = 1.0) -> np.ndarray | None:
        if self._error is not None:
            raise self._error
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


def list_devices() -> str:
    """Return a formatted listing of available speakers and microphones."""
    default_spk = sc.default_speaker()
    lines = ["=== Speakers (use one of these for loopback capture) ==="]
    for spk in sc.all_speakers():
        marker = " <-- default" if spk.name == default_spk.name else ""
        lines.append(f"  {spk.name}{marker}")
    lines.append("")
    lines.append("=== Microphones (loopback = false) ===")
    for mic in sc.all_microphones(include_loopback=True):
        tag = " [loopback]" if getattr(mic, "isloopback", False) else ""
        lines.append(f"  {mic.name}{tag}")
    lines.append("")
    lines.append('Tip: set device = "auto" to follow the active output device.')
    return "\n".join(lines)
