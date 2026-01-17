"""
Hook/value/topic-aware selector for highlight segments.
"""
from __future__ import annotations

from typing import List, Dict

from modules.clip_candidates import generate_candidates


HOOK_KEYWORDS = [
    "secret",
    "mistake",
    "don't",
    "never",
    "why",
    "how",
    "what",
    "top",
    "ошибка",
    "секрет",
    "никто",
    "почему",
    "как",
    "что",
]
VALUE_MARKERS = [
    "step",
    "steps",
    "tip",
    "tips",
    "advice",
    "first",
    "second",
    "third",
    "because",
    "so",
    "therefore",
    "if",
    "then",
    "шаг",
    "совет",
    "потому",
    "поэтому",
    "если",
    "то",
    "результат",
    "итог",
]
EMOTION_KEYWORDS = [
    "pain",
    "fear",
    "anxious",
    "stress",
    "worried",
    "struggle",
    "frustrated",
    "dream",
    "страх",
    "боюсь",
    "больно",
    "проблем",
    "мечта",
]
COMPLETION_MARKERS = [
    "therefore",
    "in the end",
    "so",
    "finally",
    "поэтому",
    "итог",
    "в итоге",
]


def _count_hits(text: str, keywords: List[str]) -> int:
    lowered = text.lower()
    return sum(1 for word in keywords if word in lowered)


def _hook_score(sentences: List[Dict]) -> tuple[float, str]:
    if not sentences:
        return 0.0, ""
    hook_text = " ".join(sentence["text"] for sentence in sentences[:2]).strip()
    score = 0.0
    reasons = []
    if "?" in hook_text:
        score += 1.5
        reasons.append("question")
    if hook_text.startswith(("why", "how", "what", "почему", "как", "что")):
        score += 1.0
        reasons.append("interrogative")
    if any(char.isdigit() for char in hook_text[:8]):
        score += 1.0
        reasons.append("number")
    hits = _count_hits(hook_text, HOOK_KEYWORDS)
    if hits:
        score += 1.0 + 0.5 * hits
        reasons.append("hook_words")
    return score, ",".join(reasons)


def _value_score(text: str) -> float:
    hits = _count_hits(text, VALUE_MARKERS)
    return 0.8 * hits


def _emotion_score(text: str) -> float:
    hits = _count_hits(text, EMOTION_KEYWORDS)
    return 0.6 * hits


def _completeness_score(text: str, last_sentence: str) -> float:
    lowered = text.lower()
    if any(marker in lowered for marker in COMPLETION_MARKERS):
        return 1.0
    if any(marker in last_sentence.lower() for marker in COMPLETION_MARKERS):
        return 1.0
    return 0.0


def _topic_hint(text: str, max_words: int = 8) -> str:
    tokens = text.split()
    if len(tokens) <= max_words:
        return text
    return " ".join(tokens[:max_words]) + "..."


def _overlap_ratio(a: Dict, b: Dict) -> float:
    overlap = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    duration = max(a["end"] - a["start"], 0.001)
    return overlap / duration


def _token_set(text: str) -> set[str]:
    tokens = [t.strip(".,!?;:()[]\"'").lower() for t in text.split()]
    return {t for t in tokens if t}


def _jaccard(a: str, b: str) -> float:
    set_a = _token_set(a)
    set_b = _token_set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def score_candidate(candidate: Dict, hook_bias: float = 1.0) -> Dict:
    sentences = candidate.get("sentences", [])
    text = candidate.get("text", "")
    hook_sentence = sentences[0]["text"] if sentences else text
    last_sentence = sentences[-1]["text"] if sentences else text

    hook_score, hook_reason = _hook_score(sentences)
    value_score = _value_score(text)
    emotion_score = _emotion_score(text)
    completeness_score = _completeness_score(text, last_sentence)

    length_score = 0.0
    if 12.0 <= candidate["duration"] <= 25.0:
        length_score = 0.8
    elif candidate["duration"] < 10.0:
        length_score = -0.6
    elif candidate["duration"] > 40.0:
        length_score = -0.4

    total = hook_score * hook_bias + value_score + emotion_score + completeness_score + length_score
    reasons: List[str] = []
    if hook_reason:
        reasons.append(f"hook:{hook_reason}")
        total += 0.3
        reasons.append("hook_bonus")
    if value_score:
        reasons.append("value")
    if emotion_score:
        reasons.append("emotion")
    if completeness_score:
        reasons.append("complete")
    if length_score:
        reasons.append("length_pref")

    return {
        **candidate,
        "score": total,
        "hook_sentence": hook_sentence,
        "topic_hint": _topic_hint(hook_sentence),
        "reason": reasons or ["heuristic"],
    }


def select_segments(
    sentences: List[Dict],
    max_clips: int,
    min_dur: float,
    max_dur: float,
    min_sentences: int,
    max_sentences: int,
    hook_bias: float = 1.0,
    score_threshold: float = 0.25,
) -> List[Dict]:
    candidates = generate_candidates(
        sentences,
        min_dur=min_dur,
        max_dur=max_dur,
        min_sentences=min_sentences,
        max_sentences=max_sentences,
    )
    scored = [score_candidate(candidate, hook_bias=hook_bias) for candidate in candidates]
    scored.sort(key=lambda c: (-c["score"], c["duration"]))

    selected: List[Dict] = []
    remaining: List[Dict] = []

    def apply_diversity(candidate: Dict, picks: List[Dict]) -> Dict | None:
        penalty = 0.0
        diversity_penalty = 0.0
        reasons = list(candidate.get("reason", []))
        max_overlap = 0.0
        max_overlap_pick = None
        for pick in picks:
            ratio = _overlap_ratio(candidate, pick)
            if ratio > max_overlap:
                max_overlap = ratio
                max_overlap_pick = pick
            if ratio > 0:
                penalty += 2.0 * ratio
            similarity = _jaccard(candidate.get("text", ""), pick.get("text", ""))
            if similarity >= 0.5:
                diversity_penalty += 0.8
                reasons.append(f"topic_overlap:{similarity:.2f}")
        if max_overlap > 0.5:
            if max_overlap_pick is not None:
                max_overlap_pick["overlap_skipped_count"] = (
                    max_overlap_pick.get("overlap_skipped_count", 0) + 1
                )
            return None
        if penalty or diversity_penalty:
            candidate = {
                **candidate,
                "score": candidate["score"] - penalty - diversity_penalty,
                "reason": reasons + [f"overlap_penalty:{penalty + diversity_penalty:.2f}"],
                "diversity_penalty_value": diversity_penalty,
            }
        else:
            candidate = {
                **candidate,
                "reason": reasons,
                "diversity_penalty_value": 0.0,
            }
        if picks and candidate["score"] <= 0:
            return None
        return candidate

    # PASS1: strict threshold picks
    for cand in scored:
        adjusted = apply_diversity(cand, selected)
        if not adjusted:
            continue
        if adjusted["score"] >= score_threshold:
            selected.append(
                {
                    **adjusted,
                    "low_confidence": False,
                    "overlap_skipped_count": adjusted.get("overlap_skipped_count", 0),
                }
            )
        else:
            remaining.append(adjusted)
        if len(selected) >= max_clips:
            return selected

    # PASS2: fallback picks to fill MaxClips (diversity enforced)
    remaining.sort(key=lambda c: (-c["score"], c["duration"]))
    for cand in remaining:
        if len(selected) >= max_clips:
            break
        adjusted = apply_diversity(cand, selected)
        if not adjusted:
            continue
        reason = list(adjusted.get("reason", []))
        reason.append("below_threshold_fallback")
        selected.append(
            {
                **adjusted,
                "reason": reason,
                "low_confidence": True,
                "overlap_skipped_count": adjusted.get("overlap_skipped_count", 0),
            }
        )

    # PASS3: if still short, relax diversity to always return MaxClips
    if len(selected) < max_clips:
        picked_ids = {item.get("id") for item in selected}
        for cand in scored:
            if len(selected) >= max_clips:
                break
            if cand.get("id") in picked_ids:
                continue
            reason = list(cand.get("reason", []))
            reason.append("below_threshold_fallback")
            reason.append("diversity_relaxed_fallback")
            selected.append(
                {
                    **cand,
                    "reason": reason,
                    "low_confidence": True,
                    "overlap_skipped_count": cand.get("overlap_skipped_count", 0),
                    "diversity_penalty_value": cand.get("diversity_penalty_value", 0.0),
                }
            )

    return selected
