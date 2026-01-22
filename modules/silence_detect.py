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


def _find_nearest_silence_boundary(
    target_time: float,
    silences: List[Dict],
    window_sec: float,
    prefer_before: bool = True,
) -> tuple[float, bool]:
    """Find the nearest silence boundary within window.

    Args:
        target_time: The time to snap from
        silences: List of silence intervals
        window_sec: Maximum distance to search
        prefer_before: If True, prefer silence before target_time

    Returns:
        Tuple of (snapped_time, was_snapped)
    """
    candidates: List[tuple[float, float]] = []  # (boundary_time, distance)

    for silence in silences:
        # Check silence end (good for segment start - start after silence)
        if abs(silence["end"] - target_time) <= window_sec:
            candidates.append((silence["end"], abs(silence["end"] - target_time)))

        # Check silence start (good for segment end - end before silence)
        if abs(silence["start"] - target_time) <= window_sec:
            candidates.append((silence["start"], abs(silence["start"] - target_time)))

    if not candidates:
        return target_time, False

    # Sort by distance, prefer boundaries before target if prefer_before is True
    if prefer_before:
        candidates.sort(key=lambda x: (x[0] > target_time, x[1]))
    else:
        candidates.sort(key=lambda x: (x[0] < target_time, x[1]))

    return candidates[0][0], True


def snap_segment_to_silence(
    segment: Dict,
    silences: List[Dict],
    window_sec: float = 1.0,
    start_window_sec: float | None = None,
    end_window_sec: float | None = None,
) -> Dict:
    """Snap segment boundaries to nearest silence for cleaner cuts.

    Args:
        segment: Segment with 'start' and 'end' keys
        silences: List of silence intervals from detect_silences()
        window_sec: Default snap window in seconds
        start_window_sec: Optional separate window for start snapping
        end_window_sec: Optional separate window for end snapping

    Returns:
        Segment dict with added 'snapped_start' and 'snapped_end' keys
    """
    start = float(segment["start"])
    end = float(segment["end"])
    original_duration = end - start

    start_win = start_window_sec if start_window_sec is not None else window_sec
    end_win = end_window_sec if end_window_sec is not None else window_sec

    # Snap start - prefer silence boundary before original start
    snapped_start, start_was_snapped = _find_nearest_silence_boundary(
        start, silences, start_win, prefer_before=True
    )

    # Snap end - prefer silence boundary after original end
    snapped_end, end_was_snapped = _find_nearest_silence_boundary(
        end, silences, end_win, prefer_before=False
    )

    # Validate: snapped segment must be positive duration
    # and not deviate too much from original
    if snapped_end <= snapped_start:
        snapped_start = start
        snapped_end = end
        start_was_snapped = False
        end_was_snapped = False

    # Don't allow snapping to change duration by more than 2x window
    max_duration_change = window_sec * 2
    new_duration = snapped_end - snapped_start
    if abs(new_duration - original_duration) > max_duration_change:
        snapped_start = start
        snapped_end = end
        start_was_snapped = False
        end_was_snapped = False

    return {
        **segment,
        "snapped_start": float(snapped_start),
        "snapped_end": float(snapped_end),
        "start_snapped": start_was_snapped,
        "end_snapped": end_was_snapped,
    }
