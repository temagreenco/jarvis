"""
Generate clip candidates from sentence windows.
"""
from __future__ import annotations

from typing import List, Dict


def _join_sentences(sentences: List[Dict]) -> str:
    return " ".join(sentence.get("text", "") for sentence in sentences).strip()


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
            candidates.append(
                {
                    "id": f"cand-{start_idx + 1}-{end_idx + 1}",
                    "start": start,
                    "end": end,
                    "duration": duration,
                    "sentences_idx_range": (start_idx, end_idx),
                    "sentences": window,
                    "text": _join_sentences(window),
                }
            )
    return candidates
