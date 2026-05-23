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
        fft_size: int = 8192,
    ):
        self.samplerate = samplerate
        self.smoothing = smoothing
        self.bars = bars
        self.gap = gap
        self.fft_size = fft_size
        self._prev_heights: np.ndarray | None = None

    def render(self, audio_frame: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
        h, w = shape
        if len(audio_frame) < 4:
            return np.zeros((h, w, 3), dtype=np.uint8)

        # Take the most recent fft_size samples from the capture's ring
        # buffer. AudioCapture owns the rolling history; we just slice.
        if len(audio_frame) >= self.fft_size:
            samples = audio_frame[-self.fft_size:]
        else:
            samples = np.concatenate(
                [np.zeros(self.fft_size - len(audio_frame), dtype=np.float32), audio_frame]
            )

        windowed = samples * np.hanning(self.fft_size)
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
        # column slot, leaving `gap` empty grid columns between slots. Color
        # matches the Conway alive-cell color in the compositor so bars look
        # like stacks of the same "stuff" Conway is made of.
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        slot = max(1, w // self.bars)
        bar_w = max(1, slot - self.gap)
        rows_lit = (heights * h).astype(int)
        for i in range(self.bars):
            x0 = i * slot
            x1 = min(x0 + bar_w, w)
            top = h - rows_lit[i]
            frame[top:h, x0:x1] = (0, 110, 70)
        return frame
