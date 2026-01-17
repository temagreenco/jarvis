"""
Sentence/utterance splitter based on word timestamps.
"""
from __future__ import annotations

from typing import List, Dict


def _ends_sentence(word_text: str) -> bool:
    lowered = word_text.strip().lower()
    if not lowered:
        return False
    if lowered.endswith("..."):
        return True
    return lowered.endswith((".", "!", "?"))


def _join_words(words: List[Dict]) -> str:
    text = " ".join(word["w"] for word in words if word.get("w"))
    for punct in (".", ",", "!", "?", ":", ";"):
        text = text.replace(f" {punct}", punct)
    return text.strip()


def _merge_sentences(left: Dict, right: Dict) -> Dict:
    words = list(left.get("words", [])) + list(right.get("words", []))
    return {
        "id": left["id"],
        "text": _join_words(words),
        "start": float(left["start"]),
        "end": float(right["end"]),
        "words": words,
    }


def _merge_short_fragments(sentences: List[Dict], min_duration: float = 0.6) -> List[Dict]:
    merged: List[Dict] = []
    carry: Dict | None = None
    for sentence in sentences:
        duration = float(sentence["end"]) - float(sentence["start"])
        if duration < min_duration:
            if merged:
                merged[-1] = _merge_sentences(merged[-1], sentence)
            elif carry is None:
                carry = sentence
            else:
                carry = _merge_sentences(carry, sentence)
            continue
        if carry:
            sentence = _merge_sentences(carry, sentence)
            carry = None
        merged.append(sentence)
    if carry:
        if merged:
            merged[-1] = _merge_sentences(merged[-1], carry)
        else:
            merged = [carry]
    return merged


def build_sentences(words: List[Dict], max_gap: float = 0.45) -> List[Dict]:
    ordered = sorted(words, key=lambda w: float(w.get("start", 0.0)))
    sentences: List[Dict] = []
    current_words: List[Dict] = []

    def flush() -> None:
        if not current_words:
            return
        text = _join_words(current_words)
        sentences.append(
            {
                "id": f"sent-{len(sentences) + 1}",
                "text": text,
                "start": float(current_words[0]["start"]),
                "end": float(current_words[-1]["end"]),
                "words": list(current_words),
            }
        )
        current_words.clear()

    for idx, word in enumerate(ordered):
        word_text = (word.get("w") or "").strip()
        if not word_text:
            continue
        current_words.append(
            {
                "start": float(word.get("start", 0.0)),
                "end": float(word.get("end", 0.0)),
                "w": word_text,
            }
        )

        gap_break = False
        if idx + 1 < len(ordered):
            next_start = float(ordered[idx + 1].get("start", current_words[-1]["end"]))
            gap = next_start - float(word.get("end", next_start))
            if gap > max_gap:
                gap_break = True

        if _ends_sentence(word_text) or gap_break:
            flush()

    flush()
    return _merge_short_fragments(sentences)
