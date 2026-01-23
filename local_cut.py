#!/usr/bin/env python3
"""
Local Video Cutting Script for JARVIS
Run this on your local machine with the video file.

Requirements:
    pip install faster-whisper

System Requirements:
    - FFmpeg installed and in PATH
    - Python 3.10+
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.transcribe import transcribe_to_segments
from modules.segment_selector import select_segments, extend_segment_to_completion
from modules.silence_detect import detect_silences, snap_segment_to_silence
from modules.video_cutter import cut_segments
from modules.clip_candidates import generate_candidates


def process_video(
    input_path: str,
    output_dir: str,
    language: str = "he",
    max_clips: int = 5,
    min_duration: float = 15.0,
    max_duration: float = 45.0,
    min_sentences: int = 3,
    max_sentences: int = 10,
    hook_bias: float = 1.2,
    score_threshold: float = 0.25,
    snap_to_silence: bool = True,
    snap_window_sec: float = 1.0,
    mode: str = "accurate",
    target_duration_sec: float = 30.0,
    prefer_duration_min_sec: float = 25.0,
    prefer_duration_max_sec: float = 40.0,
):
    """
    Process a video and extract viral clips.

    Args:
        input_path: Path to source video
        output_dir: Directory for output clips
        language: Language code ("he" for Hebrew, "en" for English, or None for auto)
        max_clips: Maximum number of clips to extract
        min_duration: Minimum clip duration in seconds
        max_duration: Maximum clip duration in seconds
        min_sentences: Minimum sentences per clip
        max_sentences: Maximum sentences per clip
        hook_bias: Weight for hook scoring (higher = prefer stronger hooks)
        score_threshold: Minimum score for clip selection
        snap_to_silence: Snap clip boundaries to silence
        snap_window_sec: Window for silence snapping
        mode: "fast" (copy) or "accurate" (re-encode with fades)
        target_duration_sec: Ideal clip duration
        prefer_duration_min_sec: Preferred minimum duration
        prefer_duration_max_sec: Preferred maximum duration
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f"Video not found: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"=" * 60)
    print(f"JARVIS Local Video Cutter")
    print(f"=" * 60)
    print(f"Input:  {input_path}")
    print(f"Output: {output_dir}")
    print(f"Language: {language or 'auto'}")
    print(f"Max clips: {max_clips}")
    print(f"Duration: {min_duration}-{max_duration}s (target: {target_duration_sec}s)")
    print(f"=" * 60)

    # Step 1: Transcribe
    print("\n[1/5] Transcribing video...")

    def progress_cb(index, ratio):
        print(f"  Transcription progress: {ratio*100:.1f}%", end="\r")

    sentences, words = transcribe_to_segments(
        str(input_path),
        language=language,
        progress_callback=progress_cb
    )
    print(f"\n  ✓ Found {len(sentences)} sentences, {len(words)} words")

    # Attach words to sentences
    for sentence in sentences:
        sentence["words"] = [
            w for w in words
            if w["start"] >= sentence["start"] and w["end"] <= sentence["end"]
        ]

    # Save transcript
    transcript_path = output_dir / "transcript.json"
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump({"sentences": sentences, "words": words}, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Saved transcript to {transcript_path}")

    # Step 2: Detect silences (for snapping)
    silences = []
    if snap_to_silence:
        print("\n[2/5] Detecting silences...")
        silences = detect_silences(str(input_path))
        print(f"  ✓ Found {len(silences)} silence regions")
    else:
        print("\n[2/5] Skipping silence detection (disabled)")

    # Step 3: Select segments
    print("\n[3/5] Selecting best clips...")
    selected = select_segments(
        sentences=sentences,
        max_clips=max_clips,
        min_dur=min_duration,
        max_dur=max_duration,
        min_sentences=min_sentences,
        max_sentences=max_sentences,
        hook_bias=hook_bias,
        score_threshold=score_threshold,
        target_duration_sec=target_duration_sec,
        prefer_duration_min_sec=prefer_duration_min_sec,
        prefer_duration_max_sec=prefer_duration_max_sec,
    )
    print(f"  ✓ Selected {len(selected)} clips")

    # Step 4: Snap to silence and prepare for cutting
    print("\n[4/5] Preparing clips...")
    clips_to_cut = []
    for i, seg in enumerate(selected):
        clip_id = f"clip_{i+1:02d}"

        # Snap to silence if enabled
        if snap_to_silence and silences:
            seg = snap_segment_to_silence(seg, silences, snap_window_sec)
            start = seg.get("snapped_start", seg["start"])
            end = seg.get("snapped_end", seg["end"])
        else:
            start = seg["start"]
            end = seg["end"]

        duration = end - start
        hook = seg.get("hook_sentence", seg.get("text", "")[:50])
        score = seg.get("score", 0)
        reasons = seg.get("reason", [])

        print(f"  [{clip_id}] {start:.1f}s - {end:.1f}s ({duration:.1f}s) score={score:.2f}")
        print(f"           Hook: {hook[:60]}...")
        print(f"           Reasons: {', '.join(reasons[:5])}")

        clips_to_cut.append({
            "id": clip_id,
            "start": start,
            "end": end,
            "score": score,
            "hook": hook,
            "text": seg.get("text", ""),
            "reasons": reasons,
        })

    # Save manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": str(input_path),
            "language": language,
            "params": {
                "max_clips": max_clips,
                "min_duration": min_duration,
                "max_duration": max_duration,
                "hook_bias": hook_bias,
                "score_threshold": score_threshold,
            },
            "clips": clips_to_cut,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  ✓ Saved manifest to {manifest_path}")

    # Step 5: Cut videos
    print(f"\n[5/5] Cutting clips (mode={mode})...")
    results = cut_segments(
        input_path=str(input_path),
        segments=clips_to_cut,
        output_dir=str(output_dir),
        mode=mode,
    )

    print(f"\n" + "=" * 60)
    print("DONE! Created clips:")
    print("=" * 60)
    for r in results:
        print(f"  ✓ {r['path']} ({r['duration']:.1f}s)")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="JARVIS Local Video Cutter - Extract viral clips from videos"
    )
    parser.add_argument("input", help="Path to source video file")
    parser.add_argument("output", help="Directory for output clips")
    parser.add_argument("--language", "-l", default="he", help="Language code (he/en/auto)")
    parser.add_argument("--max-clips", "-n", type=int, default=5, help="Max clips to extract")
    parser.add_argument("--min-duration", type=float, default=15.0, help="Min clip duration (seconds)")
    parser.add_argument("--max-duration", type=float, default=45.0, help="Max clip duration (seconds)")
    parser.add_argument("--target-duration", type=float, default=30.0, help="Ideal clip duration (seconds)")
    parser.add_argument("--min-sentences", type=int, default=3, help="Min sentences per clip")
    parser.add_argument("--max-sentences", type=int, default=10, help="Max sentences per clip")
    parser.add_argument("--hook-bias", type=float, default=1.2, help="Hook scoring weight")
    parser.add_argument("--score-threshold", type=float, default=0.25, help="Min score threshold")
    parser.add_argument("--no-snap", action="store_true", help="Disable silence snapping")
    parser.add_argument("--snap-window", type=float, default=1.0, help="Silence snap window (seconds)")
    parser.add_argument("--mode", choices=["fast", "accurate"], default="accurate", help="Cutting mode")

    args = parser.parse_args()

    try:
        process_video(
            input_path=args.input,
            output_dir=args.output,
            language=args.language if args.language != "auto" else None,
            max_clips=args.max_clips,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            min_sentences=args.min_sentences,
            max_sentences=args.max_sentences,
            hook_bias=args.hook_bias,
            score_threshold=args.score_threshold,
            snap_to_silence=not args.no_snap,
            snap_window_sec=args.snap_window,
            mode=args.mode,
            target_duration_sec=args.target_duration,
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
