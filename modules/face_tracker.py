"""
Face tracking using Haar cascades for reels cropping.
"""
from __future__ import annotations

from typing import List, Dict, Optional

import cv2


def _load_cascade() -> cv2.CascadeClassifier:
    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        raise RuntimeError(f"Failed to load Haar cascade: {path}")
    return cascade


def _load_profile_cascade() -> cv2.CascadeClassifier:
    path = cv2.data.haarcascades + "haarcascade_profileface.xml"
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        raise RuntimeError(f"Failed to load Haar cascade: {path}")
    return cascade


def sample_face_centers(
    video_path: str,
    sample_fps: float = 2.0,
) -> List[Dict]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps else 0.0
    interval = 1.0 / max(sample_fps, 0.1)
    cascade = _load_cascade()
    profile_cascade = _load_profile_cascade()

    keyframes: List[Dict] = []
    recent_cx: List[float] = []
    prev_cx: Optional[float] = None
    t = 0.0
    while t <= duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += interval
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces) > 0:
            if len(faces) > 1 and prev_cx is not None:
                def _distance_to_prev(face: tuple[int, int, int, int]) -> float:
                    x, _, w, _ = face
                    cx = float(x + w / 2.0)
                    return abs(cx - prev_cx)

                x, y, w, h = min(faces, key=_distance_to_prev)
            else:
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cx = float(x + w / 2.0)
            profile_faces = profile_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5
            )
            flipped = cv2.flip(gray, 1)
            profile_flipped = profile_cascade.detectMultiScale(
                flipped, scaleFactor=1.1, minNeighbors=5
            )
            if len(profile_faces) > 0 and len(profile_flipped) == 0:
                look_dir = "right"
            elif len(profile_flipped) > 0 and len(profile_faces) == 0:
                look_dir = "left"
            else:
                look_dir = "unknown"
            recent_cx.append(cx)
            if len(recent_cx) > 3:
                recent_cx.pop(0)
            median_cx = sorted(recent_cx)[len(recent_cx) // 2]
            prev_cx = median_cx
            keyframes.append({"t": float(t), "cx": median_cx, "look_dir": look_dir})
        t += interval

    cap.release()
    return keyframes
