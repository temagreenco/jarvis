"""
Transcription helper for auto-clips.
"""
from __future__ import annotations

import os
from typing import Callable, List, Dict, Optional, Tuple

from config.settings import settings


def transcribe_to_segments(
    video_path: str,
    language: Optional[str] = None,
    progress_callback: Optional[Callable[[int, float], None]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("faster-whisper is required for auto_clips") from exc

    model_name = os.getenv("JARVIS_WHISPER_MODEL") or settings.whisper_model
    use_gpu_env = os.getenv("JARVIS_USE_GPU")
    use_gpu = settings.use_gpu if use_gpu_env is None else (use_gpu_env.lower() == "true")
    device = settings.whisper_device if use_gpu else "cpu"
    compute_type = settings.whisper_compute_type if use_gpu else "int8"

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        video_path, language=language, beam_size=5, word_timestamps=True
    )
    total_duration = getattr(info, "duration", None)

    results: List[Dict] = []
    words: List[Dict] = []
    for index, segment in enumerate(segments):
        if progress_callback and total_duration:
            ratio = min(max(float(segment.end) / float(total_duration), 0.0), 1.0)
            if index % 10 == 0 or ratio >= 1.0:
                progress_callback(index, ratio)
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
