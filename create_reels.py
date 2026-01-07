#!/usr/bin/env python3
"""
Quick CLI tool to create viral reels from videos.

Usage:
    python create_reels.py video.mp4 --reels 5
    python create_reels.py host.mp4 --video2 guest.mp4 --reels 10 --podcast
"""
import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="Create viral reels from videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single video:
    python create_reels.py video.mp4 --reels 5

  Podcast with 2 camera angles:
    python create_reels.py host.mp4 --video2 guest.mp4 --reels 10 --podcast

  Custom output directory:
    python create_reels.py video.mp4 --output ./my_reels --reels 3
        """
    )

    parser.add_argument("video", help="Primary video file path")
    parser.add_argument("--video2", help="Secondary video for podcast mode")
    parser.add_argument("--reels", type=int, default=8, help="Number of reels to create (default: 8)")
    parser.add_argument("--output", "-o", help="Output directory (default: ./output)")
    parser.add_argument("--podcast", action="store_true", help="Enable podcast mode with speaker detection")
    parser.add_argument("--min-duration", type=float, default=15.0, help="Minimum reel duration in seconds")
    parser.add_argument("--max-duration", type=float, default=40.0, help="Maximum reel duration in seconds")

    args = parser.parse_args()

    # Validate primary video
    video_path = Path(args.video)
    if not video_path.exists():
        console.print(f"[red]Error: Video file not found: {args.video}[/]")
        console.print("\n[dim]Available videos in ./videos/:[/]")
        videos_dir = Path("videos")
        if videos_dir.exists():
            for f in videos_dir.glob("*"):
                if f.suffix.lower() in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
                    console.print(f"  {f}")
        sys.exit(1)

    # Validate secondary video if podcast mode
    video2_path = None
    if args.video2:
        video2_path = Path(args.video2)
        if not video2_path.exists():
            console.print(f"[red]Error: Secondary video not found: {args.video2}[/]")
            sys.exit(1)

    # Show configuration
    console.print(Panel(
        f"[cyan]Video:[/] {video_path}\n"
        f"[cyan]Video 2:[/] {video2_path or 'None'}\n"
        f"[cyan]Reels:[/] {args.reels}\n"
        f"[cyan]Duration:[/] {args.min_duration}-{args.max_duration}s\n"
        f"[cyan]Mode:[/] {'Podcast' if args.podcast or video2_path else 'Single Video'}",
        title="[bold green]JARVIS Reel Creator[/]",
        border_style="green"
    ))

    # Import and run
    try:
        from core.jarvis import get_jarvis
        from config.settings import settings

        # Update settings if custom values provided
        if args.output:
            settings.output_dir = Path(args.output)
        settings.target_reels = args.reels
        settings.min_reel_duration = args.min_duration
        settings.max_reel_duration = args.max_duration

        jarvis = get_jarvis()
        jarvis.initialize()

        # Build task description
        if args.podcast or video2_path:
            task = f"create {args.reels} viral podcast reels from the videos"
            kwargs = {
                "video_path": str(video_path),
                "video2_path": str(video2_path) if video2_path else None,
                "podcast_mode": True
            }
        else:
            task = f"create {args.reels} viral reels from the video"
            kwargs = {"video_path": str(video_path)}

        console.print("\n[cyan]Starting video processing...[/]")
        console.print("[dim]This may take a while depending on video length.[/]\n")

        result = jarvis.process(task, **kwargs)

        if result.success:
            console.print(Panel(
                f"[green]Successfully created reels![/]\n\n"
                f"Output: {settings.output_dir}\n"
                f"Duration: {result.duration:.1f}s",
                title="[bold green]Complete[/]",
                border_style="green"
            ))
        else:
            console.print(f"[red]Error: {result.error}[/]")
            sys.exit(1)

    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/]")
        console.print("[dim]Run: pip install -r requirements.txt[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
