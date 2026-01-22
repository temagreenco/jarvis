"""
Hook/value/topic-aware selector for highlight segments.
"""
from __future__ import annotations

from typing import List, Dict, Tuple, Optional

from modules.clip_candidates import generate_candidates


HOOK_KEYWORDS = [
    # English - Questions & Curiosity
    "secret",
    "mistake",
    "don't",
    "never",
    "why",
    "how",
    "what",
    "top",
    "truth",
    "lie",
    "myth",
    "reveal",
    "nobody",
    "hidden",
    # English - Urgency & Action
    "stop",
    "warning",
    "avoid",
    "immediately",
    # English - Intensity & Superlatives
    "biggest",
    "worst",
    "best",
    "only",
    "most",
    "number one",
    "#1",
    # English - Emotional Triggers
    "shocked",
    "surprising",
    "crazy",
    "insane",
    "unbelievable",
    # Russian
    "ошибка",
    "секрет",
    "никто",
    "почему",
    "как",
    "что",
    "срочно",
    "самая большая",
    "худшая",
    "лучшая",
    # Hebrew - Core hooks
    "הבעיה היא",
    "מה שלא אומרים לכם",
    "תקשיבו טוב",
    "האמת היא",
    "אף אחד לא",
    "אסור",
    "אל תעשו",
    # Hebrew - Urgency & Intensity
    "עכשיו",
    "תפסיקו",
    "הכי גדול",
    "הכי גרוע",
    "הכי טוב",
    "לא תאמינו",
    "מטורף",
]
HOOK_PHRASES = [
    # English - High-impact openers
    "the truth is",
    "what they don't tell you",
    "listen carefully",
    "here's the thing",
    "let me explain",
    "i was wrong",
    "this changes everything",
    "stop doing this",
    "biggest mistake",
    "game changer",
    "wish i knew",
    "changed my life",
    "blew my mind",
    "can't believe",
    "nobody talks about",
    "unpopular opinion",
    "hot take",
    "if you're not",
    "the reason why",
    "here's why",
    # Russian
    "вот почему",
    "самая большая ошибка",
    "никто не говорит",
    "изменило мою жизнь",
    # Hebrew
    "האמת היא",
    "מה שלא אומרים לכם",
    "תקשיבו טוב",
    "הבעיה היא",
    "תשמעו רגע",
    "הטעות הכי גדולה",
    "שינה לי את החיים",
    "אף אחד לא מדבר על",
    "הסיבה שבגללה",
]
INTRO_PHRASES = [
    "hey",
    "welcome",
    "today we will",
    "today we're",
    "today i will",
    "hi",
    "hello",
    "היי כולם",
    "שלום",
    "ברוכים הבאים",
    "אז היום",
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
    "לסיכום",
    "בסוף",
    "בסופו של דבר",
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
    """Score hook quality - prioritizes first sentence heavily."""
    if not sentences:
        return 0.0, ""
    # First sentence is weighted 2x more than second
    first_text = sentences[0].get("text", "").strip()
    first_score, first_reasons = score_hook_text(first_text)

    if len(sentences) >= 2:
        second_text = sentences[1].get("text", "").strip()
        second_score, _ = score_hook_text(second_text)
        # First sentence weighted 2x, second 0.5x
        combined_score = first_score * 2.0 + second_score * 0.5
    else:
        combined_score = first_score * 2.0

    return combined_score, first_reasons


def score_hook_text(text: str) -> tuple[float, str]:
    """Score a single text for hook quality."""
    hook_text = (text or "").strip()
    if not hook_text:
        return 0.0, ""
    lowered = hook_text.lower()
    score = 0.0
    reasons = []

    # Question mark - strong hook indicator
    if "?" in hook_text:
        score += 1.5
        reasons.append("question")

    # Interrogative starters (English, Russian, Hebrew)
    interrogatives = (
        "why", "how", "what", "when", "who", "which",
        "почему", "как", "что", "когда", "кто",
        "למה", "איך", "מה", "מתי", "מי",
    )
    if lowered.startswith(interrogatives):
        score += 1.0
        reasons.append("interrogative")

    # Numbers in first 10 chars (listicles perform well)
    if any(char.isdigit() for char in hook_text[:10]):
        score += 1.0
        reasons.append("number")

    # Check for high-impact phrases
    phrase_hits = sum(1 for phrase in HOOK_PHRASES if phrase in lowered)
    if phrase_hits:
        score += 1.2 * phrase_hits
        reasons.append("hook_phrase")

    # Check for hook keywords
    keyword_hits = _count_hits(hook_text, HOOK_KEYWORDS)
    if keyword_hits:
        score += 0.8 + 0.4 * keyword_hits
        reasons.append("hook_words")

    # Intensity boosters - superlatives and emphasis
    intensity_words = ["never", "always", "every", "all", "biggest", "worst", "best", "only", "must"]
    intensity_hits = sum(1 for w in intensity_words if w in lowered)
    if intensity_hits:
        score += 0.5 * intensity_hits
        reasons.append("intensity")

    # Exclamation - shows energy
    if "!" in hook_text:
        score += 0.3
        reasons.append("exclamation")

    # Penalty for weak/generic intros
    if is_intro_text(hook_text):
        score -= 1.5
        reasons.append("weak_intro_penalty")

    return score, ",".join(reasons)


def is_intro_text(text: str) -> bool:
    """Check if text is a weak intro (greetings, generic openers).

    Uses word boundary matching to avoid false positives like 'hi' in 'this'.
    """
    lowered = (text or "").strip().lower()
    if not lowered:
        return True

    # Split into words for accurate matching
    words = set(lowered.split())

    # Single-word intros must match exactly as words
    single_word_intros = {"hey", "hi", "hello", "welcome", "שלום"}
    if words & single_word_intros:
        # Only count if it's at the start
        first_word = lowered.split()[0] if lowered.split() else ""
        if first_word in single_word_intros:
            return True

    # Multi-word phrases use substring match (more reliable)
    multi_word_intros = [
        "today we will",
        "today we're",
        "today i will",
        "היי כולם",
        "ברוכים הבאים",
        "אז היום",
    ]
    return any(phrase in lowered for phrase in multi_word_intros)


def _value_score(text: str) -> float:
    hits = _count_hits(text, VALUE_MARKERS)
    return 0.8 * hits


def _emotion_score(text: str) -> float:
    hits = _count_hits(text, EMOTION_KEYWORDS)
    return 0.6 * hits


def _completeness_score(text: str, last_sentence: str, ends_with_punctuation: bool) -> float:
    lowered = text.lower()
    if any(marker in lowered for marker in COMPLETION_MARKERS):
        return 1.0
    if any(marker in last_sentence.lower() for marker in COMPLETION_MARKERS):
        return 1.0
    if ends_with_punctuation:
        return 0.6
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


def _join_sentences(sentences: List[Dict]) -> str:
    return " ".join(sentence.get("text", "") for sentence in sentences).strip()


def _join_words(sentences: List[Dict]) -> List[Dict]:
    words: List[Dict] = []
    for sentence in sentences:
        words.extend(sentence.get("words", []) or [])
    return words


def _ends_with_punctuation(text: str) -> bool:
    trimmed = (text or "").strip()
    if not trimmed:
        return False
    if trimmed.endswith("..."):
        return True
    return trimmed.endswith((".", "!", "?"))


def _sentence_complete(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    if any(marker in lowered for marker in COMPLETION_MARKERS):
        return True
    return _ends_with_punctuation(lowered)


def _length_preference_score(
    duration: float,
    prefer_min: float,
    prefer_max: float,
    target_duration: float,
    max_duration_sec: float,
) -> float:
    if duration <= 0.0:
        return -0.5
    if duration < 18.0:
        return -1.2
    if prefer_max <= prefer_min:
        return 0.0
    if duration < prefer_min:
        span = max(prefer_min - 18.0, 1.0)
        scale = min(max((prefer_min - duration) / span, 0.0), 1.0)
        return -0.6 * scale
    if duration <= prefer_max:
        span = max((prefer_max - prefer_min) / 2.0, 1.0)
        distance = min(abs(duration - target_duration) / span, 1.0)
        return 1.2 - (1.2 * distance)
    if duration <= 45.0:
        return -0.1
    if duration <= max_duration_sec:
        return -0.4
    return -0.8


def _token_set(text: str) -> set[str]:
    tokens = [t.strip(".,!?;:()[]\"'").lower() for t in text.split()]
    return {t for t in tokens if t}


def _jaccard(a: str, b: str) -> float:
    set_a = _token_set(a)
    set_b = _token_set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _token_freq(text: str) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for token in _token_set(text):
        freq[token] = freq.get(token, 0) + 1
    return freq


def _cosine_similarity(a: str, b: str) -> float:
    freq_a = _token_freq(a)
    freq_b = _token_freq(b)
    if not freq_a or not freq_b:
        return 0.0
    dot = 0.0
    for token, count in freq_a.items():
        dot += count * freq_b.get(token, 0)
    norm_a = sum(v * v for v in freq_a.values()) ** 0.5
    norm_b = sum(v * v for v in freq_b.values()) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _energy_score(
    speech_rate_wps: float,
    pause_ratio: float,
    rms_db_mean: Optional[float],
    rms_db_std: Optional[float],
    zcr_mean: Optional[float],
    f0_hz_std: Optional[float],
) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    if speech_rate_wps >= 3.0:
        score += 0.6
        reasons.append("fast_speech")
    if pause_ratio <= 0.15:
        score += 0.4
        reasons.append("low_pause")
    if speech_rate_wps <= 1.2:
        score -= 0.2
        reasons.append("slow_speech")
    if rms_db_mean is not None:
        if rms_db_mean > -25.0:
            score += 0.4
            reasons.append("loud_audio")
        elif rms_db_mean < -40.0:
            score -= 0.3
            reasons.append("quiet_audio")
    if rms_db_std is not None and rms_db_std >= 3.0:
        score += 0.2
        reasons.append("dynamic_audio")
    if zcr_mean is not None:
        if zcr_mean > 200.0:
            score += 0.2
            reasons.append("animated_audio")
        elif zcr_mean < 50.0:
            score -= 0.1
            reasons.append("flat_audio")
    if f0_hz_std is not None:
        if f0_hz_std >= 20.0:
            score += 0.3
            reasons.append("pitch_variation")
        elif f0_hz_std <= 5.0:
            score -= 0.1
            reasons.append("flat_pitch")
    return score, reasons


def _cluster_candidates(scored: List[Dict], similarity_threshold: float = 0.6) -> None:
    clusters: List[Dict] = []
    for candidate in scored:
        assigned = False
        for cluster in clusters:
            sim = _cosine_similarity(candidate.get("text", ""), cluster.get("text", ""))
            if sim >= similarity_threshold:
                candidate["cluster_id"] = cluster["id"]
                assigned = True
                break
        if not assigned:
            cluster_id = f"cluster-{len(clusters) + 1}"
            clusters.append({"id": cluster_id, "text": candidate.get("text", "")})
            candidate["cluster_id"] = cluster_id


def _audio_stats_for_window(
    features: List[Dict],
    start: float,
    end: float,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    if not features:
        return None, None, None
    values = [f for f in features if f["start"] < end and f["end"] > start]
    if not values:
        return None, None, None
    rms_vals = [float(f["rms_db"]) for f in values if f.get("rms_db") is not None]
    zcr_vals = [float(f["zcr"]) for f in values if f.get("zcr") is not None]
    f0_vals = [float(f["f0_hz"]) for f in values if f.get("f0_hz") is not None]
    if not rms_vals:
        return None, None, None, None
    mean = sum(rms_vals) / len(rms_vals)
    variance = sum((v - mean) ** 2 for v in rms_vals) / len(rms_vals)
    std = variance ** 0.5
    zcr_mean = sum(zcr_vals) / len(zcr_vals) if zcr_vals else None
    f0_std = None
    if f0_vals:
        f0_mean = sum(f0_vals) / len(f0_vals)
        f0_std = (sum((v - f0_mean) ** 2 for v in f0_vals) / len(f0_vals)) ** 0.5
    return mean, std, zcr_mean, f0_std
def score_candidate(
    candidate: Dict,
    hook_bias: float = 1.0,
    target_duration_sec: float = 32.0,
    prefer_duration_min_sec: float = 25.0,
    prefer_duration_max_sec: float = 40.0,
    max_duration_sec: float = 70.0,
) -> Dict:
    sentences = candidate.get("sentences", [])
    text = candidate.get("text", "")
    hook_sentence = sentences[0]["text"] if sentences else text
    last_sentence = sentences[-1]["text"] if sentences else text

    hook_score, hook_reason = _hook_score(sentences)
    value_score = _value_score(text)
    emotion_score = _emotion_score(text)
    completeness_score = _completeness_score(
        text,
        last_sentence,
        bool(candidate.get("ends_with_punctuation", False)),
    )
    energy_score, energy_reasons = _energy_score(
        float(candidate.get("speech_rate_wps", 0.0)),
        float(candidate.get("pause_ratio", 0.0)),
        candidate.get("audio_rms_db_mean"),
        candidate.get("audio_rms_db_std"),
        candidate.get("audio_zcr_mean"),
        candidate.get("audio_f0_hz_std"),
    )

    length_score = _length_preference_score(
        float(candidate["duration"]),
        prefer_duration_min_sec,
        prefer_duration_max_sec,
        target_duration_sec,
        max_duration_sec,
    )

    total = hook_score * hook_bias + value_score + emotion_score + completeness_score + energy_score + length_score
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
    if energy_score:
        reasons.extend(energy_reasons)
    if length_score:
        reasons.append("length_pref")

    return {
        **candidate,
        "score": total,
        "hook_sentence": hook_sentence,
        "topic_hint": _topic_hint(hook_sentence),
        "reason": reasons or ["heuristic"],
    }


def extend_segment_to_completion(
    segment: Dict,
    sentences: List[Dict],
    target_duration_sec: float,
    max_duration_sec: float,
    silence_gap_sec: float = 1.0,
) -> Dict:
    idx_range = segment.get("sentences_idx_range")
    if not idx_range:
        return segment
    start_idx, end_idx = idx_range
    if end_idx >= len(sentences) - 1:
        return segment
    start = float(segment["start"])
    current_end = float(segment["end"])
    duration = current_end - start
    if duration >= target_duration_sec:
        return segment

    extended_end = current_end
    extended_end_idx = end_idx
    for next_idx in range(end_idx + 1, len(sentences)):
        next_sentence = sentences[next_idx]
        gap = float(next_sentence.get("start", extended_end)) - extended_end
        if gap >= silence_gap_sec:
            break
        next_end = float(next_sentence.get("end", extended_end))
        if next_end - start > max_duration_sec:
            break
        extended_end = next_end
        extended_end_idx = next_idx
        duration = extended_end - start
        if duration >= target_duration_sec or _sentence_complete(next_sentence.get("text", "")):
            break

    if extended_end_idx == end_idx:
        return segment

    window = sentences[start_idx : extended_end_idx + 1]
    words = _join_words(window)
    updated = {
        **segment,
        "end": extended_end,
        "duration": extended_end - start,
        "sentences_idx_range": (start_idx, extended_end_idx),
        "sentences": window,
        "text": _join_sentences(window),
        "words": words,
        "word_count": len(words),
        "ends_with_punctuation": _ends_with_punctuation(window[-1].get("text", "")),
        "extended_to_completion": True,
    }
    return updated


def select_segments(
    sentences: List[Dict],
    max_clips: int,
    min_dur: float,
    max_dur: float,
    min_sentences: int,
    max_sentences: int,
    hook_bias: float = 1.0,
    score_threshold: float = 0.25,
    min_avg_word_confidence: float = 0.7,
    diversity_radius_s: float = 0.0,
    audio_features: Optional[List[Dict]] = None,
    target_duration_sec: float = 32.0,
    prefer_duration_min_sec: float = 25.0,
    prefer_duration_max_sec: float = 40.0,
    max_duration_sec: float = 70.0,
) -> List[Dict]:
    candidates = generate_candidates(
        sentences,
        min_dur=min_dur,
        max_dur=max_dur,
        min_sentences=min_sentences,
        max_sentences=max_sentences,
    )
    filtered = []
    for candidate in candidates:
        avg_conf = candidate.get("avg_word_confidence")
        if avg_conf is not None and avg_conf < min_avg_word_confidence:
            continue
        if audio_features:
            rms_mean, rms_std, zcr_mean, f0_std = _audio_stats_for_window(
                audio_features, float(candidate["start"]), float(candidate["end"])
            )
            candidate["audio_rms_db_mean"] = rms_mean
            candidate["audio_rms_db_std"] = rms_std
            candidate["audio_zcr_mean"] = zcr_mean
            candidate["audio_f0_hz_std"] = f0_std
        filtered.append(candidate)

    scored = [
        score_candidate(
            candidate,
            hook_bias=hook_bias,
            target_duration_sec=target_duration_sec,
            prefer_duration_min_sec=prefer_duration_min_sec,
            prefer_duration_max_sec=prefer_duration_max_sec,
            max_duration_sec=max_duration_sec,
        )
        for candidate in filtered
    ]
    scored.sort(key=lambda c: (-c["score"], c["duration"]))
    _cluster_candidates(scored)

    selected: List[Dict] = []
    remaining: List[Dict] = []

    def apply_diversity(candidate: Dict, picks: List[Dict]) -> Dict | None:
        penalty = 0.0
        diversity_penalty = 0.0
        reasons = list(candidate.get("reason", []))
        max_overlap = 0.0
        max_overlap_pick = None
        for pick in picks:
            if diversity_radius_s and abs(candidate["start"] - pick["start"]) < diversity_radius_s:
                return None
            if candidate.get("cluster_id") and candidate.get("cluster_id") == pick.get("cluster_id"):
                return None
            ratio = _overlap_ratio(candidate, pick)
            if ratio > max_overlap:
                max_overlap = ratio
                max_overlap_pick = pick
            if ratio > 0:
                penalty += 2.0 * ratio
            similarity = _cosine_similarity(candidate.get("text", ""), pick.get("text", ""))
            if similarity >= 0.55:
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
