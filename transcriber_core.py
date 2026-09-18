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


# --------------------------------------------------------------------------- #
# Choix du backend de calcul (CPU / GPU).
#
# CTranslate2 — le moteur de faster-whisper — expose les GPU NVIDIA (CUDA) ET
# AMD (ROCm/HIP, depuis CTranslate2 4.7.1) sous le MÊME nom de périphérique :
# "cuda". Il n'existe pas de valeur "rocm" ; sur une Radeon on passe donc bien
# device="cuda". La distinction se fait au moment de l'installation de la roue
# CTranslate2 (roue CUDA par défaut sur PyPI, roue ROCm à installer à la main).
#
# Le GPU n'est JAMAIS imposé : `detect_device()` ne renvoie "cuda" que si le
# moteur voit réellement un périphérique, et le chargement du modèle retombe
# automatiquement sur le CPU en cas d'échec (voir Transcriber.load).
# --------------------------------------------------------------------------- #
DEVICE_AUTO = "auto"
DEVICE_CPU = "cpu"
DEVICE_GPU = "cuda"          # CUDA (NVIDIA) *et* ROCm/HIP (AMD)

# Type de calcul conseillé par périphérique.
#   - CPU : int8 (seul choix réellement rapide sans AVX-512/AMX).
#   - GPU : float16 — plus PRÉCIS que int8 et largement plus rapide ; large-v3
#     tient dans ~3–4 Go de VRAM, donc sans risque sur une carte ≥ 8 Go.
DEFAULT_COMPUTE_BY_DEVICE = {
    DEVICE_CPU: "int8",
    DEVICE_GPU: "float16",
}


def gpu_device_count() -> int:
    """Nombre de GPU visibles par CTranslate2 (CUDA ou ROCm). 0 si aucun."""
    try:
        import ctranslate2
    except Exception:
        return 0
    try:
        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        # Roue CPU-only, pilote absent, runtime ROCm/CUDA incomplet…
        return 0


def gpu_is_available() -> bool:
    return gpu_device_count() > 0


def detect_device(preference: str = DEVICE_AUTO) -> str:
    """Résout une préférence utilisateur en périphérique concret.

    "auto" => GPU s'il est réellement disponible, sinon CPU.
    """
    if preference == DEVICE_CPU:
        return DEVICE_CPU
    if preference == DEVICE_GPU:
        # Choix explicite : on respecte la demande. Si le GPU est en fait
        # inutilisable, Transcriber.load bascule sur le CPU avec un message.
        return DEVICE_GPU
    return DEVICE_GPU if gpu_is_available() else DEVICE_CPU


def resolve_compute_type(device: str, compute_type: str | None) -> str:
    """Complète un type de calcul non renseigné ("auto"/None) selon le device.

    Évite le piège classique : garder int8 après être passé sur GPU, ce qui
    perd en précision sans gagner en vitesse.
    """
    if compute_type and compute_type != DEVICE_AUTO:
        return compute_type
    return DEFAULT_COMPUTE_BY_DEVICE.get(device, "int8")


def describe_gpu() -> str:
    """Libellé lisible du backend GPU, pour les journaux et l'interface."""
    count = gpu_device_count()
    if count <= 0:
        return "aucun GPU détecté par CTranslate2"
    try:
        import ctranslate2
        types = sorted(ctranslate2.get_supported_compute_types(DEVICE_GPU))
    except Exception:
        types = []
    suffix = f" — types: {', '.join(types)}" if types else ""
    return f"{count} GPU détecté(s){suffix}"


# Variables d'environnement : le GPU reste une option explicite, activable sans
# toucher au code ni à l'installeur (qui continue d'embarquer la roue CPU).
#   TVFR_DEVICE  = auto | cpu | cuda
#   TVFR_COMPUTE = int8 | float16 | bfloat16 | float32 | …
ENV_DEVICE = "TVFR_DEVICE"
ENV_COMPUTE = "TVFR_COMPUTE"

# Vrai dès qu'un modèle a été chargé sur GPU dans ce processus.
_gpu_in_use = False


def gpu_in_use() -> bool:
    """Vrai si un modèle GPU est vivant dans ce processus."""
    return _gpu_in_use


# Références fortes gardées au niveau du module. Un modèle détenu par une
# variable LOCALE est détruit dès que la fonction se termine : les workers
# créaient leur Transcriber dans main(), dont le retour déclenchait le
# destructeur bloquant AVANT même que safe_exit ne soit atteint. Épingler le
# modèle ici le rend indestructible jusqu'à l'arrêt brutal du processus.
_pinned_models: list = []


def _pin_model(model) -> None:
    """Rend un modèle indestructible (contournement CTranslate2 #2038)."""
    if model is not None:
        _pinned_models.append(model)


def rocm_runtime_present() -> bool:
    """Vrai si la DLL CTranslate2 chargée est celle liée à ROCm.

    On teste la présence du runtime ROCm à côté du paquet ctranslate2, là où
    `ctranslate2/__init__.py` va le chercher (os.add_dll_directory). C'est vrai
    dans la variante GPU et dans un environnement de développement GPU, faux
    dans la build CPU standard — qui garde donc un arrêt normal.
    """
    module = sys.modules.get("ctranslate2")
    path = getattr(module, "__file__", None) if module else None
    if not path:
        return False
    try:
        return (Path(path).resolve().parent.parent / "_rocm_sdk_core").is_dir()
    except Exception:
        return False


def safe_exit(code: int = 0) -> int:
    """Termine le processus SANS exécuter les destructeurs natifs.

    Seconde moitié du contournement de
    https://github.com/OpenNMT/CTranslate2/issues/2038 : sur gfx1100 (RX 7900
    XT/XTX) sous Windows + ROCm, détruire un modèle CTranslate2 se bloque
    indéfiniment dans la libération mémoire HIP. Retenir le modèle (voir
    Transcriber._retire_model) suffit pendant la vie du processus, mais PAS à
    l'arrêt : l'interpréteur détruit alors tous les objets restants et se figerait.

    ATTENTION : le blocage ne dépend PAS de l'utilisation réelle du GPU.
    `ctranslate2/__init__.py` charge `ctranslate2.dll` — liée à hipBLAS, rocBLAS
    et rocSOLVER — dès l'import, ce qui initialise le runtime ROCm même pour un
    calcul sur CPU. Mesuré : dans la variante GPU, un travail lancé en mode CPU
    terminait sa transcription puis restait figé indéfiniment à l'arrêt. La
    condition porte donc sur le runtime chargé, pas sur le périphérique utilisé.

    Comme les workers sont des processus jetables (un travail, puis sortie), on
    court-circuite l'arrêt propre avec os._exit après avoir vidé les tampons.
    Dans la build CPU standard, rien ne change : la valeur est simplement renvoyée.
    """
    if not (_gpu_in_use or rocm_runtime_present()):
        return code
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)


def resolve_backend(options: "TranscriptionOptions") -> tuple[str, str]:
    """Détermine (device, compute_type) effectifs pour un jeu d'options.

    Ordre de priorité : variable d'environnement > champ de `options` > auto.

    Note : les workers (fichier / dictée) transmettent historiquement
    `compute_type="int8"`, valeur pensée pour le CPU. Si le calcul bascule sur
    GPU sans consigne explicite, on repasse sur le type conseillé (float16) :
    sur GPU, int8 serait à la fois moins précis et sans gain de vitesse.
    """
    device_pref = os.environ.get(ENV_DEVICE) or options.device or DEVICE_AUTO
    device = detect_device(device_pref.strip().lower())

    env_compute = os.environ.get(ENV_COMPUTE)
    if env_compute:
        return device, env_compute.strip().lower()

    if device == DEVICE_GPU and options.compute_type == DEFAULT_COMPUTE_BY_DEVICE[DEVICE_CPU]:
        return device, DEFAULT_COMPUTE_BY_DEVICE[DEVICE_GPU]

    return device, resolve_compute_type(device, options.compute_type)


@dataclass
class TranscriptionOptions:
    model_name: str = "large-v3"
    language: str | None = "fr"          # None => détection automatique
    compute_type: str = "int8"
    device: str = DEVICE_AUTO            # "auto" | "cpu" | "cuda" (CUDA ou ROCm)
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
        self._device: str = DEVICE_CPU
        # Modèles GPU « retirés » mais volontairement NON libérés — voir
        # _retire_model() et le contournement du blocage CTranslate2 #2038.
        self._retired: list = []

    @staticmethod
    def _resolve_threads(threads: int) -> int:
        return threads if threads and threads > 0 else (os.cpu_count() or 4)

    @property
    def device(self) -> str:
        """Périphérique réellement utilisé par le modèle chargé."""
        return self._device

    def _retire_model(self, log: Callable[[str], None] | None = None) -> None:
        """Se sépare du modèle courant SANS déclencher son destructeur sur GPU.

        Contournement de https://github.com/OpenNMT/CTranslate2/issues/2038 :
        sur gfx1100 (RX 7900 XT/XTX) sous Windows + ROCm, la destruction d'un
        modèle CTranslate2 se bloque indéfiniment dans la libération mémoire
        HIP. Or un simple réassignement de `self._model` suffit à déclencher ce
        destructeur. On conserve donc une référence vive : la VRAM du modèle
        précédent reste occupée jusqu'à la fin du processus, mais l'application
        ne se fige pas. Sur CPU, aucun problème : on libère normalement.
        """
        if self._model is None:
            return
        if self._device == DEVICE_GPU:
            self._retired.append(self._model)
            if log:
                log("Changement de configuration sur GPU : le modèle précédent "
                    "reste en VRAM jusqu'au redémarrage (contournement "
                    "CTranslate2 #2038).")
        self._model = None
        self._loaded_key = None

    def load(
        self,
        options: TranscriptionOptions,
        log: Callable[[str], None] | None = None,
    ) -> None:
        """Charge (ou recharge) le modèle si nécessaire."""
        from faster_whisper import WhisperModel

        threads = self._resolve_threads(options.cpu_threads)
        device, compute_type = resolve_backend(options)
        key = (options.model_name, compute_type, threads, device)
        if self._model is not None and key == self._loaded_key:
            return

        self._retire_model(log)

        # Si le modèle est déjà en cache : mode hors-ligne => AUCUN appel réseau,
        # donc aucun risque de re-téléchargement. Sinon : téléchargement autorisé.
        cached = enable_offline_if_cached(options.model_name)

        if log:
            log(f"Chargement du modèle « {options.model_name} » "
                f"(device={device}, compute={compute_type}, threads={threads})…")
            if not cached:
                log("Premier lancement : le modèle est téléchargé (~3 Go). "
                    "Cela peut prendre plusieurs minutes.")

        t0 = time.time()
        try:
            self._model = self._build(
                WhisperModel, options, device, compute_type, threads, cached,
            )
            self._device = device
            if device == DEVICE_GPU:
                global _gpu_in_use
                _gpu_in_use = True
            # Le runtime ROCm se bloque à la destruction, même après un calcul
            # sur CPU : on épingle dès qu'il est présent, pas seulement sur GPU.
            if device == DEVICE_GPU or rocm_runtime_present():
                _pin_model(self._model)
        except Exception as exc:
            # Le GPU peut échouer pour de multiples raisons (roue CUDA installée
            # sur une machine AMD, runtime ROCm incomplet, VRAM insuffisante,
            # type de calcul non supporté…). Dans tous ces cas, on ne casse pas
            # l'application : on revient au CPU, qui fonctionne partout.
            if device != DEVICE_GPU:
                raise
            fallback_compute = resolve_compute_type(DEVICE_CPU, None)
            if log:
                log(f"GPU indisponible ({type(exc).__name__}: {exc}). "
                    f"Retour au CPU (compute={fallback_compute}).")
            self._model = self._build(
                WhisperModel, options, DEVICE_CPU, fallback_compute, threads, cached,
            )
            self._device = DEVICE_CPU
            if rocm_runtime_present():
                _pin_model(self._model)
            compute_type = fallback_compute
            key = (options.model_name, compute_type, threads, DEVICE_CPU)

        self._loaded_key = key
        if log:
            log(f"Modèle prêt en {time.time() - t0:.1f}s ({self._device}).")

    @staticmethod
    def _build(
        model_cls,
        options: TranscriptionOptions,
        device: str,
        compute_type: str,
        threads: int,
        cached: bool,
    ):
        """Instancie WhisperModel pour un périphérique donné."""
        kwargs = dict(
            compute_type=compute_type,
            download_root=str(MODEL_CACHE),
            local_files_only=cached,
        )
        if device == DEVICE_CPU:
            # `cpu_threads` n'a de sens que sur CPU.
            kwargs["cpu_threads"] = threads
        return model_cls(options.model_name, device=device, **kwargs)

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
