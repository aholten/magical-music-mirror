import numpy as np
import sounddevice as sd


class AudioCapture:
    def __init__(self, device: str | int | None, samplerate: int = 44100, chunk: int = 1024):
        self.chunk = chunk
        self.samplerate = samplerate
        self._buf = np.zeros(chunk, dtype=np.float32)
        self._stream = sd.InputStream(
            device=device,
            channels=1,
            samplerate=samplerate,
            blocksize=chunk,
            dtype="float32",
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        self._buf = indata[:, 0].copy()

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()

    def latest(self) -> np.ndarray:
        return self._buf
