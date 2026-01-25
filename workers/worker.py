"""
Background worker that processes jobs from Redis and updates Postgres.
"""
from __future__ import annotations

import json
import os
import time
import tempfile
import subprocess
import math
import wave
import audioop
import signal
import threading
from array import array
import numpy as np
from typing import Any, Dict

import httpx

from modules.db_models import Job, db_session, init_db, validate_status_transition
from modules.job_queue import JobQueue
from modules.minio_client import get_s3_client
from modules.video_cutter import cut_segments
from modules.transcribe import transcribe_to_segments
from modules.segment_selector import (
    select_segments,
    score_hook_text,
    is_intro_text,
    extend_segment_to_completion,
)
from modules.reels_renderer import render_reels
from modules.sentence_splitter import build_sentences
from modules.silence_detect import detect_silences, snap_segment_to_silence
from utils.logger import get_logger

logger = get_logger("worker")

MINIO_BUCKET = os.getenv("MINIO_BUCKET", "jarvis")
_shutdown_event = threading.Event()


def _handle_shutdown(signum, frame) -> None:
    logger.info(f"Shutdown signal received ({signum}), stopping after current job.")
    _shutdown_event.set()


def update_progress(job_id: str, stage: str, progress: float) -> None:
    with db_session() as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.progress = float(progress)
        job.progress_stage = stage


class ProgressTracker:
    def __init__(self, job_id: str) -> None:
        self._job_id = job_id

    def update(self, stage: str, progress: float) -> None:
        clamped = max(0.0, min(100.0, float(progress)))
        update_progress(self._job_id, stage, clamped)


def get_media_duration(path: str) -> float:
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            text=True,
        ).strip()
        return float(output)
    except Exception:
        return 0.0


def upload_json(key: str, payload: Dict[str, Any]) -> None:
    client = get_s3_client()
    if not client:
        raise RuntimeError("S3 client is not configured")
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    client.put_object(Bucket=MINIO_BUCKET, Key=key, Body=body, ContentType="application/json")


def load_transcript(input_data: Dict[str, Any], work_dir: str) -> tuple[list[dict], list[dict]]:
    transcript_payload = input_data.get("transcript")
    transcript_key = input_data.get("transcript_s3_key")

    if transcript_key:
        client = get_s3_client()
        if not client:
            raise RuntimeError("S3 client is not configured")
        transcript_path = os.path.join(work_dir, "transcript.json")
        client.download_file(MINIO_BUCKET, transcript_key, transcript_path)
        with open(transcript_path, "r", encoding="utf-8") as handle:
            transcript_payload = json.load(handle)

    if isinstance(transcript_payload, dict):
        segments = transcript_payload.get("segments") or []
        words = transcript_payload.get("words") or []
        return list(segments), list(words)

    return [], []


def download_input(job: Job, work_dir: str) -> str:
    input_data = job.input_data or {}
    input_s3_key = input_data.get("input_s3_key")
    source_url = input_data.get("source_url")
    input_path = os.path.join(work_dir, "input.mp4")

    if input_s3_key:
        client = get_s3_client()
        if not client:
            raise RuntimeError("S3 client is not configured")
        client.download_file(MINIO_BUCKET, input_s3_key, input_path)
        return input_path

    if source_url:
        with httpx.stream("GET", source_url, timeout=60.0) as response:
            response.raise_for_status()
            with open(input_path, "wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return input_path

    raise ValueError("Missing input_s3_key or source_url")


def validate_segments(segments: list[dict]) -> list[dict]:
    if not segments:
        raise ValueError("segments must be provided")
    normalized: list[dict] = []
    for segment in segments:
        seg_id = str(segment.get("id"))
        start = float(segment.get("start"))
        end = float(segment.get("end"))
        if start < 0 or end <= start:
            raise ValueError(f"Invalid segment bounds for {seg_id}")
        normalized.append({"id": seg_id, "start": start, "end": end})
    return normalized


def collect_words_in_window(
    words: list[dict], start: float, end: float, epsilon: float = 0.001
) -> list[dict]:
    if not words:
        return []
    selected = [
        w
        for w in words
        if float(w.get("start", 0.0)) <= end + epsilon
        and float(w.get("end", 0.0)) >= start - epsilon
    ]
    return sorted(selected, key=lambda w: float(w.get("start", 0.0)))


def avg_word_confidence(words: list[dict]) -> float | None:
    scores = [float(w.get("p")) for w in words if w.get("p") is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def min_word_confidence(words: list[dict]) -> float | None:
    scores = [float(w.get("p")) for w in words if w.get("p") is not None]
    if not scores:
        return None
    return min(scores)


def pause_ratio(words: list[dict], duration: float) -> float:
    if duration <= 0.0 or len(words) < 2:
        return 0.0
    ordered = sorted(words, key=lambda w: float(w.get("start", 0.0)))
    total_gap = 0.0
    for idx in range(len(ordered) - 1):
        gap = float(ordered[idx + 1].get("start", 0.0)) - float(ordered[idx].get("end", 0.0))
        if gap > 0:
            total_gap += gap
    return min(total_gap / duration, 1.0)


def extract_audio_features(media_path: str, work_dir: str, window_ms: int = 200) -> list[dict]:
    wav_path = os.path.join(work_dir, "audio_mono.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        media_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        wav_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.warning(f"Audio feature extraction failed: {exc}")
        return []

    features: list[dict] = []
    try:
        with wave.open(wav_path, "rb") as wav:
            rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            window_frames = max(1, int(rate * window_ms / 1000))
            index = 0
            while True:
                frames = wav.readframes(window_frames)
                if not frames:
                    break
                if sample_width != 2:
                    frames = audioop.lin2lin(frames, sample_width, 2)
                    sample_width = 2
                rms = audioop.rms(frames, sample_width)
                max_rms = float(2 ** (8 * sample_width - 1))
                rms_db = -90.0 if rms <= 0 else 20.0 * math.log10(rms / max_rms)
                samples = array("h")
                samples.frombytes(frames)
                samples_np = np.array(samples, dtype=np.float32)
                if samples_np.size:
                    samples_np -= samples_np.mean()
                f0_hz = None
                if rate and samples_np.size >= int(rate * 0.03):
                    fmin = 70.0
                    fmax = 400.0
                    lag_min = int(rate / fmax)
                    lag_max = int(rate / fmin)
                    if lag_max > lag_min and lag_max < samples_np.size:
                        corr = np.correlate(samples_np, samples_np, mode="full")
                        corr = corr[corr.size // 2 :]
                        corr[:lag_min] = 0
                        segment = corr[lag_min:lag_max]
                        if segment.size:
                            peak = int(np.argmax(segment)) + lag_min
                            if peak > 0 and corr[peak] > 0:
                                f0_hz = float(rate / peak)
                crossings = 0
                for i in range(1, len(samples)):
                    if (samples[i - 1] >= 0 and samples[i] < 0) or (
                        samples[i - 1] < 0 and samples[i] >= 0
                    ):
                        crossings += 1
                duration = len(samples) / rate if rate else 0.0
                zcr = crossings / duration if duration > 0 else 0.0
                start = index * window_frames / rate if rate else 0.0
                end = (index * window_frames + len(samples)) / rate if rate else start
                features.append(
                    {
                        "start": start,
                        "end": end,
                        "rms_db": round(rms_db, 3),
                        "zcr": round(zcr, 3),
                        "f0_hz": round(f0_hz, 3) if f0_hz is not None else None,
                    }
                )
                index += 1
    except Exception as exc:
        logger.warning(f"Audio feature parse failed: {exc}")
        return []
    return features


def audio_rms_for_window(features: list[dict], start: float, end: float) -> float | None:
    if not features:
        return None
    values = [f for f in features if f["start"] < end and f["end"] > start]
    if not values:
        return None
    rms_vals = [float(f["rms_db"]) for f in values if f.get("rms_db") is not None]
    if not rms_vals:
        return None
    return sum(rms_vals) / len(rms_vals)


def pick_hook_start(
    candidate: Dict,
    window_sec: float,
    min_duration: float,
    audio_features: list[dict] | None = None,
    min_rms_db: float | None = None,
) -> tuple[float, str, str]:
    sentences = candidate.get("sentences") or []
    if not sentences:
        return float(candidate["start"]), "", ""
    clip_start = float(candidate["start"])
    clip_end = float(candidate["end"])
    best_score = 0.0
    best_text = ""
    best_reason = ""
    best_start = clip_start
    window_end = clip_start + window_sec
    for sentence in sentences:
        sent_start = float(sentence.get("start", clip_start))
        sent_end = float(sentence.get("end", sent_start))
        if sent_start > window_end:
            break
        text = sentence.get("text", "") or ""
        if is_intro_text(text):
            continue
        if audio_features and min_rms_db is not None:
            rms_mean = audio_rms_for_window(audio_features, sent_start, sent_end)
            if rms_mean is None or rms_mean < min_rms_db:
                continue
        score, reason = score_hook_text(text)
        if score > best_score:
            best_score = score
            best_text = text.strip()
            best_reason = reason
            best_start = sent_start
    if best_score <= 0.0:
        return clip_start, "", ""
    if (clip_end - best_start) < min_duration:
        return clip_start, "", ""
    return best_start, best_text, best_reason


def worker_loop(poll_interval: float = 1.0) -> None:
    init_db()
    queue = JobQueue()
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    logger.info("Worker started, waiting for jobs...")

    while True:
        if _shutdown_event.is_set():
            logger.info("Shutdown requested, exiting worker loop.")
            break
        job_id = queue.dequeue(timeout=5)
        if not job_id:
            time.sleep(poll_interval)
            continue

        logger.info(f"Processing job {job_id}")
        with db_session() as session:
            job = session.get(Job, job_id)
            if not job:
                logger.warning(f"Job {job_id} not found")
                continue
            if job.status == "completed":
                logger.info(f"Job {job_id} already completed, skipping.")
                continue
            if not validate_status_transition(job.status, "processing"):
                logger.warning(
                    f"Job {job_id} invalid transition {job.status} -> processing, skipping."
                )
                continue
            job.status = "processing"
            job.progress = 0.0
            job.progress_stage = "starting"
        tracker = ProgressTracker(job_id)

        try:
            with db_session() as session:
                job = session.get(Job, job_id)
                input_data = job.input_data or {}
                task = input_data.get("task") or "cut"
                mode = input_data.get("mode") or "accurate"
                if mode not in ("fast", "accurate"):
                    mode = "accurate"

                with tempfile.TemporaryDirectory() as work_dir:
                    tracker.update("downloading_input", 5.0)
                    input_path = download_input(job, work_dir)
                    clips_dir = os.path.join(work_dir, "clips")

                    transcript_segments = []
                    transcript_words: list[dict] = []
                    audio_features: list[dict] = []
                    segment_meta: list[dict] = []
                    selected = []
                    segments = []

                    if task == "cut":
                        boundary_mode = input_data.get("boundary_mode") or "sentence"
                        render_mode = input_data.get("render_mode") or "original"
                        track_mode = input_data.get("track_mode") or "none"
                        tracker.update("validating_segments", 15.0)
                        segments = validate_segments(input_data.get("segments", []))
                    elif task == "auto_clips":
                        auto_params = input_data.get("auto_clips") or {}
                        max_clips = int(auto_params.get("max_clips", 3))
                        min_duration = float(auto_params.get("min_duration", 12))
                        max_duration = float(auto_params.get("max_duration", 45))
                        max_duration_sec = float(auto_params.get("max_duration_sec", 60.0))
                        target_duration_sec = float(auto_params.get("target_duration_sec", 32))
                        prefer_duration_min_sec = float(auto_params.get("prefer_duration_min_sec", 25))
                        prefer_duration_max_sec = float(auto_params.get("prefer_duration_max_sec", 40))
                        min_sentences = int(auto_params.get("min_sentences", 4))
                        max_sentences = int(auto_params.get("max_sentences", 12))
                        hook_bias = float(auto_params.get("hook_bias", 1.0))
                        score_threshold = float(auto_params.get("score_threshold", 0.25))
                        min_avg_word_conf = float(auto_params.get("min_avg_word_confidence", 0.7))
                        diversity_radius_s = float(auto_params.get("diversity_radius_s", 0.0))
                        language = auto_params.get("language")
                        if isinstance(language, str) and not language.strip():
                            language = None
                        boundary_mode = input_data.get("boundary_mode") or "word"
                        render_mode = input_data.get("render_mode") or "reels"
                        track_mode = input_data.get("track_mode") or ("face" if render_mode == "reels" else "none")

                        hook_first_cutting = bool(input_data.get("hook_first_cutting", False))
                        hook_window_sec = float(input_data.get("hook_window_sec", 6.0))
                        hook_min_rms_db = input_data.get("hook_min_rms_db")
                        if hook_min_rms_db is not None:
                            hook_min_rms_db = float(hook_min_rms_db)

                        enable_extend_to_completion = bool(
                            auto_params.get("enable_extend_to_completion", True)
                        )
                        sentence_max_gap = float(auto_params.get("sentence_max_gap", 0.9))
                        extend_silence_gap_sec = float(
                            auto_params.get("extend_silence_gap_sec", 1.0)
                        )

                        audio_features = extract_audio_features(input_path, work_dir)
                        transcript_segments, transcript_words = load_transcript(input_data, work_dir)
                        if transcript_segments or transcript_words:
                            tracker.update("using_cached_transcript", 20.0)
                        else:
                            def transcribe_progress(idx: int, ratio: float) -> None:
                                progress = 20.0 + 20.0 * ratio
                                tracker.update("transcribing", progress)
                                if idx % 10 == 0:
                                    logger.info(f"Transcribing chunk {idx}")

                            tracker.update("transcribing", 20.0)
                            transcript_segments, transcript_words = transcribe_to_segments(
                                input_path, language=language, progress_callback=transcribe_progress
                            )
                        media_duration = get_media_duration(input_path)
                        if 0 < media_duration < 60.0:
                            max_clips = max(1, min(max_clips, 3))
                        tracker.update("building_sentences", 30.0)
                        sentences = (
                            build_sentences(transcript_words, max_gap=sentence_max_gap)
                            if transcript_words
                            else [
                                {
                                    "id": f"sent-{idx + 1}",
                                    "text": seg["text"],
                                    "start": seg["start"],
                                    "end": seg["end"],
                                    "words": [],
                                }
                                for idx, seg in enumerate(transcript_segments)
                            ]
                        )
                        tracker.update("selecting_segments", 40.0)
                        selected = select_segments(
                            sentences,
                            max_clips,
                            min_duration,
                            max_duration_sec,
                            min_sentences,
                            max_sentences,
                            hook_bias=hook_bias,
                            score_threshold=score_threshold,
                            min_avg_word_confidence=min_avg_word_conf,
                            diversity_radius_s=diversity_radius_s,
                            audio_features=audio_features,
                            target_duration_sec=target_duration_sec,
                            prefer_duration_min_sec=prefer_duration_min_sec,
                            prefer_duration_max_sec=prefer_duration_max_sec,
                            max_duration_sec=max_duration_sec,
                        )
                        if not selected:
                            raise RuntimeError("No segments selected from transcript")
                        if enable_extend_to_completion:
                            selected = [
                                extend_segment_to_completion(
                                    seg,
                                    sentences,
                                    target_duration_sec=target_duration_sec,
                                    max_duration_sec=max_duration_sec,
                                    silence_gap_sec=extend_silence_gap_sec,
                                )
                                for seg in selected
                            ]
                        segments = []
                        segment_meta = []
                        for idx, s in enumerate(selected):
                            clip_start = float(s["start"])
                            clip_end = float(s["end"])
                            original_start = clip_start
                            hook_first_used = False
                            hook_first_text = ""
                            hook_first_reason = ""
                            hook_first_start = None
                            if hook_first_cutting:
                                hook_start, hook_text, hook_reason = pick_hook_start(
                                    s,
                                    hook_window_sec,
                                    min_duration,
                                    audio_features=audio_features,
                                    min_rms_db=hook_min_rms_db,
                                )
                                if hook_text and hook_start > clip_start:
                                    hook_first_used = True
                                    hook_first_text = hook_text
                                    hook_first_reason = hook_reason
                                    hook_first_start = hook_start
                                    clip_start = hook_start
                                    logger.info(
                                        f"HOOK-FIRST clip-{idx + 1} start shifted: "
                                        f"{original_start:.2f} -> {clip_start:.2f} | "
                                        f"reason={hook_first_reason} | text='{hook_first_text}'"
                                    )
                                else:
                                    logger.info(
                                        f"HOOK-FIRST clip-{idx + 1} no hook found in first "
                                        f"{hook_window_sec:.1f}s"
                                    )
                            clip_words = collect_words_in_window(transcript_words, clip_start, clip_end)
                            first_word = clip_words[0] if clip_words else None
                            last_word = clip_words[-1] if clip_words else None
                            # Note: boundary_mode word will be applied AFTER snapping to silence
                            # This ensures we get the best of both: silence boundaries + word precision
                            # hook_first has priority and will be respected in the final boundary_mode step
                            segments.append(
                                {
                                    "id": f"clip-{idx + 1}",
                                    "start": clip_start,
                                    "end": clip_end,
                                }
                            )
                            clip_text = " ".join(w.get("w", "") for w in clip_words).strip()
                            clip_duration = max(clip_end - clip_start, 0.001)
                            avg_conf = avg_word_confidence(clip_words)
                            min_conf = min_word_confidence(clip_words)
                            speech_rate_wps = len(clip_words) / clip_duration
                            pause_ratio_value = pause_ratio(clip_words, clip_duration)
                            leading_silence = 0.0
                            trailing_silence = 0.0
                            if first_word:
                                leading_silence = max(0.0, min(0.5, float(first_word["start"]) - clip_start))
                            if last_word:
                                trailing_silence = max(0.0, min(0.5, clip_end - float(last_word["end"])))
                            ends_with_punctuation = False
                            if clip_text:
                                ends_with_punctuation = clip_text.rstrip().endswith((".", "!", "?", "…"))
                            segment_meta.append(
                                {
                                    "clip_text": clip_text,
                                    "first_word": {
                                        "w": first_word.get("w"),
                                        "start": first_word.get("start"),
                                    }
                                    if first_word
                                    else None,
                                    "last_word": {
                                        "w": last_word.get("w"),
                                        "end": last_word.get("end"),
                                    }
                                    if last_word
                                    else None,
                                    "words": clip_words,
                                    "word_count": len(clip_words),
                                    "avg_word_confidence": avg_conf,
                                    "min_word_confidence": min_conf,
                                    "speech_rate_wps": round(speech_rate_wps, 3),
                                    "pause_ratio": round(pause_ratio_value, 3),
                                    "audio_rms_db_mean": s.get("audio_rms_db_mean"),
                                    "audio_rms_db_std": s.get("audio_rms_db_std"),
                                    "audio_zcr_mean": s.get("audio_zcr_mean"),
                                    "audio_f0_hz_std": s.get("audio_f0_hz_std"),
                                    "leading_silence_s": round(leading_silence, 3),
                                    "trailing_silence_s": round(trailing_silence, 3),
                                    "ends_with_punctuation": ends_with_punctuation,
                                    "has_hook": bool(s.get("hook_sentence")),
                                    "score": s.get("score", 0.0),
                                    "reason": s.get("reason") or [],
                                    "hook_sentence": s.get("hook_sentence", ""),
                                    "topic_hint": s.get("topic_hint", ""),
                                    "hook_first_used": hook_first_used,
                                    "hook_first_text": hook_first_text,
                                    "hook_first_reason": hook_first_reason,
                                    "hook_first": {
                                        "enabled": bool(hook_first_cutting),
                                        "used": hook_first_used,
                                        "window_sec": float(hook_window_sec),
                                        "min_rms_db": hook_min_rms_db if hook_min_rms_db is not None else None,
                                        "start_sec": float(hook_first_start)
                                        if hook_first_start is not None
                                        else None,
                                        "text": hook_first_text if hook_first_used else "",
                                        "reason": hook_first_reason if hook_first_used else "",
                                    },
                                    "timing": {
                                        "original_start": float(original_start),
                                        "final_start": float(clip_start),
                                        "end": float(clip_end),
                                        "duration": float(max(clip_end - clip_start, 0.0)),
                                    },
                                    "extended_to_completion": bool(s.get("extended_to_completion", False)),
                                    "low_confidence": bool(s.get("low_confidence", False)),
                                    "overlap_skipped_count": int(s.get("overlap_skipped_count", 0)),
                                    "diversity_penalty_value": float(s.get("diversity_penalty_value", 0.0)),
                                }
                            )
                    else:
                        raise RuntimeError(f"Unsupported task: {task}")

                    tracker.update("snapping_to_silence", 50.0)
                    snap_to_silence = input_data.get("snap_to_silence")
                    if snap_to_silence is None:
                        snap_to_silence = task == "auto_clips"
                    snap_window_sec = float(input_data.get("snap_window_sec", 1.0))
                    # Limit to reasonable maximum (2.0s) to prevent excessive boundary shifts
                    # The silence_detect module already has protection: max_duration_change = window_sec * 2
                    snap_window_sec = min(snap_window_sec, 2.0)

                    silences = []
                    if snap_to_silence:
                        silences = detect_silences(input_path)

                    snapped_segments = []
                    for idx, segment in enumerate(segments):
                        if snap_to_silence:
                            snapped = snap_segment_to_silence(segment, silences, snap_window_sec)
                        else:
                            snapped = {**segment, "snapped_start": segment["start"], "snapped_end": segment["end"]}
                        
                        # For auto_clips: ensure end doesn't go backwards, but allow forward adjustment
                        # Exception: if boundary_mode is word, we'll adjust to word boundaries below
                        if task == "auto_clips" and boundary_mode != "word":
                            snapped["snapped_end"] = max(
                                float(snapped["snapped_end"]), float(segment["end"])
                            )
                        
                        # Apply boundary_mode word after snapping (final word-level precision)
                        if task == "auto_clips" and boundary_mode == "word":
                            meta = segment_meta[idx]
                            first_word = meta.get("first_word")
                            last_word = meta.get("last_word")
                            hook_first_used = meta.get("hook_first_used", False)
                            
                            if first_word:
                                # Only adjust start if hook_first wasn't used (hook_first has priority)
                                if not hook_first_used:
                                    snapped["snapped_start"] = min(
                                        float(snapped["snapped_start"]), float(first_word["start"])
                                    )
                            if last_word:
                                # Always adjust end to last word boundary (but not before snapped_end from silence)
                                snapped["snapped_end"] = max(
                                    float(snapped["snapped_end"]), float(last_word["end"])
                                )
                        if task == "auto_clips" and idx < len(segment_meta):
                            meta = segment_meta[idx]
                            timing = meta.get("timing", {})
                            timing["final_start"] = float(snapped["snapped_start"])
                            timing["end"] = float(snapped["snapped_end"])
                            timing["duration"] = float(
                                max(float(snapped["snapped_end"]) - float(snapped["snapped_start"]), 0.0)
                            )
                            meta["timing"] = timing
                        snapped_segments.append(snapped)

                    tracker.update("cutting_clips", 55.0)
                    cut_segments_payload = []
                    for s in snapped_segments:
                        start = float(s["snapped_start"])
                        end = float(s["snapped_end"])
                        # Final validation: ensure valid segment boundaries
                        if end <= start:
                            logger.warning(
                                f"Invalid segment {s['id']}: end ({end:.3f}) <= start ({start:.3f}), "
                                f"skipping"
                            )
                            continue
                        min_dur = min_duration if task == "auto_clips" else 0.1
                        if (end - start) < min_dur:
                            logger.warning(
                                f"Segment {s['id']} too short: {end - start:.3f}s < {min_dur:.3f}s, "
                                f"skipping"
                            )
                            continue
                        cut_segments_payload.append({"id": s["id"], "start": start, "end": end})
                    
                    if not cut_segments_payload:
                        raise RuntimeError("No valid segments to cut after validation")
                    clip_results = []
                    total_segments = max(len(cut_segments_payload), 1)
                    for idx, seg in enumerate(cut_segments_payload):
                        clip_results.extend(cut_segments(input_path, [seg], clips_dir, mode))
                        progress = 55.0 + (idx + 1) / total_segments * 15.0
                        tracker.update("cutting_clips", progress)

                    client = get_s3_client()
                    if not client:
                        raise RuntimeError("S3 client is not configured")

                    clips_entries: list[dict] = []
                    reels_meta_by_id: dict[str, dict] = {}
                    total_clips = max(len(clip_results), 1)
                    for idx, clip in enumerate(clip_results):
                        key = f"jobs/{job_id}/clips/{clip['id']}.mp4"
                        client.upload_file(clip["path"], MINIO_BUCKET, key)
                        clip_meta = None
                        if task == "auto_clips" and idx < len(segment_meta):
                            clip_meta = segment_meta[idx]
                        reels_key = None
                        reels_meta = {
                            "reels_enabled": False,
                            "tracking_used": "none",
                            "tracking_samples": 0,
                            "avg_pan_px_per_s": 0.0,
                        }
                        if render_mode == "reels":
                            reels_opts = input_data.get("reels") or {}
                            reels_out = os.path.join(clips_dir, f"{clip['id']}_reels.mp4")
                            reels_info = render_reels(
                                clip["path"],
                                reels_out,
                                target_w=int(reels_opts.get("target_w", 1080)),
                                target_h=int(reels_opts.get("target_h", 1920)),
                                sample_fps=float(reels_opts.get("sample_fps", 4.0)),
                                smoothing=float(reels_opts.get("smoothing", 0.95)),
                                deadzone_px=float(reels_opts.get("deadzone_px", 60.0)),
                                max_pan_px_per_s=float(reels_opts.get("max_pan_px_per_s", 90.0)),
                                motion_mode=str(reels_opts.get("motion_mode", "static")),
                                lookspace_ratio=float(reels_opts.get("lookspace_ratio", 0.10)),
                                micro_motion=bool(reels_opts.get("micro_motion", True)),
                                micro_amp_px=float(reels_opts.get("micro_amp_px", 6.0)),
                                micro_period_s=float(reels_opts.get("micro_period_s", 5.0)),
                                micro_only_when_stable=bool(
                                    reels_opts.get("micro_only_when_stable", True)
                                ),
                                track_mode=track_mode,
                            )
                            reels_key = f"jobs/{job_id}/clips/{clip['id']}_reels.mp4"
                            client.upload_file(reels_out, MINIO_BUCKET, reels_key)
                            reels_meta = {
                                "reels_enabled": True,
                                "tracking_used": reels_info.get("tracking_used", "none"),
                                "tracking_samples": reels_info.get("tracking_samples", 0),
                                "avg_pan_px_per_s": reels_info.get("avg_pan_px_per_s", 0.0),
                                "pan_range_px": reels_info.get("pan_range_px", 0.0),
                                "pan_rms_px": reels_info.get("pan_rms_px", 0.0),
                                "motion_mode": reels_info.get("motion_mode", "static"),
                                "look_dir": reels_info.get("look_dir", "unknown"),
                                "static_crop_x": reels_info.get("static_crop_x"),
                            }
                        reels_meta_by_id[clip["id"]] = reels_meta
                        clips_entries.append(
                            {
                                "id": clip["id"],
                                "start": clip["start"],
                                "end": clip["end"],
                                "duration": clip["duration"],
                                "key": key,
                                "reels_key": reels_key,
                                "clip_text": clip_meta.get("clip_text") if clip_meta else None,
                                "first_word": clip_meta.get("first_word") if clip_meta else None,
                                "last_word": clip_meta.get("last_word") if clip_meta else None,
                                "words": clip_meta.get("words") if clip_meta else None,
                                "low_confidence": clip_meta.get("low_confidence") if clip_meta else None,
                                "leading_silence_s": clip_meta.get("leading_silence_s") if clip_meta else None,
                                "trailing_silence_s": clip_meta.get("trailing_silence_s") if clip_meta else None,
                                "ends_with_punctuation": clip_meta.get("ends_with_punctuation") if clip_meta else None,
                                "word_count": clip_meta.get("word_count") if clip_meta else None,
                                "avg_word_confidence": clip_meta.get("avg_word_confidence") if clip_meta else None,
                                "min_word_confidence": clip_meta.get("min_word_confidence") if clip_meta else None,
                                "speech_rate_wps": clip_meta.get("speech_rate_wps") if clip_meta else None,
                                "pause_ratio": clip_meta.get("pause_ratio") if clip_meta else None,
                                "audio_rms_db_mean": clip_meta.get("audio_rms_db_mean") if clip_meta else None,
                                "audio_rms_db_std": clip_meta.get("audio_rms_db_std") if clip_meta else None,
                                "audio_zcr_mean": clip_meta.get("audio_zcr_mean") if clip_meta else None,
                                "audio_f0_hz_std": clip_meta.get("audio_f0_hz_std") if clip_meta else None,
                                "has_hook": clip_meta.get("has_hook") if clip_meta else None,
                                "hook_first": clip_meta.get("hook_first") if clip_meta else None,
                                "timing": clip_meta.get("timing") if clip_meta else None,
                                "overlap_skipped_count": clip_meta.get("overlap_skipped_count") if clip_meta else None,
                                "diversity_penalty_value": clip_meta.get("diversity_penalty_value") if clip_meta else None,
                                **reels_meta,
                            }
                        )
                        progress = 70.0 + (idx + 1) / total_clips * 20.0
                        tracker.update("uploading_clips", progress)

                    hooks_report_path = os.path.join(work_dir, "hooks_report.jsonl")
                    with open(hooks_report_path, "w", encoding="utf-8") as report_file:
                        for idx, clip in enumerate(clip_results):
                            clip_meta = segment_meta[idx] if idx < len(segment_meta) else {}
                            hook_info = clip_meta.get("hook_first") or {}
                            hook_start = hook_info.get("start_sec")
                            hook_rms_db = None
                            if hook_info.get("used") and hook_start is not None:
                                hook_window_end = min(float(clip["end"]), float(hook_start) + 1.2)
                                hook_rms_db = audio_rms_for_window(
                                    audio_features, float(hook_start), hook_window_end
                                )
                            record = {
                                "clip_index": idx + 1,
                                "clip_name": f"{clip['id']}.mp4",
                                "reels_name": f"{clip['id']}_reels.mp4" if render_mode == "reels" else None,
                                "score_total": float(clip_meta.get("score", 0.0)),
                                "start": float(clip["start"]),
                                "end": float(clip["end"]),
                                "duration": float(clip["duration"]),
                                "hook": {
                                    "enabled": bool(hook_info.get("enabled", False)),
                                    "used": bool(hook_info.get("used", False)),
                                    "hook_start": float(hook_start) if hook_start is not None else None,
                                    "hook_text": hook_info.get("text", "") or "",
                                    "hook_reason": hook_info.get("reason", "") or "",
                                    "hook_rms_db": float(hook_rms_db) if hook_rms_db is not None else None,
                                },
                            }
                            report_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    hooks_report_key = f"jobs/{job_id}/hooks_report.jsonl"
                    client.upload_file(hooks_report_path, MINIO_BUCKET, hooks_report_key)

                    manifest_key = f"jobs/{job_id}/manifest.json"
                    selected_manifest = []
                    if task == "cut":
                        for seg in snapped_segments:
                            selected_manifest.append(
                                {
                                    "id": seg["id"],
                                    "start": seg["start"],
                                    "end": seg["end"],
                                    "snapped_start": seg["snapped_start"],
                                    "snapped_end": seg["snapped_end"],
                                    "score": 0.0,
                                    "reason": "manual",
                                }
                            )
                    else:
                        for idx, seg in enumerate(snapped_segments):
                            meta = selected[idx]
                            reason = meta.get("reason") or []
                            if isinstance(reason, str):
                                reason = [reason]
                            clip_meta = segment_meta[idx]
                            selected_manifest.append(
                                {
                                    "id": seg["id"],
                                    "start": seg["start"],
                                    "end": seg["end"],
                                    "snapped_start": seg["snapped_start"],
                                    "snapped_end": seg["snapped_end"],
                                    "score": clip_meta.get("score", meta.get("score", 0.0)),
                                    "hook_sentence": clip_meta.get("hook_sentence", meta.get("hook_sentence", "")),
                                    "topic_hint": clip_meta.get("topic_hint", meta.get("topic_hint", "")),
                                    "clip_text": clip_meta.get("clip_text", ""),
                                    "first_word": clip_meta.get("first_word"),
                                    "last_word": clip_meta.get("last_word"),
                                    "words": clip_meta.get("words", []),
                                    "low_confidence": clip_meta.get("low_confidence", False),
                                    "leading_silence_s": clip_meta.get("leading_silence_s"),
                                    "trailing_silence_s": clip_meta.get("trailing_silence_s"),
                                    "ends_with_punctuation": clip_meta.get("ends_with_punctuation"),
                                    "word_count": clip_meta.get("word_count"),
                                    "avg_word_confidence": clip_meta.get("avg_word_confidence"),
                                    "min_word_confidence": clip_meta.get("min_word_confidence"),
                                    "speech_rate_wps": clip_meta.get("speech_rate_wps"),
                                    "pause_ratio": clip_meta.get("pause_ratio"),
                                    "audio_rms_db_mean": clip_meta.get("audio_rms_db_mean"),
                                    "audio_rms_db_std": clip_meta.get("audio_rms_db_std"),
                                    "audio_zcr_mean": clip_meta.get("audio_zcr_mean"),
                                    "audio_f0_hz_std": clip_meta.get("audio_f0_hz_std"),
                                    "has_hook": clip_meta.get("has_hook"),
                                    "hook_first": clip_meta.get("hook_first"),
                                    "timing": clip_meta.get("timing"),
                                    "overlap_skipped_count": clip_meta.get("overlap_skipped_count"),
                                    "diversity_penalty_value": clip_meta.get("diversity_penalty_value"),
                                    "reels_enabled": reels_meta_by_id.get(seg["id"], {}).get("reels_enabled"),
                                    "tracking_used": reels_meta_by_id.get(seg["id"], {}).get("tracking_used"),
                                    "tracking_samples": reels_meta_by_id.get(seg["id"], {}).get("tracking_samples"),
                                    "avg_pan_px_per_s": reels_meta_by_id.get(seg["id"], {}).get("avg_pan_px_per_s"),
                                    "pan_range_px": reels_meta_by_id.get(seg["id"], {}).get("pan_range_px"),
                                    "pan_rms_px": reels_meta_by_id.get(seg["id"], {}).get("pan_rms_px"),
                                    "motion_mode": reels_meta_by_id.get(seg["id"], {}).get("motion_mode"),
                                    "look_dir": reels_meta_by_id.get(seg["id"], {}).get("look_dir"),
                                    "static_crop_x": reels_meta_by_id.get(seg["id"], {}).get("static_crop_x"),
                                    "reason": reason or ["heuristic"],
                                }
                            )

                    manifest = {
                        "job_id": job_id,
                        "task": task,
                        "mode": mode,
                        "auto_clips": input_data.get("auto_clips"),
                        "boundary_mode": boundary_mode,
                        "transcript": transcript_segments,
                        "transcript_words": transcript_words,
                        "selected": selected_manifest,
                        "clips": clips_entries,
                    }
                    tracker.update("uploading_manifest", 95.0)
                    upload_json(manifest_key, manifest)

                job.output_data = {"manifest_key": manifest_key}
                job.output_key = manifest_key
                job.clips_keys = clips_entries
                job.output_url = None
                if validate_status_transition(job.status, "completed"):
                    job.status = "completed"
                job.progress = 100.0
                job.progress_stage = "completed"
                job.error = None
        except Exception as exc:
            logger.error(f"Job {job_id} failed: {exc}")
            with db_session() as session:
                job = session.get(Job, job_id)
                if job:
                    if validate_status_transition(job.status, "failed"):
                        job.status = "failed"
                    job.progress_stage = "failed"
                    job.error = str(exc)
                    job.retry_count = int(job.retry_count or 0) + 1


if __name__ == "__main__":
    worker_loop()
