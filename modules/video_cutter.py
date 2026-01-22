"""
FFmpeg-based video cutting utilities.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Iterable, Optional

# Default audio fade duration in seconds
DEFAULT_FADE_DURATION = 0.15


def build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
    mode: str,
    fade_in_sec: float = DEFAULT_FADE_DURATION,
    fade_out_sec: float = DEFAULT_FADE_DURATION,
) -> list[str]:
    """Build FFmpeg command for cutting a segment.

    Args:
        input_path: Source video path
        output_path: Output video path
        start: Start time in seconds
        end: End time in seconds
        mode: 'fast' (copy codec) or 'accurate' (re-encode)
        fade_in_sec: Audio fade-in duration (0 to disable)
        fade_out_sec: Audio fade-out duration (0 to disable)
    """
    start = round(start, 3)
    end = round(end, 3)
    duration = max(end - start, 0.0)

    if mode == "fast":
        # Fast mode: stream copy, no fades (keyframe-aligned cuts)
        return [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-i",
            input_path,
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            output_path,
        ]

    # Accurate mode: re-encode with audio fades for smooth transitions
    audio_filters = ["aresample=async=1:first_pts=0"]

    # Add fade-in at start
    if fade_in_sec > 0:
        audio_filters.append(f"afade=t=in:st=0:d={fade_in_sec}")

    # Add fade-out at end
    if fade_out_sec > 0 and duration > fade_out_sec:
        fade_out_start = duration - fade_out_sec
        audio_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_sec}")

    audio_filter_str = ",".join(audio_filters)

    return [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-af",
        audio_filter_str,
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
        output_path,
    ]


def run_ffmpeg(cmd: list[str], retries: int = 2, retry_delay: float = 1.0) -> None:
    """Run FFmpeg command with retry logic for transient failures."""
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            return
        except subprocess.CalledProcessError as e:
            last_error = e
            if attempt < retries:
                time.sleep(retry_delay)
                continue
            raise RuntimeError(
                f"FFmpeg failed after {retries + 1} attempts: {e.stderr}"
            ) from e


def cut_segments(
    input_path: str,
    segments: Iterable[dict],
    output_dir: str,
    mode: str,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    results: list[dict] = []
    for segment in segments:
        seg_id = segment["id"]
        start = float(segment["start"])
        end = float(segment["end"])
        output_path = os.path.join(output_dir, f"{seg_id}.mp4")
        cmd = build_ffmpeg_cmd(input_path, output_path, start, end, mode)
        run_ffmpeg(cmd)
        results.append(
            {
                "id": seg_id,
                "start": start,
                "end": end,
                "duration": max(end - start, 0.0),
                "path": output_path,
            }
        )
    return results
