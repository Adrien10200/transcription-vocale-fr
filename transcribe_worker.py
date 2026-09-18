#!/usr/bin/env python3
"""
Worker de transcription exécuté dans un PROCESSUS séparé.

Il émet des événements JSON (un par ligne) sur stdout, ce qui permet à
l'interface graphique de suivre la progression. L'intérêt majeur d'un
processus séparé : il peut être TUÉ instantanément (bouton « Annuler »),
y compris pendant le téléchargement ou le chargement du modèle — ce qu'un
thread Python ne permet pas.

Protocole (stdout, une ligne JSON par événement) :
  {"type": "phase",    "key": "...", "params": {...}}
  {"type": "segment",  "index": 1, "start": 0.0, "end": 2.5, "text": "..."}
  {"type": "finished", "text": "...", "segments": N, "language": "fr",
                       "language_probability": 1.0, "duration": 35.2,
                       "elapsed": 12.3, "srt": "..."}
  {"type": "failed",   "message": "..."}

Usage :
  python transcribe_worker.py <audio_path> <model> <language> <compute> <beam>
"""

from __future__ import annotations

import json
import os
import sys


def emit(obj: dict) -> None:
    """Écrit un événement JSON sur stdout en UTF-8, et vide le tampon.

    On écrit TOUJOURS des octets UTF-8 bruts (encodage explicite) pour éviter
    que Windows n'encode en cp1252 et corrompe les accents. On privilégie le
    tampon binaire (sys.stdout.buffer) ; à défaut, le descripteur de fichier 1.
    """
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")

    out = sys.stdout
    buffer = getattr(out, "buffer", None) if out is not None else None
    if buffer is not None:
        try:
            buffer.write(data)
            buffer.flush()
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        os.write(1, data)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    if len(sys.argv) < 6:
        emit({"type": "failed", "message": "arguments invalides"})
        return 2

    audio_path = sys.argv[1]
    model_name = sys.argv[2]
    language = sys.argv[3]
    compute = sys.argv[4]
    try:
        beam = int(sys.argv[5])
    except ValueError:
        beam = 8
    # 7e argument optionnel : "1" pour activer la diarisation.
    diarize = len(sys.argv) > 6 and sys.argv[6] == "1"

    lang = None if language.lower() == "auto" else language

    try:
        # Imports lourds ici pour que le kill reste réactif au démarrage.
        import os
        from transcriber_core import (
            Transcriber, TranscriptionOptions, _model_is_cached,
        )

        threads = os.cpu_count() or 4
        emit({"type": "phase", "key": "loading_model",
              "params": {"model": model_name, "compute": compute, "threads": threads}})
        # N'affiche « téléchargement » QUE si le modèle n'est pas déjà en cache.
        if not _model_is_cached(model_name):
            emit({"type": "phase", "key": "downloading_model", "params": {}})

        options = TranscriptionOptions(
            model_name=model_name,
            language=lang,
            compute_type=compute,
            beam_size=beam,
            diarize=diarize,
        )

        # Vérifie qu'un flux audio décodable existe (ex. MP4 vidéo sans son).
        try:
            import av
            container = av.open(audio_path)
            has_audio = any(s.type == "audio" for s in container.streams)
            container.close()
            if not has_audio:
                emit({"type": "failed",
                      "message": "no_audio_track"})
                return 1
        except Exception:  # noqa: BLE001
            # Si la sonde échoue, on laisse le décodeur principal tenter quand même.
            pass

        transcriber = Transcriber()
        transcriber.load(options)

        emit({"type": "phase", "key": "transcribing", "params": {}})

        def on_segment(s) -> None:
            emit({"type": "segment", "index": s.index,
                  "start": s.start, "end": s.end, "text": s.text,
                  "speaker": s.speaker})

        result = transcriber.transcribe(
            audio_path, options, on_segment=on_segment,
        )

        emit({
            "type": "finished",
            "text": result.text,
            "segments": len(result.segments),
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "elapsed": result.elapsed,
            "srt": result.srt,
        })
        return 0

    except Exception as exc:  # noqa: BLE001
        emit({"type": "failed", "message": str(exc)})
        return 1


if __name__ == "__main__":
    # safe_exit court-circuite l'arrêt de l'interpréteur quand un modèle GPU est
    # vivant : ses destructeurs natifs se bloquent (CTranslate2 #2038).
    from transcriber_core import safe_exit
    raise SystemExit(safe_exit(main()))
