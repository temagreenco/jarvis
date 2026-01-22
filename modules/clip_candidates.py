"""
Generate clip candidates from sentence windows.
"""
from __future__ import annotations

from typing import List, Dict, Optional, Callable

# Hook indicator patterns for quick pre-scoring
QUICK_HOOK_INDICATORS = [
    "?",  # Questions
    "!",  # Exclamations
    # English
    "secret", "mistake", "truth", "never", "always",
    "biggest", "worst", "best", "stop", "why", "how",
    # Hebrew
    "סוד", "טעות", "אמת", "אף פעם", "תמיד",
    "הכי גדול", "הכי גרוע", "הכי טוב", "תפסיקו", "למה", "איך",
    "בעיה", "הבעיה", "האמת", "מה ש",
]


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


def _quick_hook_score(text: str) -> float:
    """Quick hook scoring for candidate prioritization (not full scoring)."""
    if not text:
        return 0.0
    lowered = text.lower()
    score = 0.0
    for indicator in QUICK_HOOK_INDICATORS:
        if indicator in lowered:
            score += 1.0
    return score


def _has_natural_start(sentence: Dict, prev_sentence: Optional[Dict]) -> bool:
    """Check if sentence is a natural starting point (after a pause or topic shift)."""
    if prev_sentence is None:
        return True

    # Gap between sentences suggests natural break
    gap = float(sentence.get("start", 0)) - float(prev_sentence.get("end", 0))
    if gap >= 0.5:
        return True

    # Previous sentence ended with strong punctuation
    prev_text = prev_sentence.get("text", "").strip()
    if prev_text.endswith((".", "!", "?")):
        return True

    return False


def generate_candidates(
    sentences: List[Dict],
    min_dur: float = 12.0,
    max_dur: float = 45.0,
    min_sentences: int = 2,
    max_sentences: int = 6,
    prioritize_hooks: bool = True,
) -> List[Dict]:
    """Generate clip candidates from sentence windows.

    Args:
        sentences: List of sentence dicts with 'start', 'end', 'text', 'words'
        min_dur: Minimum clip duration in seconds
        max_dur: Maximum clip duration in seconds
        min_sentences: Minimum sentences per clip
        max_sentences: Maximum sentences per clip
        prioritize_hooks: If True, prioritize candidates starting with hook-like sentences

    Returns:
        List of candidate dicts sorted by potential (hooks first if prioritize_hooks=True)
    """
    candidates: List[Dict] = []
    count = len(sentences)
    if count == 0:
        return candidates

    for start_idx in range(count):
        # Check if this is a natural starting point
        prev_sentence = sentences[start_idx - 1] if start_idx > 0 else None
        is_natural_start = _has_natural_start(sentences[start_idx], prev_sentence)

        # Quick hook score for the starting sentence
        first_sentence_text = sentences[start_idx].get("text", "")
        hook_potential = _quick_hook_score(first_sentence_text)

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
                    # Hook-first optimization fields
                    "hook_potential": hook_potential,
                    "is_natural_start": is_natural_start,
                }
            )

    # Sort candidates: hook potential (desc), natural start (desc), then by start time
    if prioritize_hooks:
        candidates.sort(
            key=lambda c: (-c["hook_potential"], -int(c["is_natural_start"]), c["start"])
        )

    return candidates
