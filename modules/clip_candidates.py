"""
Generate clip candidates from sentence windows.
"""
from __future__ import annotations

from typing import List, Dict, Optional


def _join_sentences(sentences: List[Dict]) -> str:
    return " ".join(sentence.get("text", "") for sentence in sentences).strip()


def _join_words(sentences: List[Dict]) -> List[Dict]:
    words: List[Dict] = []
    for sentence in sentences:
        words.extend(sentence.get("words", []) or [])
    return words


def _avg_confidence(words: List[Dict]) -> Optional[float]:
    scores = [float(w.get("p")) for w in words if w.get("p") is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _min_confidence(words: List[Dict]) -> Optional[float]:
    scores = [float(w.get("p")) for w in words if w.get("p") is not None]
    if not scores:
        return None
    return min(scores)


def _pause_ratio(words: List[Dict], duration: float) -> float:
    if duration <= 0.0 or len(words) < 2:
        return 0.0
    total_gap = 0.0
    ordered = sorted(words, key=lambda w: float(w.get("start", 0.0)))
    for idx in range(len(ordered) - 1):
        gap = float(ordered[idx + 1].get("start", 0.0)) - float(ordered[idx].get("end", 0.0))
        if gap > 0:
            total_gap += gap
    return min(total_gap / duration, 1.0)


def _ends_with_punctuation(text: str) -> bool:
    trimmed = text.strip()
    if not trimmed:
        return False
    if trimmed.endswith("..."):
        return True
    return trimmed.endswith((".", "!", "?"))


def generate_candidates(
    sentences: List[Dict],
    min_dur: float = 12.0,
    max_dur: float = 45.0,
    min_sentences: int = 2,
    max_sentences: int = 6,
) -> List[Dict]:
    candidates: List[Dict] = []
    count = len(sentences)
    if count == 0:
        return candidates

    for start_idx in range(count):
        for end_idx in range(start_idx + min_sentences - 1, min(count, start_idx + max_sentences)):
            start = float(sentences[start_idx]["start"])
            end = float(sentences[end_idx]["end"])
            duration = end - start
            if duration > max_dur:
                break
            if duration < min_dur:
                continue
            window = sentences[start_idx : end_idx + 1]
            window_text = _join_sentences(window)
            words = _join_words(window)
            word_count = len(words)
            avg_conf = _avg_confidence(words)
            min_conf = _min_confidence(words)
            speech_rate_wps = word_count / duration if duration > 0 else 0.0
            candidates.append(
                {
                    "id": f"cand-{start_idx + 1}-{end_idx + 1}",
                    "start": start,
                    "end": end,
                    "duration": duration,
                    "sentences_idx_range": (start_idx, end_idx),
                    "sentences": window,
                    "text": window_text,
                    "words": words,
                    "word_count": word_count,
                    "avg_word_confidence": avg_conf,
                    "min_word_confidence": min_conf,
                    "speech_rate_wps": speech_rate_wps,
                    "pause_ratio": _pause_ratio(words, duration),
                    "ends_with_punctuation": _ends_with_punctuation(window_text),
                }
            )
    return candidates
