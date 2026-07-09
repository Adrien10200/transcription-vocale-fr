#!/usr/bin/env python3
"""
Cœur de transcription partagé (CLI + interface graphique).

Regroupe la configuration de l'environnement (ffmpeg, cache modèles) et la
logique de transcription faster-whisper réglée pour la MEILLEURE précision
possible en français sur CPU.
"""

from __future__ import annotations

import json
import os
import re
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
# Cache des modèles.
#
# IMPORTANT : le cache est stocké dans un dossier PERSISTANT propre à
# l'utilisateur (hors du dossier de l'application) afin qu'une mise à jour de
# l'app — qui remplace son dossier — NE force PAS un re-téléchargement du
# modèle (~3 Go). Sous Windows : %LOCALAPPDATA%\TranscriptionVocaleFR\models.
#
# Un dossier `models/` présent À CÔTÉ de l'application reste prioritaire s'il
# contient déjà un modèle (rétrocompatibilité, cache portable volontaire).
# --------------------------------------------------------------------------- #
_CACHE_DIR_NAME = "models"
_APP_DATA_FOLDER = "TranscriptionVocaleFR"


def _user_data_dir() -> Path:
    """Dossier de données persistant, propre à l'utilisateur et à l'OS."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / _APP_DATA_FOLDER
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DATA_FOLDER
    # Linux / autres
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / _APP_DATA_FOLDER
    return Path.home() / ".local" / "share" / _APP_DATA_FOLDER


def _has_model(folder: Path) -> bool:
    """Vrai si le dossier contient au moins un modèle Whisper téléchargé."""
    if not folder.is_dir():
        return False
    try:
        return any(folder.glob("models--*"))
    except OSError:
        return False


def _resolve_model_cache() -> Path:
    """Choisit l'emplacement du cache, en préservant un cache existant.

    Priorité :
      1. Cache portable à côté de l'app s'il contient DÉJÀ un modèle
         (respecte un choix volontaire / installation portable).
      2. Sinon, dossier persistant utilisateur (survit aux mises à jour).
    """
    app_local = APP_ROOT / _CACHE_DIR_NAME
    if _has_model(app_local):
        return app_local

    user_dir = _user_data_dir() / _CACHE_DIR_NAME
    try:
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    except OSError:
        # Repli ultime : à côté de l'app (mode portable).
        app_local.mkdir(parents=True, exist_ok=True)
        return app_local


MODEL_CACHE = _resolve_model_cache()

# faster-whisper / huggingface_hub utilisent ces variables pour le cache.
os.environ["HF_HOME"] = str(MODEL_CACHE)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(MODEL_CACHE)

# IMPORTANT : désactive les liens symboliques du cache HuggingFace.
# Par défaut, HF crée des symlinks snapshots/ -> blobs/ ; ces liens sont
# fragiles sous Windows (droits, copie, décompression, installeur) et peuvent
# « casser », ce qui pousse HF à re-télécharger le modèle. En désactivant les
# symlinks, les fichiers sont copiés directement : le cache est autonome et
# robuste (survit aux copies/mises à jour/installeur).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


# Taille minimale plausible du poids « model.bin » de large-v3 (~3 Go).
# Sert à distinguer un cache complet d'un cache partiel/corrompu.
_MIN_MODEL_BIN_BYTES = 500 * 1024 * 1024  # 500 Mo (marge large, medium ~1.5 Go)


def _model_is_cached(model_name: str) -> bool:
    """Vrai si le modèle demandé est réellement présent ET complet dans le cache.

    Robuste aux symlinks cassés : on vérifie qu'un fichier `model.bin`
    (fichier réel OU lien résolvable) d'une taille plausible existe dans un
    snapshot. On tolère aussi un `model.bin` directement présent (mode sans
    symlink) et on vérifie le blob correspondant si besoin.
    """
    repo = f"models--Systran--faster-whisper-{model_name}"
    repo_dir = MODEL_CACHE / repo
    if not repo_dir.is_dir():
        return False
    snapshots = repo_dir / "snapshots"
    if not snapshots.is_dir():
        return False

    for snap in snapshots.iterdir():
        if not snap.is_dir():
            continue
        model_bin = snap / "model.bin"
        try:
            # exists() suit les symlinks ; si le lien est cassé -> False.
            if not model_bin.exists():
                continue
            size = model_bin.stat().st_size  # suit le lien vers le blob réel
            # Certains liens rapportent 0 : on tente alors de résoudre la cible.
            if size == 0:
                target = model_bin.resolve()
                if target.exists():
                    size = target.stat().st_size
            if size >= _MIN_MODEL_BIN_BYTES:
                return True
        except OSError:
            continue
    return False


def enable_offline_if_cached(model_name: str) -> bool:
    """Active le mode 100 % hors-ligne de HuggingFace SI le modèle est déjà
    présent localement. Cela empêche tout appel réseau (donc tout
    re-téléchargement) au chargement d'un modèle déjà en cache.

    Retourne True si le mode hors-ligne a été activé.
    """
    if _model_is_cached(model_name):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        return True
    # Modèle absent : on retire un éventuel mode hors-ligne pour permettre
    # le premier téléchargement.
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    return False


# --------------------------------------------------------------------------- #
# Corrections de vocabulaire (dictionnaire personnalisé, persistant).
#
# L'utilisateur peut définir des remplacements du type « Volio » -> « Voelio ».
# Après chaque transcription, ces remplacements sont appliqués au texte final.
# Le fichier est stocké dans le dossier de données utilisateur (persistant,
# survit aux redémarrages ET aux mises à jour de l'application).
# --------------------------------------------------------------------------- #
def _corrections_file() -> Path:
    """Chemin du fichier de corrections. Réutilise un fichier présent à côté de
    l'app (mode portable) sinon le dossier utilisateur persistant."""
    app_local = APP_ROOT / "corrections.json"
    if app_local.is_file():
        return app_local
    try:
        base = _user_data_dir()
        base.mkdir(parents=True, exist_ok=True)
        return base / "corrections.json"
    except OSError:
        return app_local


CORRECTIONS_FILE = _corrections_file()


def load_corrections() -> list[dict]:
    """Charge la liste des corrections : [{"from": "...", "to": "...",
    "whole_word": bool, "case_sensitive": bool}, ...]. Retourne [] si absent."""
    try:
        raw = CORRECTIONS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        src = str(item.get("from", "")).strip()
        dst = str(item.get("to", ""))
        if not src:
            continue
        result.append({
            "from": src,
            "to": dst,
            "whole_word": bool(item.get("whole_word", True)),
            "case_sensitive": bool(item.get("case_sensitive", False)),
        })
    return result


def save_corrections(corrections: list[dict]) -> None:
    """Enregistre la liste des corrections (création du dossier si besoin)."""
    clean: list[dict] = []
    for item in corrections:
        src = str(item.get("from", "")).strip()
        if not src:
            continue
        clean.append({
            "from": src,
            "to": str(item.get("to", "")),
            "whole_word": bool(item.get("whole_word", True)),
            "case_sensitive": bool(item.get("case_sensitive", False)),
        })
    try:
        CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CORRECTIONS_FILE.write_text(
            json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def apply_corrections(text: str, corrections: list[dict] | None = None) -> str:
    """Applique les corrections de vocabulaire à un texte.

    Chaque correction remplace « from » par « to ». Par défaut :
      • whole_word=True  : ne remplace que des mots entiers (ex. « Volio » mais
        pas « Voliotech »).
      • case_sensitive=False : insensible à la casse.
    Si « to » commence par une majuscule et « from » aussi, la casse d'origine
    est raisonnablement préservée pour le premier caractère.
    """
    if corrections is None:
        corrections = load_corrections()
    if not corrections or not text:
        return text

    for corr in corrections:
        src = corr.get("from", "")
        dst = corr.get("to", "")
        if not src:
            continue
        flags = 0 if corr.get("case_sensitive", False) else re.IGNORECASE
        pattern = re.escape(src)
        if corr.get("whole_word", True):
            # \b ne fonctionne pas toujours avec les caractères accentués :
            # on encadre par des frontières basées sur les caractères de mot.
            pattern = r"(?<![\w'’])" + pattern + r"(?![\w'’])"
        try:
            text = re.sub(pattern, lambda _m: dst, text, flags=flags)
        except re.error:
            continue
    return text


# --------------------------------------------------------------------------- #
# Diarisation légère (heuristique par pauses).
#
# Sans modèle neuronal lourd : on attribue un numéro d'interlocuteur en se
# basant sur les pauses entre segments. Une pause « longue » (typiquement un
# tour de parole) fait basculer sur l'interlocuteur suivant. Simple, rapide,
# 100 % hors-ligne. Utile pour distinguer les tours de parole d'une conversation.
# --------------------------------------------------------------------------- #
def assign_speakers(
    segments: list["Segment"],
    pause_threshold: float = 1.0,
    max_speakers: int = 2,
) -> None:
    """Attribue un numéro d'interlocuteur (1..max_speakers) à chaque segment,
    en place. Bascule d'interlocuteur après une pause >= pause_threshold s.

    Heuristique volontairement simple : alterne entre interlocuteurs à chaque
    silence marqué. Convient aux dialogues à 2 voix (le cas le plus courant).
    """
    if not segments:
        return
    current = 1
    prev_end = None
    for seg in segments:
        if prev_end is not None:
            gap = seg.start - prev_end
            if gap >= pause_threshold:
                # Changement de tour de parole : passe à l'interlocuteur suivant.
                current = current % max_speakers + 1
        seg.speaker = current
        prev_end = seg.end


def format_diarized_text(segments: list["Segment"], label: str = "Interlocuteur") -> str:
    """Assemble le texte en regroupant par tours de parole :
        Interlocuteur 1 : ...
        Interlocuteur 2 : ...
    Regroupe les segments consécutifs d'un même interlocuteur.
    """
    if not segments:
        return ""
    lines: list[str] = []
    current_speaker = None
    buffer: list[str] = []

    def flush():
        if buffer and current_speaker is not None:
            lines.append(f"{label} {current_speaker} : " + " ".join(buffer).strip())

    for seg in segments:
        spk = seg.speaker if seg.speaker is not None else 1
        if spk != current_speaker:
            flush()
            buffer = []
            current_speaker = spk
        if seg.text:
            buffer.append(seg.text)
    flush()
    return "\n".join(lines).strip()


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
    diarize: bool = False                # identifier les interlocuteurs


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str
    speaker: int | None = None           # numéro d'interlocuteur (1, 2…) si diarisation


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

        # Si le modèle est déjà en cache : mode hors-ligne => AUCUN appel réseau,
        # donc aucun risque de re-téléchargement. Sinon : téléchargement autorisé.
        cached = enable_offline_if_cached(options.model_name)

        if log:
            log(f"Chargement du modèle « {options.model_name} » "
                f"(compute={options.compute_type}, threads={threads})…")
            if not cached:
                log("Premier lancement : le modèle est téléchargé (~3 Go). "
                    "Cela peut prendre plusieurs minutes.")

        t0 = time.time()
        self._model = WhisperModel(
            options.model_name,
            device="cpu",
            compute_type=options.compute_type,
            cpu_threads=threads,
            download_root=str(MODEL_CACHE),
            local_files_only=cached,
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

        # Corrections de vocabulaire personnalisées (chargées une seule fois).
        corrections = load_corrections()

        segments: list[Segment] = []
        srt_chunks: list[str] = []

        for i, seg in enumerate(segments_gen, start=1):
            if cancel and cancel():
                raise TranscriptionCancelled()
            clean = seg.text.strip()
            if corrections:
                clean = apply_corrections(clean, corrections)
            s = Segment(index=i, start=seg.start, end=seg.end, text=clean)
            segments.append(s)
            if on_segment:
                on_segment(s)
            if options.make_srt:
                srt_chunks.append(
                    f"{i}\n{format_timestamp(seg.start)} --> "
                    f"{format_timestamp(seg.end)}\n{clean}\n"
                )

        # Diarisation légère : attribue « Interlocuteur 1/2… » selon les pauses.
        if options.diarize and segments:
            assign_speakers(segments)
            full_text = format_diarized_text(segments)
        else:
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
