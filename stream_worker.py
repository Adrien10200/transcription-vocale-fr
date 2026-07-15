#!/usr/bin/env python3
"""
Worker de transcription EN DIRECT (streaming) depuis le microphone.

Exécuté dans un processus séparé (comme transcribe_worker.py). Il :
  • capture le micro en continu (16 kHz mono, format natif de Whisper),
  • découpe la parole sur les silences (VAD énergétique simple),
  • transcrit chaque « énoncé » dès qu'une pause est détectée,
  • émet des événements JSON (une ligne par événement) sur stdout.

Le découpage sur silence garantit que chaque morceau n'est transcrit
qu'UNE fois (pas de texte qui « scintille » comme avec des fenêtres glissantes).

Arrêt : l'application tue le processus (bouton Stop) — l'énoncé en cours est
finalisé juste avant via un signal côté worker (réception d'une ligne "stop"
sur stdin) pour ne pas perdre les derniers mots.

Usage :
  python stream_worker.py <model> <language> <compute> <beam> <device_index|-1>
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time


def emit(obj: dict) -> None:
    """Écrit un événement JSON UTF-8 sur stdout et vide le tampon."""
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


SAMPLE_RATE = 16000
BLOCK_SEC = 0.1                      # granularité de lecture (100 ms)
SILENCE_RMS = 0.015                 # seuil d'énergie pour « du silence »
SPEECH_RMS = 0.03                   # énergie MOYENNE mini pour valider un énoncé
SILENCE_HANG_SEC = 0.8              # pause après parole => fin d'énoncé
MAX_UTTERANCE_SEC = 18.0           # force la transcription si trop long
MIN_UTTERANCE_SEC = 0.5            # ignore les bruits trop courts

# Hallucinations classiques de Whisper sur du silence/bruit (à filtrer).
_HALLUCINATIONS = (
    "sous-titres réalisés par",
    "sous-titres réalisés para",
    "amara.org",
    "merci d'avoir regardé",
    "merci à tous",
    "abonnez-vous",
    "sous-titrage",
    "thanks for watching",
    "thank you for watching",
    "subtitles by",
    "♪",
)


def _is_hallucination(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return True
    for h in _HALLUCINATIONS:
        if h in low:
            return True
    # Un énoncé fait uniquement de ponctuation / très court est ignoré.
    letters = sum(ch.isalpha() for ch in low)
    return letters < 2


def main() -> int:
    if len(sys.argv) < 6:
        emit({"type": "failed", "message": "arguments invalides"})
        return 2

    model_name = sys.argv[1]
    language = sys.argv[2]
    compute = sys.argv[3]
    try:
        beam = int(sys.argv[4])
    except ValueError:
        beam = 5
    try:
        device = int(sys.argv[5])
    except ValueError:
        device = -1
    lang = None if language.lower() == "auto" else language

    # Signal d'arrêt : un thread lit stdin ; toute ligne => on arrête proprement.
    stop_flag = {"stop": False}

    def _watch_stdin() -> None:
        try:
            for _line in sys.stdin:
                stop_flag["stop"] = True
                break
        except Exception:  # noqa: BLE001
            pass
        stop_flag["stop"] = True

    try:
        import numpy as np
        import sounddevice as sd
        from transcriber_core import (
            Transcriber, TranscriptionOptions, load_corrections, apply_corrections,
        )

        threads = os.cpu_count() or 4
        emit({"type": "phase", "key": "loading_model",
              "params": {"model": model_name, "compute": compute, "threads": threads}})
        emit({"type": "phase", "key": "downloading_model", "params": {}})

        options = TranscriptionOptions(
            model_name=model_name, language=lang,
            compute_type=compute, beam_size=beam,
        )
        transcriber = Transcriber()
        transcriber.load(options)
        corrections = load_corrections()

        emit({"type": "phase", "key": "listening", "params": {}})

        # Démarre la surveillance de stdin pour l'arrêt.
        threading.Thread(target=_watch_stdin, daemon=True).start()

        blocksize = int(SAMPLE_RATE * BLOCK_SEC)
        utterance = []             # blocs float32 de l'énoncé courant
        silence_time = 0.0
        speaking = False
        seg_index = 0

        def transcribe_utterance(chunks) -> None:
            nonlocal seg_index
            if not chunks:
                return
            audio = np.concatenate(chunks).astype(np.float32)
            if len(audio) / SAMPLE_RATE < MIN_UTTERANCE_SEC:
                return
            # Rejette les énoncés dont l'énergie moyenne est trop faible
            # (bruit de fond) : évite les hallucinations de Whisper sur silence.
            mean_rms = float(np.sqrt(np.mean(audio**2)))
            if mean_rms < SPEECH_RMS:
                return
            segments, _info = transcriber._model.transcribe(  # noqa: SLF001
                audio,
                language=lang, task="transcribe",
                beam_size=beam, best_of=beam,
                temperature=[0.0, 0.2, 0.4],
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
            )
            # Garde les segments qui ne sont pas des « non-parole ».
            kept = []
            for s in segments:
                if getattr(s, "no_speech_prob", 0.0) > 0.6:
                    continue
                t = s.text.strip()
                if t:
                    kept.append(t)
            text = " ".join(kept).strip()
            if corrections:
                text = apply_corrections(text, corrections)
            if text and not _is_hallucination(text):
                seg_index += 1
                emit({"type": "segment", "index": seg_index, "text": text})

        dev = None if device < 0 else device
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=blocksize, device=dev) as stream:
            while not stop_flag["stop"]:
                block, _overflowed = stream.read(blocksize)
                mono = block[:, 0] if block.ndim > 1 else block
                rms = float(np.sqrt(np.mean(mono**2))) if len(mono) else 0.0

                if rms >= SILENCE_RMS:
                    speaking = True
                    silence_time = 0.0
                    utterance.append(mono.copy())
                else:
                    if speaking:
                        utterance.append(mono.copy())
                        silence_time += BLOCK_SEC
                        if silence_time >= SILENCE_HANG_SEC:
                            transcribe_utterance(utterance)
                            utterance = []
                            speaking = False
                            silence_time = 0.0

                # Sécurité : énoncé trop long => on transcrit et on continue.
                if speaking and len(utterance) * BLOCK_SEC >= MAX_UTTERANCE_SEC:
                    transcribe_utterance(utterance)
                    utterance = []
                    speaking = False
                    silence_time = 0.0

        # Arrêt demandé : finalise l'énoncé en cours.
        transcribe_utterance(utterance)
        emit({"type": "finished_stream"})
        return 0

    except Exception as exc:  # noqa: BLE001
        emit({"type": "failed", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
