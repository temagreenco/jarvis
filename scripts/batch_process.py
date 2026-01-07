#!/usr/bin/env python3
"""
Batch Video Processing for RunPod
Process multiple podcast videos in parallel with GPU acceleration
"""
import argparse
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def process_video(video_path: Path, output_dir: Path) -> tuple[str, bool, float]:
    """Process a single video and return status"""
    start = time.time()
    video_name = video_path.stem
    video_output = output_dir / video_name
    video_output.mkdir(exist_ok=True)

    cmd = [
        sys.executable, "-m", "jarvis", "video", "process",
        str(video_path),
        "--output", str(video_output)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30min timeout
        elapsed = time.time() - start

        if result.returncode == 0:
            return video_name, True, elapsed
        else:
            print(f"Error processing {video_name}: {result.stderr[:200]}")
            return video_name, False, elapsed
    except subprocess.TimeoutExpired:
        return video_name, False, 1800.0
    except Exception as e:
        return video_name, False, time.time() - start

def main():
    parser = argparse.ArgumentParser(description="Batch process videos for reels")
    parser.add_argument("input_dir", help="Directory with input videos")
    parser.add_argument("--output", "-o", default="output", help="Output directory")
    parser.add_argument("--workers", "-w", type=int, default=1, help="Parallel workers (1 for GPU)")
    parser.add_argument("--ext", default="mp4,mkv,mov,avi", help="Video extensions to process")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    # Find all videos
    extensions = args.ext.split(",")
    videos = []
    for ext in extensions:
        videos.extend(input_dir.glob(f"*.{ext}"))
        videos.extend(input_dir.glob(f"*.{ext.upper()}"))

    if not videos:
        print(f"No videos found in {input_dir}")
        sys.exit(1)

    print(f"Found {len(videos)} videos to process")
    print(f"Output directory: {output_dir}")
    print(f"Workers: {args.workers}")
    print("-" * 50)

    results = []
    total_start = time.time()

    # Process videos (sequential for GPU, parallel for CPU-only tasks)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_video, v, output_dir): v for v in videos}

        for future in as_completed(futures):
            name, success, elapsed = future.result()
            status = "✓" if success else "✗"
            print(f"{status} {name}: {elapsed:.1f}s")
            results.append((name, success, elapsed))

    # Summary
    total_time = time.time() - total_start
    successful = sum(1 for _, s, _ in results if s)

    print("-" * 50)
    print(f"Completed: {successful}/{len(videos)} videos")
    print(f"Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"Average per video: {total_time/len(videos):.1f}s")

    # List outputs
    print(f"\nOutput reels in: {output_dir}/")
    for d in output_dir.iterdir():
        if d.is_dir():
            reels = list(d.glob("reel_*.mp4"))
            print(f"  {d.name}/: {len(reels)} reels")

if __name__ == "__main__":
    main()
