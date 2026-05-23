import numpy as np


class BarMeter:
    """FFT magnitude binned into N log-spaced frequency bars, low→high left→right."""

    def __init__(self, samplerate: int = 44100, smoothing: float = 0.6):
        self.samplerate = samplerate
        self.smoothing = smoothing
        self._prev_heights: np.ndarray | None = None

    def render(self, audio_frame: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
        h, w = shape
        n = len(audio_frame)
        if n < 4:
            return np.zeros((h, w, 3), dtype=np.uint8)

        windowed = audio_frame * np.hanning(n)
        spec = np.abs(np.fft.rfft(windowed))
        # log-spaced bin edges from 40 Hz to nyquist
        nyquist = self.samplerate / 2
        edges = np.logspace(np.log10(40), np.log10(nyquist), w + 1)
        bin_idx = (edges / nyquist * len(spec)).astype(int).clip(0, len(spec) - 1)

        heights = np.zeros(w, dtype=np.float32)
        for i in range(w):
            lo, hi = bin_idx[i], max(bin_idx[i] + 1, bin_idx[i + 1])
            heights[i] = spec[lo:hi].mean() if hi > lo else 0.0

        # log-compress, normalize to ~[0,1]
        heights = np.log1p(heights * 50) / 5.0
        heights = np.clip(heights, 0, 1)

        if self._prev_heights is not None:
            heights = self.smoothing * self._prev_heights + (1 - self.smoothing) * heights
        self._prev_heights = heights

        frame = np.zeros((h, w, 3), dtype=np.uint8)
        rows_lit = (heights * h).astype(int)
        for x in range(w):
            top = h - rows_lit[x]
            # color gradient: blue (bottom) → magenta (top)
            for y in range(top, h):
                t = (h - y) / h  # 0 at bottom, 1 at top
                r = int(60 + 195 * t)
                g = int(20 + 60 * (1 - t))
                b = int(255 - 100 * t)
                frame[y, x] = (r, g, b)
        return frame
