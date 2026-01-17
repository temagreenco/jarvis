"""
Transcription helper for auto-clips.
"""
from __future__ import annotations

import os
from typing import List, Dict, Optional, Tuple


def transcribe_to_segments(
    video_path: str, language: Optional[str] = None
) -> Tuple[List[Dict], List[Dict]]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("faster-whisper is required for auto_clips") from exc

    model_name = os.getenv("JARVIS_WHISPER_MODEL", "base")
    use_gpu = os.getenv("JARVIS_USE_GPU", "false").lower() == "true"
    device = "cuda" if use_gpu else "cpu"
    compute_type = "float16" if use_gpu else "int8"

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        video_path, language=language, beam_size=5, word_timestamps=True
    )

    results: List[Dict] = []
    words: List[Dict] = []
    for segment in segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        results.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
            }
        )
        for word in segment.words or []:
            word_text = (word.word or "").strip()
            if not word_text:
                continue
            payload = {
                "w": word_text,
                "start": float(word.start),
                "end": float(word.end),
            }
            if hasattr(word, "probability") and word.probability is not None:
                payload["p"] = float(word.probability)
            words.append(payload)
    return results, words
