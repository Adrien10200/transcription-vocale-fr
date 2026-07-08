#!/usr/bin/env python3
"""
Cœur de transcription partagé (CLI + interface graphique).

Regroupe la configuration de l'environnement (ffmpeg, cache modèles) et la
logique de transcription faster-whisper réglée pour la MEILLEURE précision
possible en français sur CPU.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


# --------------------------------------------------------------------------- #
# Racine du projet — fonctionne aussi bien lancé en script qu'empaqueté (exe).
# --------------------------------------------------------------------------- #
def _app_root() -> Path:
    if getattr(sys, "frozen", False):  # exécutable PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = _app_root()


def _resource_root() -> Path:
    """Dossier des ressources embarquées (ffmpeg) selon le mode d'exécution."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
    return APP_ROOT


RESOURCE_ROOT = _resource_root()


# --------------------------------------------------------------------------- #
# ffmpeg portable : cherché d'abord dans les ressources embarquées, puis à côté.
# --------------------------------------------------------------------------- #
def _configure_ffmpeg() -> None:
    candidates = [
        RESOURCE_ROOT / "tools" / "ffmpeg" / "bin",
        APP_ROOT / "tools" / "ffmpeg" / "bin",
    ]
    for bin_dir in candidates:
        if (bin_dir / "ffmpeg.exe").exists() or (bin_dir / "ffmpeg").exists():
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            return


_configure_ffmpeg()


# --------------------------------------------------------------------------- #
# Cache local des modèles (toujours à côté de l'app, pas dans %USERPROFILE%).
# --------------------------------------------------------------------------- #
MODEL_CACHE = APP_ROOT / "models"
MODEL_CACHE.mkdir(exist_ok=True)
os.environ.setdefault("HF_HOME", str(MODEL_CACHE))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(MODEL_CACHE))


MEDIA_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".3gp", ".amr",
}


def is_media_file(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTS


def format_timestamp(seconds: float) -> str:
    """Formate un temps (s) vers HH:MM:SS,mmm (format SRT)."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000.0))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


@dataclass
class TranscriptionOptions:
    model_name: str = "large-v3"
    language: str | None = "fr"          # None => détection automatique
    compute_type: str = "int8"
    beam_size: int = 8
    cpu_threads: int = 0                 # 0 => auto
    initial_prompt: str | None = None
    make_srt: bool = False


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0
    duration: float = 0.0
    elapsed: float = 0.0
    srt: str = ""


class Transcriber:
    """Encapsule le modèle Whisper. Chargez-le une fois, réutilisez-le."""

    def __init__(self) -> None:
        self._model = None
        self._loaded_key: tuple | None = None

    @staticmethod
    def _resolve_threads(threads: int) -> int:
        return threads if threads and threads > 0 else (os.cpu_count() or 4)

    def load(
        self,
        options: TranscriptionOptions,
        log: Callable[[str], None] | None = None,
    ) -> None:
        """Charge (ou recharge) le modèle si nécessaire."""
        from faster_whisper import WhisperModel

        threads = self._resolve_threads(options.cpu_threads)
        key = (options.model_name, options.compute_type, threads)
        if self._model is not None and key == self._loaded_key:
            return

        if log:
            log(f"Chargement du modèle « {options.model_name} » "
                f"(compute={options.compute_type}, threads={threads})…")
            log("Au premier lancement, le modèle est téléchargé (~3 Go). "
                "Cela peut prendre plusieurs minutes.")

        t0 = time.time()
        self._model = WhisperModel(
            options.model_name,
            device="cpu",
            compute_type=options.compute_type,
            cpu_threads=threads,
            download_root=str(MODEL_CACHE),
        )
        self._loaded_key = key
        if log:
            log(f"Modèle prêt en {time.time() - t0:.1f}s.")

    def transcribe(
        self,
        audio_path: str | os.PathLike,
        options: TranscriptionOptions,
        log: Callable[[str], None] | None = None,
        on_segment: Callable[[Segment], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> TranscriptionResult:
        """Transcrit un fichier. Peut être interrompu via `cancel()`."""
        if self._model is None:
            self.load(options, log=log)
        assert self._model is not None

        audio_path = str(audio_path)
        t0 = time.time()

        segments_gen, info = self._model.transcribe(
            audio_path,
            language=options.language,
            task="transcribe",
            beam_size=options.beam_size,
            best_of=options.beam_size,
            patience=1.0,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=True,
            initial_prompt=options.initial_prompt,
            word_timestamps=options.make_srt,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=400),
            prepend_punctuations="\"'“¿([{-",
            append_punctuations="\"'.。,，!！?？:：”)]}、",
        )

        if log:
            log(f"Langue : {info.language} (prob. {info.language_probability:.2f}) "
                f"— durée {info.duration:.1f}s")

        segments: list[Segment] = []
        srt_chunks: list[str] = []

        for i, seg in enumerate(segments_gen, start=1):
            if cancel and cancel():
                raise TranscriptionCancelled()
            clean = seg.text.strip()
            s = Segment(index=i, start=seg.start, end=seg.end, text=clean)
            segments.append(s)
            if on_segment:
                on_segment(s)
            if options.make_srt:
                srt_chunks.append(
                    f"{i}\n{format_timestamp(seg.start)} --> "
                    f"{format_timestamp(seg.end)}\n{clean}\n"
                )

        full_text = " ".join(s.text for s in segments if s.text)
        full_text = " ".join(full_text.split()).strip()

        return TranscriptionResult(
            text=full_text,
            segments=segments,
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            elapsed=time.time() - t0,
            srt="\n".join(srt_chunks).strip(),
        )


class TranscriptionCancelled(Exception):
    """Levée lorsque l'utilisateur annule une transcription en cours."""


def collect_inputs(target: str | os.PathLike) -> list[Path]:
    """Retourne la liste des fichiers média pour un fichier OU un dossier."""
    p = Path(target)
    if p.is_dir():
        return sorted(
            f for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in MEDIA_EXTS
        )
    if p.is_file():
        return [p]
    return []
