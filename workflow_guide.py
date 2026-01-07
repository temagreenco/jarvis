#!/usr/bin/env python3
"""
JARVIS Workflow Guide - System checker and setup helper.

Run this script to verify your environment is ready for video editing.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def check_command(cmd: str) -> tuple[bool, str]:
    """Check if a command is available."""
    result = shutil.which(cmd)
    return (True, result) if result else (False, "Not found")


def check_python_package(package: str) -> tuple[bool, str]:
    """Check if a Python package is installed."""
    try:
        __import__(package)
        return True, "Installed"
    except ImportError:
        return False, "Not installed"


def check_gpu() -> tuple[bool, str]:
    """Check GPU availability."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            return True, gpu_info
        return False, "nvidia-smi failed"
    except FileNotFoundError:
        return False, "nvidia-smi not found"
    except Exception as e:
        return False, str(e)


def check_ollama() -> tuple[bool, str]:
    """Check if Ollama is running."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            models = [line.split()[0] for line in result.stdout.strip().split('\n')[1:] if line]
            return True, f"Models: {', '.join(models) if models else 'None'}"
        return False, "Ollama not responding"
    except FileNotFoundError:
        return False, "Ollama not installed"
    except Exception as e:
        return False, str(e)


def main():
    console.print(Panel(
        "[bold cyan]JARVIS Workflow Guide[/]\n"
        "Checking system requirements for video editing...",
        border_style="cyan"
    ))

    # System Requirements Table
    table = Table(title="System Requirements")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    # Check GPU
    gpu_ok, gpu_info = check_gpu()
    table.add_row(
        "NVIDIA GPU",
        "[green]OK[/]" if gpu_ok else "[red]MISSING[/]",
        gpu_info
    )

    # Check FFmpeg
    ffmpeg_ok, ffmpeg_path = check_command("ffmpeg")
    table.add_row(
        "FFmpeg",
        "[green]OK[/]" if ffmpeg_ok else "[red]MISSING[/]",
        ffmpeg_path
    )

    # Check Ollama
    ollama_ok, ollama_info = check_ollama()
    table.add_row(
        "Ollama",
        "[green]OK[/]" if ollama_ok else "[yellow]OPTIONAL[/]",
        ollama_info
    )

    # Python packages
    packages = [
        ("faster_whisper", "faster-whisper"),
        ("ultralytics", "ultralytics"),
        ("moviepy", "moviepy"),
        ("torch", "torch"),
        ("typer", "typer"),
        ("rich", "rich"),
    ]

    for import_name, package_name in packages:
        pkg_ok, pkg_info = check_python_package(import_name)
        table.add_row(
            package_name,
            "[green]OK[/]" if pkg_ok else "[red]MISSING[/]",
            pkg_info
        )

    console.print(table)

    # Check directories
    console.print("\n[bold]Directory Structure:[/]")
    dirs = {
        "videos": Path("videos"),
        "output": Path("output"),
        "models": Path("models"),
    }
    for name, path in dirs.items():
        exists = path.exists()
        status = "[green]exists[/]" if exists else "[yellow]will be created[/]"
        console.print(f"  ./{name}/ - {status}")
        if not exists:
            path.mkdir(parents=True, exist_ok=True)

    # Workflow Instructions
    console.print(Panel(
        """[bold]Quick Start Workflow:[/]

[cyan]1. Upload your video:[/]
   • Place video files in ./videos/ directory
   • Supported: .mp4, .mov, .avi, .mkv, .webm

[cyan]2. Create reels (single video):[/]
   python create_reels.py videos/your_video.mp4 --reels 5

[cyan]3. Create podcast reels (2 cameras):[/]
   python create_reels.py videos/host.mp4 --video2 videos/guest.mp4 --reels 10 --podcast

[cyan]4. Use the CLI:[/]
   python cli.py chat  # Interactive chat
   python cli.py process "create 5 reels" --video videos/your_video.mp4

[bold]Tips:[/]
• Start Ollama: ollama serve (in background)
• Check status: python cli.py status
• Output goes to ./output/ directory
""",
        title="[bold green]Workflow Guide[/]",
        border_style="green"
    ))

    # Final status
    all_critical = gpu_ok and ffmpeg_ok
    if all_critical:
        console.print("\n[bold green]System ready for video editing![/]")
    else:
        console.print("\n[bold yellow]Some components missing. Install them to enable full functionality.[/]")
        if not ffmpeg_ok:
            console.print("  [dim]Install FFmpeg: apt install ffmpeg[/]")
        if not gpu_ok:
            console.print("  [dim]GPU required for fast processing[/]")


if __name__ == "__main__":
    main()
