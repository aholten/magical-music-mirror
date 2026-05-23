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
        attack: float = 0.0,
        release: float = 0.65,
        bars: int = 48,
        fft_size: int = 8192,
        centroid_smoothing: float = 0.30,
        centroid_treble_bias: float = 3.0,
    ):
        # Asymmetric smoothing: attack governs how much the previous height
        # influences a NEW MAX (going up); release governs the descent. 0.0
        # = instant snap up on transients. 0.65 = drop 35% of the gap per
        # frame on the way down (~27 ms half-life @60fps). This makes peaks
        # punch through immediately while the decay still reads smooth.
        self.samplerate = samplerate
        self.attack = attack
        self.release = release
        self.bars = bars
        self.fft_size = fft_size
        self._prev_heights: np.ndarray | None = None
        # Smoothed spectral centroid in [0, 1]: 0 = all energy in bass, 1 =
        # all energy in treble. Updated each render(); 0.5 when silent so
        # consumers (e.g. dynamic warp focal) see a neutral default. Lower
        # `centroid_smoothing` = snappier response (0.0 = raw, ~no smoothing).
        self.centroid: float = 0.5
        self._centroid_smoothing = centroid_smoothing
        # Treble bias counteracts the bass-dominated nature of raw FFT
        # magnitudes — without this, the centroid hugs the low end even
        # during treble-heavy material. Linear ramp: bin 0 weighted 1×,
        # bin (bars-1) weighted (1 + bias)×. bias=0 → unweighted centroid.
        self._centroid_weights = (
            1.0 + centroid_treble_bias * np.arange(bars, dtype=np.float32) / max(1, bars - 1)
        )

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
            going_up = heights > self._prev_heights
            up = self.attack * self._prev_heights + (1 - self.attack) * heights
            down = self.release * self._prev_heights + (1 - self.release) * heights
            heights = np.where(going_up, up, down)
        self._prev_heights = heights

        # Spectral centroid in normalized bar-index space [0, 1]. Pre-weight
        # heights with the treble-bias ramp so high-frequency bars actually
        # influence the result. Hold the previous value when silent so the
        # warp focal doesn't lurch back to center between songs.
        weighted = heights * self._centroid_weights
        total = float(weighted.sum())
        if total > 1e-6 and self.bars > 1:
            indices = np.arange(self.bars, dtype=np.float32)
            raw_centroid = float((weighted * indices).sum() / total / (self.bars - 1))
            self.centroid = (
                self._centroid_smoothing * self.centroid
                + (1 - self._centroid_smoothing) * raw_centroid
            )

        # Tile the full grid width with `bars` contiguous columns. Slot edges
        # are computed as `(i * w / bars)` floored — this absorbs the
        # remainder when w isn't a multiple of bars (e.g. 48 bars over 160
        # cols gives a mix of 3- and 4-pixel-wide bars) and leaves no blank
        # space at the right edge.
        #
        # Pixel values here are SENTINELS, not display colors — app.py
        # remaps everything via the fade-table lookup. R=1 marks the top
        # row of each bar (forced to age 0 by app.py so the leading edge
        # always shows the initial palette color), R=2 marks the body.
        # Conway underlay uses R=0 in compositor.py, so the channels stay
        # disjoint after compose.
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        slot_starts = (np.arange(self.bars + 1) * w / self.bars).astype(int)
        rows_lit = (heights * h).astype(int)
        for i in range(self.bars):
            x0 = slot_starts[i]
            x1 = slot_starts[i + 1]
            top = h - rows_lit[i]
            if rows_lit[i] <= 0:
                continue
            frame[top:h, x0:x1] = (2, 0, 0)
            frame[top, x0:x1] = (1, 0, 0)
        return frame
