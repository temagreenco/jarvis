"""
Background worker that processes jobs from Redis and updates Postgres.
"""
from __future__ import annotations

import json
import os
import time
import tempfile
import subprocess
from typing import Any, Dict

import httpx

from modules.db_models import Job, db_session, init_db
from modules.job_queue import JobQueue
from modules.minio_client import get_s3_client
from modules.video_cutter import cut_segments
from modules.transcribe import transcribe_to_segments
from modules.segment_selector import select_segments
from modules.reels_renderer import render_reels
from modules.sentence_splitter import build_sentences
from modules.silence_detect import detect_silences, snap_segment_to_silence
from utils.logger import get_logger

logger = get_logger("worker")

MINIO_BUCKET = os.getenv("MINIO_BUCKET", "jarvis")


def update_progress(job_id: str, stage: str, progress: float) -> None:
    with db_session() as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.progress = float(progress)
        job.progress_stage = stage


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


def worker_loop(poll_interval: float = 1.0) -> None:
    init_db()
    queue = JobQueue()
    logger.info("Worker started, waiting for jobs...")

    while True:
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
            job.status = "processing"
            job.progress = 0.0
            job.progress_stage = "starting"

        try:
            with db_session() as session:
                job = session.get(Job, job_id)
                input_data = job.input_data or {}
                task = input_data.get("task") or "cut"
                mode = input_data.get("mode") or "accurate"
                if mode not in ("fast", "accurate"):
                    mode = "accurate"

                with tempfile.TemporaryDirectory() as work_dir:
                    update_progress(job_id, "downloading_input", 5.0)
                    input_path = download_input(job, work_dir)
                    clips_dir = os.path.join(work_dir, "clips")

                    transcript_segments = []
                    transcript_words: list[dict] = []
                    segment_meta: list[dict] = []
                    selected = []
                    segments = []

                    if task == "cut":
                        boundary_mode = input_data.get("boundary_mode") or "sentence"
                        render_mode = input_data.get("render_mode") or "original"
                        track_mode = input_data.get("track_mode") or "none"
                        update_progress(job_id, "validating_segments", 15.0)
                        segments = validate_segments(input_data.get("segments", []))
                    elif task == "auto_clips":
                        auto_params = input_data.get("auto_clips") or {}
                        max_clips = int(auto_params.get("max_clips", 3))
                        min_duration = float(auto_params.get("min_duration", 12))
                        max_duration = float(auto_params.get("max_duration", 45))
                        min_sentences = int(auto_params.get("min_sentences", 2))
                        max_sentences = int(auto_params.get("max_sentences", 6))
                        hook_bias = float(auto_params.get("hook_bias", 1.0))
                        score_threshold = float(auto_params.get("score_threshold", 0.25))
                        language = auto_params.get("language")
                        boundary_mode = input_data.get("boundary_mode") or "word"
                        render_mode = input_data.get("render_mode") or "original"
                        track_mode = input_data.get("track_mode") or ("face" if render_mode == "reels" else "none")

                        update_progress(job_id, "transcribing", 20.0)
                        transcript_segments, transcript_words = transcribe_to_segments(
                            input_path, language=language
                        )
                        media_duration = get_media_duration(input_path)
                        if 0 < media_duration < 60.0:
                            max_clips = max(1, min(max_clips, 3))
                        update_progress(job_id, "building_sentences", 30.0)
                        sentences = (
                            build_sentences(transcript_words)
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
                        update_progress(job_id, "selecting_segments", 40.0)
                        selected = select_segments(
                            sentences,
                            max_clips,
                            min_duration,
                            max_duration,
                            min_sentences,
                            max_sentences,
                            hook_bias=hook_bias,
                            score_threshold=score_threshold,
                        )
                        if not selected:
                            raise RuntimeError("No segments selected from transcript")
                        segments = []
                        segment_meta = []
                        for idx, s in enumerate(selected):
                            clip_start = float(s["start"])
                            clip_end = float(s["end"])
                            clip_words = collect_words_in_window(transcript_words, clip_start, clip_end)
                            first_word = clip_words[0] if clip_words else None
                            last_word = clip_words[-1] if clip_words else None
                            if boundary_mode == "word" and first_word and last_word:
                                clip_start = float(first_word["start"])
                                clip_end = float(last_word["end"])
                            segments.append(
                                {
                                    "id": f"clip-{idx + 1}",
                                    "start": clip_start,
                                    "end": clip_end,
                                }
                            )
                            clip_text = " ".join(w.get("w", "") for w in clip_words).strip()
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
                                    "leading_silence_s": round(leading_silence, 3),
                                    "trailing_silence_s": round(trailing_silence, 3),
                                    "ends_with_punctuation": ends_with_punctuation,
                                    "has_hook": bool(s.get("hook_sentence")),
                                    "score": s.get("score", 0.0),
                                    "reason": s.get("reason") or [],
                                    "hook_sentence": s.get("hook_sentence", ""),
                                    "topic_hint": s.get("topic_hint", ""),
                                    "low_confidence": bool(s.get("low_confidence", False)),
                                    "overlap_skipped_count": int(s.get("overlap_skipped_count", 0)),
                                    "diversity_penalty_value": float(s.get("diversity_penalty_value", 0.0)),
                                }
                            )
                    else:
                        raise RuntimeError(f"Unsupported task: {task}")

                    update_progress(job_id, "snapping_to_silence", 50.0)
                    snap_to_silence = input_data.get("snap_to_silence")
                    if snap_to_silence is None:
                        snap_to_silence = task == "auto_clips"
                    snap_window_sec = float(input_data.get("snap_window_sec", 1.0))
                    snap_window_sec = min(snap_window_sec, 0.25)

                    silences = []
                    if snap_to_silence:
                        silences = detect_silences(input_path)

                    snapped_segments = []
                    for idx, segment in enumerate(segments):
                        if snap_to_silence:
                            snapped = snap_segment_to_silence(segment, silences, snap_window_sec)
                        else:
                            snapped = {**segment, "snapped_start": segment["start"], "snapped_end": segment["end"]}
                        if task == "auto_clips" and boundary_mode == "word":
                            meta = segment_meta[idx]
                            first_word = meta.get("first_word")
                            last_word = meta.get("last_word")
                            if first_word:
                                snapped["snapped_start"] = min(
                                    float(snapped["snapped_start"]), float(first_word["start"])
                                )
                            if last_word:
                                snapped["snapped_end"] = max(
                                    float(snapped["snapped_end"]), float(last_word["end"])
                                )
                        snapped_segments.append(snapped)

                    update_progress(job_id, "cutting_clips", 55.0)
                    cut_segments_payload = [
                        {"id": s["id"], "start": s["snapped_start"], "end": s["snapped_end"]}
                        for s in snapped_segments
                    ]
                    clip_results = []
                    total_segments = max(len(cut_segments_payload), 1)
                    for idx, seg in enumerate(cut_segments_payload):
                        clip_results.extend(cut_segments(input_path, [seg], clips_dir, mode))
                        progress = 55.0 + (idx + 1) / total_segments * 15.0
                        update_progress(job_id, "cutting_clips", progress)

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
                                "has_hook": clip_meta.get("has_hook") if clip_meta else None,
                                "overlap_skipped_count": clip_meta.get("overlap_skipped_count") if clip_meta else None,
                                "diversity_penalty_value": clip_meta.get("diversity_penalty_value") if clip_meta else None,
                                **reels_meta,
                            }
                        )
                        progress = 70.0 + (idx + 1) / total_clips * 20.0
                        update_progress(job_id, "uploading_clips", progress)

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
                                    "has_hook": clip_meta.get("has_hook"),
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
                    update_progress(job_id, "uploading_manifest", 95.0)
                    upload_json(manifest_key, manifest)

                job.output_data = {"manifest_key": manifest_key}
                job.output_key = manifest_key
                job.clips_keys = clips_entries
                job.output_url = None
                job.status = "completed"
                job.progress = 100.0
                job.progress_stage = "completed"
                job.error = None
        except Exception as exc:
            logger.error(f"Job {job_id} failed: {exc}")
            with db_session() as session:
                job = session.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.progress_stage = "failed"
                    job.error = str(exc)


if __name__ == "__main__":
    worker_loop()
