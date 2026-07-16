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


def has_desktop_audio() -> bool:
    """Vrai si la capture du son du bureau (loopback WASAPI) est possible."""
    try:
        import soundcard as sc
        return sc.default_speaker() is not None
    except Exception:  # noqa: BLE001
        return False


class MicRecorder(QObject):
    """Enregistre le micro dans un thread. Émet le niveau audio en direct et,
    à l'arrêt, le chemin du fichier WAV écrit."""

    level = Signal(float)          # niveau RMS courant (0..1) pour un indicateur
    finished = Signal(str)         # chemin du WAV
    failed = Signal(str)
    done = Signal()

    def __init__(self, device=None) -> None:
        super().__init__()
        # device : int (micro), None (micro par défaut) ou "loopback" (son du bureau)
        self._device = device
        self._stop = False
        self._frames: list = []

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            import numpy as np
            if self._device == "loopback":
                self._record_loopback(np)
            else:
                self._record_mic(np)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()

    def _write_wav_int16(self, audio) -> str:
        import os
        fd, tmp = tempfile.mkstemp(suffix="_rec.wav")
        os.close(fd)
        with wave.open(tmp, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)          # int16
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return tmp

    def _record_mic(self, np) -> None:
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
                rms = float(np.sqrt(np.mean((mono.astype(np.float32) / 32768.0) ** 2)))
                self.level.emit(min(1.0, rms * 4.0))
        audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype="int16")
        self.finished.emit(self._write_wav_int16(audio))

    def _record_loopback(self, np) -> None:
        """Capture le son du bureau (sortie système) via WASAPI loopback."""
        import soundcard as sc
        block = int(SAMPLE_RATE * 0.1)
        self._frames = []
        speaker = sc.default_speaker()
        mic = sc.get_microphone(speaker.name, include_loopback=True)
        with mic.recorder(samplerate=SAMPLE_RATE, channels=1) as rec:
            while not self._stop:
                data = rec.record(numframes=block)       # float32 [-1, 1], mono
                mono = data[:, 0] if data.ndim > 1 else data
                rms = float(np.sqrt(np.mean(mono ** 2))) if len(mono) else 0.0
                self.level.emit(min(1.0, rms * 4.0))
                # Convertit en int16 pour le WAV.
                self._frames.append((np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16))
        audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype="int16")
        self.finished.emit(self._write_wav_int16(audio))
