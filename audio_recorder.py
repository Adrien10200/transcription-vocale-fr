"""Enregistrement micro pour le mode « Enregistrer puis transcrire ».

Capture le microphone en 16 kHz mono (format natif de Whisper) dans un thread,
et écrit un fichier WAV temporaire à l'arrêt.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from PySide6.QtCore import QObject, Signal


SAMPLE_RATE = 16000


def list_input_devices() -> list[tuple[int, str]]:
    """Retourne [(index, nom), …] des périphériques d'entrée disponibles."""
    try:
        import sounddevice as sd
    except Exception:  # noqa: BLE001
        return []
    devices = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                devices.append((i, d.get("name", f"Device {i}")))
    except Exception:  # noqa: BLE001
        return []
    return devices


def has_microphone() -> bool:
    return len(list_input_devices()) > 0


class MicRecorder(QObject):
    """Enregistre le micro dans un thread. Émet le niveau audio en direct et,
    à l'arrêt, le chemin du fichier WAV écrit."""

    level = Signal(float)          # niveau RMS courant (0..1) pour un indicateur
    finished = Signal(str)         # chemin du WAV
    failed = Signal(str)
    done = Signal()

    def __init__(self, device: int | None = None) -> None:
        super().__init__()
        self._device = device
        self._stop = False
        self._frames: list = []

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            block = int(SAMPLE_RATE * 0.1)
            self._frames = []
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype="int16", blocksize=block,
                                device=self._device) as stream:
                while not self._stop:
                    data, _ = stream.read(block)
                    mono = data[:, 0] if data.ndim > 1 else data
                    self._frames.append(mono.copy())
                    # Niveau pour l'indicateur visuel.
                    rms = float(np.sqrt(np.mean((mono.astype(np.float32) / 32768.0) ** 2)))
                    self.level.emit(min(1.0, rms * 4.0))

            # Écrit le WAV temporaire.
            audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype="int16")
            fd, tmp = tempfile.mkstemp(suffix="_rec.wav")
            import os
            os.close(fd)
            with wave.open(tmp, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)          # int16
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio.tobytes())
            self.finished.emit(tmp)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()
