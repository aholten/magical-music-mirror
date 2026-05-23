import numpy as np


class BarMeter:
    """FFT magnitude binned into N log-spaced frequency bars, low→high left→right.

    Renders ``bars`` distinct bars across the grid width. A rolling internal
    audio buffer (``fft_size`` samples) is FFT'd each frame so low-frequency
    bins have enough resolution to be distinct (a fresh 1024-sample chunk has
    only ~43 Hz resolution, which causes the lowest dozen log bins to collide
    onto the same FFT bin and appear as one wide block).
    """

    def __init__(
        self,
        samplerate: int = 44100,
        smoothing: float = 0.6,
        bars: int = 48,
        gap: int = 1,
        fft_size: int = 4096,
    ):
        self.samplerate = samplerate
        self.smoothing = smoothing
        self.bars = bars
        self.gap = gap
        self.fft_size = fft_size
        self._prev_heights: np.ndarray | None = None
        self._fft_buf = np.zeros(fft_size, dtype=np.float32)

    def render(self, audio_frame: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
        h, w = shape
        n = len(audio_frame)
        if n < 4:
            return np.zeros((h, w, 3), dtype=np.uint8)

        # Roll the new chunk into the FFT buffer so we always FFT fft_size samples.
        n = min(n, self.fft_size)
        self._fft_buf = np.roll(self._fft_buf, -n)
        self._fft_buf[-n:] = audio_frame[-n:]

        windowed = self._fft_buf * np.hanning(self.fft_size)
        spec = np.abs(np.fft.rfft(windowed))

        # log-spaced bin edges from 40 Hz to nyquist, across self.bars bands
        nyquist = self.samplerate / 2
        edges = np.logspace(np.log10(40), np.log10(nyquist), self.bars + 1)
        bin_idx = (edges / nyquist * (len(spec) - 1)).astype(int).clip(0, len(spec) - 1)

        heights = np.zeros(self.bars, dtype=np.float32)
        for i in range(self.bars):
            lo, hi = bin_idx[i], max(bin_idx[i] + 1, bin_idx[i + 1])
            heights[i] = spec[lo:hi].mean() if hi > lo else 0.0

        # log-compress, normalize to ~[0,1]
        heights = np.log1p(heights * 50) / 5.0
        heights = np.clip(heights, 0, 1)

        if self._prev_heights is not None:
            heights = self.smoothing * self._prev_heights + (1 - self.smoothing) * heights
        self._prev_heights = heights

        # Render bars-with-gaps across the grid width: each bar gets a uniform
        # column slot, leaving `gap` empty grid columns between slots.
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        slot = max(1, w // self.bars)
        bar_w = max(1, slot - self.gap)
        rows_lit = (heights * h).astype(int)
        for i in range(self.bars):
            x0 = i * slot
            x1 = min(x0 + bar_w, w)
            top = h - rows_lit[i]
            for y in range(top, h):
                t = (h - y) / h  # 0 at bottom, 1 at top
                r = int(60 + 195 * t)
                g = int(20 + 60 * (1 - t))
                b = int(255 - 100 * t)
                frame[y, x0:x1] = (r, g, b)
        return frame
