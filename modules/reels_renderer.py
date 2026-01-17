"""
Render vertical reels with optional face tracking crop.
"""
from __future__ import annotations

import math
import subprocess
from typing import Dict, List, Tuple

from modules.face_tracker import sample_face_centers


def _ffprobe_dims(path: str) -> Tuple[int, int, float]:
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        text=True,
    ).strip().splitlines()
    width = int(float(output[0])) if len(output) > 0 else 0
    height = int(float(output[1])) if len(output) > 1 else 0
    duration = float(output[2]) if len(output) > 2 else 0.0
    return width, height, duration


def _clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def build_crop_trajectory(
    width: int,
    height: int,
    keyframes: List[Dict],
    sample_fps: float,
    smoothing: float,
    deadzone_px: float,
    max_pan_px_per_s: float,
) -> Tuple[List[Dict], float]:
    crop_w = int(round(height * 9 / 16)) if width >= height else width
    max_x = max(0, width - crop_w)

    frames: List[Dict] = []
    if not keyframes:
        frames.append({"t": 0.0, "x": 0.0})
        return frames, 0.0

    last_x = None
    avg_pan = 0.0
    pan_count = 0
    for idx, kf in enumerate(keyframes):
        cx = float(kf["cx"])
        t = float(kf["t"])
        target_x = _clamp(cx - crop_w / 2.0, 0.0, float(max_x))
        if last_x is None:
            x = target_x
        else:
            if abs(target_x - last_x) < deadzone_px:
                target_x = last_x
            dt = max(t - keyframes[idx - 1]["t"], 0.001)
            max_step = max_pan_px_per_s * dt
            step = _clamp(target_x - last_x, -max_step, max_step)
            x = last_x + step
            x = smoothing * last_x + (1.0 - smoothing) * x
            pan = abs(x - last_x) / dt
            avg_pan += pan
            pan_count += 1
        x = _clamp(x, 0.0, float(max_x))
        frames.append({"t": t, "x": x})
        last_x = x

    avg_pan_px_per_s = avg_pan / max(pan_count, 1)
    return frames, avg_pan_px_per_s


def _build_piecewise_expr(trajectory: List[Dict]) -> str:
    if not trajectory:
        return "0"
    if len(trajectory) == 1:
        return f"{trajectory[0]['x']:.3f}"

    expr = ""
    for idx in range(len(trajectory) - 1):
        t0 = float(trajectory[idx]["t"])
        t1 = float(trajectory[idx + 1]["t"])
        x0 = float(trajectory[idx]["x"])
        x1 = float(trajectory[idx + 1]["x"])
        dt = max(t1 - t0, 0.001)
        seg = (
            f"if(between(t,{t0:.3f},{t1:.3f}),"
            f"{x0:.3f}+({x1:.3f}-{x0:.3f})*(t-{t0:.3f})/{dt:.3f},"
        )
        expr += seg
    expr += f"{float(trajectory[-1]['x']):.3f}" + ")" * (len(trajectory) - 1)
    return expr


def _compute_pan_metrics(xs: List[float]) -> Tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    min_x = min(xs)
    max_x = max(xs)
    mean_x = sum(xs) / len(xs)
    rms = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / len(xs))
    return round(max_x - min_x, 3), round(rms, 3)


def _downsample_trajectory(trajectory: List[Dict], max_points: int = 60) -> List[Dict]:
    if len(trajectory) <= max_points:
        return trajectory
    step = max(1, int(math.ceil(len(trajectory) / max_points)))
    reduced = trajectory[::step]
    if reduced[-1]["t"] != trajectory[-1]["t"]:
        reduced.append(trajectory[-1])
    return reduced


def render_reels(
    input_path: str,
    output_path: str,
    target_w: int = 1080,
    target_h: int = 1920,
    sample_fps: float = 4.0,
    smoothing: float = 0.95,
    deadzone_px: float = 60.0,
    max_pan_px_per_s: float = 90.0,
    motion_mode: str = "static",
    lookspace_ratio: float = 0.10,
    micro_motion: bool = True,
    micro_amp_px: float = 6.0,
    micro_period_s: float = 5.0,
    micro_only_when_stable: bool = True,
    track_mode: str = "face",
) -> Dict:
    width, height, duration = _ffprobe_dims(input_path)
    if width == 0 or height == 0:
        raise RuntimeError("Failed to probe clip dimensions")

    crop_w = int(round(height * 9 / 16)) if width >= height else width
    crop_h = height

    keyframes = []
    if track_mode == "face":
        keyframes = sample_face_centers(input_path, sample_fps=sample_fps)

    if not keyframes:
        keyframes = [{"t": 0.0, "cx": width / 2.0}]
        tracking_used = "none"
    else:
        tracking_used = "face"

    look_counts = {"left": 0, "right": 0}
    for kf in keyframes:
        direction = kf.get("look_dir")
        if direction in look_counts:
            look_counts[direction] += 1
    if look_counts["left"] == look_counts["right"]:
        look_dir = "unknown"
    else:
        look_dir = "left" if look_counts["left"] > look_counts["right"] else "right"

    if motion_mode == "static":
        centers = [float(kf["cx"]) for kf in keyframes]
        centers.sort()
        median_cx = centers[len(centers) // 2]
        x_center = median_cx
        x = _clamp(x_center - crop_w / 2.0, 0.0, float(width - crop_w))
        crop = f"crop={crop_w}:{crop_h}:{x:.3f}:0,scale={target_w}:{target_h}"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vf",
            crop,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_path,
        ]
        subprocess.run(cmd, check=True)
        return {
            "tracking_used": tracking_used,
            "tracking_samples": len(keyframes),
            "avg_pan_px_per_s": 0.0,
            "pan_range_px": 0.0,
            "pan_rms_px": 0.0,
            "motion_mode": "static",
            "look_dir": look_dir,
            "static_crop_x": round(float(x), 3),
        }

    trajectory, avg_pan_px_per_s = build_crop_trajectory(
        width,
        height,
        keyframes,
        sample_fps,
        smoothing,
        deadzone_px,
        max_pan_px_per_s,
    )

    trajectory = _downsample_trajectory(trajectory, max_points=60)
    x_expr = _build_piecewise_expr(trajectory)
    center_x = (width - crop_w) / 2.0
    max_x = max(0, width - crop_w)
    if micro_motion and motion_mode == "follow":
        sin_expr = f"{micro_amp_px:.3f}*sin(2*PI*t/{micro_period_s:.3f})"
        if micro_only_when_stable:
            x_expr = (
                f"if(lt(abs(({x_expr})-{center_x:.3f}),{deadzone_px:.3f}),"
                f"({x_expr})+({sin_expr}),"
                f"({x_expr}))"
            )
        else:
            x_expr = f"({x_expr})+({sin_expr})"

    x_expr = f"max(0,min({max_x:.3f},({x_expr})))"
    safe_expr = x_expr.replace(",", "\\,")
    crop = f"crop={crop_w}:{crop_h}:{safe_expr}:0,scale={target_w}:{target_h}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vf",
        crop,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True)

    xs = [float(item["x"]) for item in trajectory]
    pan_range_px, pan_rms_px = _compute_pan_metrics(xs)

    return {
        "tracking_used": tracking_used,
        "tracking_samples": len(keyframes),
        "avg_pan_px_per_s": round(avg_pan_px_per_s, 3),
        "pan_range_px": pan_range_px,
        "pan_rms_px": pan_rms_px,
        "motion_mode": "follow",
        "look_dir": look_dir,
        "static_crop_x": None,
    }
