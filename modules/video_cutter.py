"""
FFmpeg-based video cutting utilities.
"""
from __future__ import annotations

import os
import subprocess
from typing import Iterable


def build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
    mode: str,
) -> list[str]:
    start = round(start, 3)
    end = round(end, 3)
    duration = max(end - start, 0.0)
    if mode == "fast":
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
            output_path,
        ]
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
        "-c:a",
        "aac",
        "-af",
        "aresample=async=1:first_pts=0",
        "-avoid_negative_ts",
        "make_zero",
        "-movflags",
        "+faststart",
        output_path,
    ]


def run_ffmpeg(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


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
