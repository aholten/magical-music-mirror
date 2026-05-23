import numpy as np
import sounddevice as sd


class AudioCapture:
    """Continuous ring buffer of the last `history` audio samples.

    The PortAudio callback writes one fresh chunk at the end of the buffer
    each time it fires (~chunk/samplerate seconds apart). Render code calls
    `latest()` at video framerate; multiple render frames between audio
    callbacks see the same buffer state — that's intentional and correct.
    Without the ring buffer the visualizer would re-incorporate the same
    chunk multiple times per audio frame and create periodic spectral
    artifacts at multiples of samplerate/chunk Hz.
    """

    def __init__(
        self,
        device: str | int | None,
        samplerate: int = 44100,
        chunk: int = 1024,
        history: int = 8192,
    ):
        self.chunk = chunk
        self.samplerate = samplerate
        self.history = history
        self._buf = np.zeros(history, dtype=np.float32)
        self._stream = sd.InputStream(
            device=device,
            channels=1,
            samplerate=samplerate,
            blocksize=chunk,
            dtype="float32",
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        # Atomic-from-the-reader's-perspective swap: build a new buffer,
        # then rebind self._buf in one step. latest() sees either the old
        # or the new buf, never a partial roll.
        n = min(frames, self.history)
        new_buf = np.roll(self._buf, -n)
        new_buf[-n:] = indata[:n, 0]
        self._buf = new_buf

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()

    def latest(self) -> np.ndarray:
        return self._buf
