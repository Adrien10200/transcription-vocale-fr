#!/usr/bin/env python3
"""
Transcription de voix française vers texte brut.

Optimisé pour la MEILLEURE qualité possible (pas pour la vitesse) sur CPU.
Utilise faster-whisper avec le modèle large-v3, recherche par faisceau,
repli sur la température, et un filtre VAD (détection d'activité vocale).

Usage :
    python transcribe.py "chemin/vers/audio.mp3"
    python transcribe.py "audio.mp3" --model large-v3 --output resultat.txt
    python transcribe.py "dossier_audio/"          # traite tous les fichiers du dossier

Le texte brut (.txt) est écrit à côté du fichier source par défaut.
Un fichier .srt (sous-titres horodatés) est aussi généré si --srt est passé.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration de l'environnement AVANT tout import lourd.
# On force ffmpeg portable dans le PATH pour que faster-whisper puisse
# décoder n'importe quel format audio/vidéo.
# --------------------------------------------------------------------------- #
_HERE = Path(__file__).resolve().parent
_FFMPEG_BIN = _HERE / "tools" / "ffmpeg" / "bin"
if _FFMPEG_BIN.is_dir():
    os.environ["PATH"] = str(_FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")

# Cache local des modèles (évite de re-télécharger et garde tout dans le projet).
_MODEL_CACHE = _HERE / "models"
_MODEL_CACHE.mkdir(exist_ok=True)
os.environ.setdefault("HF_HOME", str(_MODEL_CACHE))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_MODEL_CACHE))

# Extensions audio/vidéo prises en charge (ffmpeg décode le reste de toute façon).
_MEDIA_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".3gp", ".amr",
}


def _eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def _format_timestamp(seconds: float) -> str:
    """Formate un temps en secondes vers HH:MM:SS,mmm (format SRT)."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000.0))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _collect_inputs(target: Path) -> list[Path]:
    """Retourne la liste des fichiers média à traiter."""
    if target.is_dir():
        files = sorted(
            p for p in target.iterdir()
            if p.is_file() and p.suffix.lower() in _MEDIA_EXTS
        )
        if not files:
            _eprint(f"[!] Aucun fichier audio/vidéo trouvé dans : {target}")
        return files
    if target.is_file():
        return [target]
    _eprint(f"[!] Introuvable : {target}")
    return []


def _build_model(model_name: str, compute_type: str, cpu_threads: int,
                 device: str = "auto"):
    """Charge le modèle Whisper (téléchargement automatique au premier lancement).

    `device` accepte "auto", "cpu" ou "cuda". Rappel : CTranslate2 nomme "cuda"
    aussi bien les GPU NVIDIA que les GPU AMD (ROCm/HIP). En cas d'échec sur
    GPU, on retombe automatiquement sur le CPU plutôt que d'abandonner.
    """
    from faster_whisper import WhisperModel
    from transcriber_core import (
        DEVICE_CPU, DEVICE_GPU, detect_device, resolve_compute_type,
    )

    resolved = detect_device(device)
    compute = resolve_compute_type(resolved, None if compute_type == "auto" else compute_type)

    def _make(dev: str, comp: str):
        kwargs = dict(compute_type=comp, download_root=str(_MODEL_CACHE))
        if dev == DEVICE_CPU:
            kwargs["cpu_threads"] = cpu_threads
        return WhisperModel(model_name, device=dev, **kwargs)

    _eprint(f"[*] Chargement du modèle « {model_name} » (device={resolved}, "
            f"compute={compute}, threads={cpu_threads})…")
    _eprint("    Premier lancement : téléchargement du modèle (~3 Go pour large-v3). "
            "Cela peut prendre plusieurs minutes.")
    t0 = time.time()
    try:
        model = _make(resolved, compute)
    except Exception as exc:  # noqa: BLE001
        if resolved != DEVICE_GPU:
            raise
        fallback = resolve_compute_type(DEVICE_CPU, None)
        _eprint(f"[!] GPU indisponible ({type(exc).__name__}: {exc}). "
                f"Retour au CPU (compute={fallback}).")
        resolved, compute = DEVICE_CPU, fallback
        model = _make(DEVICE_CPU, fallback)
    _eprint(f"[*] Modèle prêt en {time.time() - t0:.1f}s ({resolved}).")
    return model


def _transcribe_file(
    model,
    audio_path: Path,
    language: str,
    beam_size: int,
    initial_prompt: str | None,
    make_srt: bool,
    output_path: Path | None,
) -> None:
    _eprint(f"\n[>] Transcription : {audio_path.name}")
    t0 = time.time()

    # Paramètres réglés pour la précision maximale en français.
    segments, info = model.transcribe(
        str(audio_path),
        language=language,                 # "fr" forcé => pas d'erreur de détection
        task="transcribe",
        beam_size=beam_size,               # recherche par faisceau large = plus précis
        best_of=beam_size,
        patience=1.0,
        # Repli progressif sur la température si le décodage échoue/répète.
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        condition_on_previous_text=True,   # garde le contexte entre segments
        initial_prompt=initial_prompt,
        word_timestamps=make_srt,          # nécessaire seulement pour de beaux SRT
        # Filtre VAD : supprime les silences => moins d'hallucinations.
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=400,
        ),
        # Ponctuation : rattachement propre aux mots (utile en français).
        prepend_punctuations="\"'“¿([{-",
        append_punctuations="\"'.。,，!！?？:：”)]}、",
    )

    _eprint(f"    Langue détectée/forcée : {info.language} "
            f"(prob. {info.language_probability:.2f}) — durée {info.duration:.1f}s")

    text_parts: list[str] = []
    srt_lines: list[str] = []
    seg_index = 0

    for segment in segments:
        seg_index += 1
        clean = segment.text.strip()
        text_parts.append(clean)

        # Progression en direct sur stderr.
        _eprint(f"    [{_format_timestamp(segment.start)} -> "
                f"{_format_timestamp(segment.end)}] {clean}")

        if make_srt:
            srt_lines.append(str(seg_index))
            srt_lines.append(
                f"{_format_timestamp(segment.start)} --> "
                f"{_format_timestamp(segment.end)}"
            )
            srt_lines.append(clean)
            srt_lines.append("")

    # Assemblage du texte brut : un espace entre segments, nettoyage des espaces.
    full_text = " ".join(part for part in text_parts if part)
    full_text = " ".join(full_text.split()).strip()

    # Détermination du chemin de sortie.
    if output_path is not None:
        txt_path = output_path
    else:
        txt_path = audio_path.with_suffix(".txt")

    txt_path.write_text(full_text + "\n", encoding="utf-8")
    _eprint(f"[✓] Texte écrit  : {txt_path}")

    if make_srt:
        srt_path = txt_path.with_suffix(".srt")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        _eprint(f"[✓] SRT écrit    : {srt_path}")

    elapsed = time.time() - t0
    ratio = (info.duration / elapsed) if elapsed > 0 else 0.0
    _eprint(f"[✓] Terminé en {elapsed:.1f}s "
            f"({ratio:.2f}x temps réel, {seg_index} segments).")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcription de voix française vers texte brut (haute précision).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        help="Fichier audio/vidéo OU dossier contenant des fichiers média.",
    )
    parser.add_argument(
        "--model", default="large-v3",
        help="Modèle Whisper (défaut : large-v3 = meilleure qualité). "
             "Alternatives : large-v2, medium, small…",
    )
    parser.add_argument(
        "--language", default="fr",
        help="Langue forcée (défaut : fr). Mettre 'auto' pour la détection automatique.",
    )
    parser.add_argument(
        "--compute-type", default="auto",
        choices=["auto", "int8", "int8_float32", "float32", "float16", "bfloat16"],
        help="Type de calcul. 'auto' (défaut) = int8 sur CPU, float16 sur GPU. "
             "float32 = un poil plus précis mais bien plus lent et gourmand en RAM. "
             "float16/bfloat16 nécessitent un GPU.",
    )
    parser.add_argument(
        "--device", default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Périphérique de calcul. 'auto' (défaut) = GPU s'il est détecté, "
             "sinon CPU. 'cuda' désigne aussi bien un GPU NVIDIA (CUDA) qu'un "
             "GPU AMD (ROCm) : CTranslate2 emploie le même nom pour les deux.",
    )
    parser.add_argument(
        "--beam-size", type=int, default=8,
        help="Taille du faisceau de recherche (défaut : 8, plus = plus précis/plus lent).",
    )
    parser.add_argument(
        "--threads", type=int, default=0,
        help="Nombre de threads CPU (0 = automatique, tous les cœurs logiques).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Chemin du fichier .txt de sortie (uniquement si UN seul fichier en entrée).",
    )
    parser.add_argument(
        "--prompt", default=None,
        help="Amorce de contexte (vocabulaire, noms propres attendus…) pour guider le modèle.",
    )
    parser.add_argument(
        "--srt", action="store_true",
        help="Génère aussi un fichier .srt (sous-titres horodatés).",
    )
    args = parser.parse_args()

    language = None if args.language.lower() == "auto" else args.language

    threads = args.threads
    if threads <= 0:
        threads = os.cpu_count() or 4

    target = Path(args.input).expanduser().resolve()
    inputs = _collect_inputs(target)
    if not inputs:
        return 1

    if args.output and len(inputs) > 1:
        _eprint("[!] --output ne peut être utilisé qu'avec un seul fichier d'entrée.")
        return 2

    try:
        model = _build_model(args.model, args.compute_type, threads, args.device)
    except Exception as exc:  # noqa: BLE001
        _eprint(f"[!] Échec du chargement du modèle : {exc}")
        return 3

    output_path = Path(args.output).expanduser().resolve() if args.output else None

    failures = 0
    for audio_path in inputs:
        try:
            _transcribe_file(
                model=model,
                audio_path=audio_path,
                language=language,
                beam_size=args.beam_size,
                initial_prompt=args.prompt,
                make_srt=args.srt,
                output_path=output_path,
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            _eprint(f"[!] Erreur sur « {audio_path.name} » : {exc}")

    if failures:
        _eprint(f"\n[!] Terminé avec {failures} échec(s) sur {len(inputs)} fichier(s).")
        return 4

    _eprint(f"\n[✓] Tout est transcrit ({len(inputs)} fichier(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
