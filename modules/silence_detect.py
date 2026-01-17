"""
Silence detection helpers using FFmpeg silencedetect.
"""
from __future__ import annotations

import re
import subprocess
from typing import List, Dict

SILENCE_START_RE = re.compile(r"silence_start:\s*(\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(\d+(?:\.\d+)?)\s*\|\s*silence_duration")


def detect_silences(
    video_path: str,
    threshold_db: str = "-30dB",
    min_silence_dur: float = 0.25,
) -> List[Dict]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-vn",
        "-i",
        video_path,
        "-af",
        f"silencedetect=n={threshold_db}:d={min_silence_dur}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    silences: List[Dict] = []
    current_start = None
    for line in proc.stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue
        end_match = SILENCE_END_RE.search(line)
        if end_match and current_start is not None:
            end = float(end_match.group(1))
            if end > current_start:
                silences.append({"start": current_start, "end": end})
            current_start = None
    return silences


def snap_segment_to_silence(
    segment: Dict,
    silences: List[Dict],
    window_sec: float = 1.0,
) -> Dict:
    start = float(segment["start"])
    end = float(segment["end"])
    snapped_start = start
    snapped_end = end

    prev_silence_end = None
    for silence in silences:
        if silence["end"] <= start and start - silence["end"] <= window_sec:
            prev_silence_end = silence["end"]
    if prev_silence_end is not None:
        snapped_start = prev_silence_end

    next_silence_start = None
    for silence in silences:
        if silence["start"] >= end and silence["start"] - end <= window_sec:
            next_silence_start = silence["start"]
            break
    if next_silence_start is not None:
        snapped_end = next_silence_start

    if snapped_end <= snapped_start:
        snapped_start = start
        snapped_end = end

    return {
        **segment,
        "snapped_start": float(snapped_start),
        "snapped_end": float(snapped_end),
    }
