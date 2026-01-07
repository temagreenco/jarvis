#!/usr/bin/env python3
"""
JARVIS CLI - Command line interface for JARVIS AI system
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import typer
from rich.console import Console
from rich.panel import Panel

from core.jarvis import get_jarvis
from config.settings import settings

app = typer.Typer(name="jarvis", help="JARVIS AI Assistant")
console = Console()


@app.command()
def video(
    input_path: Path = typer.Argument(..., help="Path to input video file (Camera 1)"),
    video2: Path = typer.Option(None, "--video2", "-v2", help="Path to second video (Camera 2) for multi-cam"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory"),
    num_reels: int = typer.Option(8, "--reels", "-n", help="Number of reels to generate"),
):
    """Create viral short-form reels from a video (supports multi-cam)"""
    if not input_path.exists():
        console.print(f"[red]Error: Video file not found: {input_path}[/red]")
        raise typer.Exit(1)

    if video2 and not video2.exists():
        console.print(f"[red]Error: Second video file not found: {video2}[/red]")
        raise typer.Exit(1)

    output = output_dir or settings.output_dir / input_path.stem
    output.mkdir(parents=True, exist_ok=True)

    multi_cam = video2 is not None
    console.print(Panel(
        f"[bold cyan]JARVIS Video Editor[/bold cyan]\n\n"
        f"Camera 1: {input_path}\n"
        + (f"Camera 2: {video2}\n" if multi_cam else "")
        + f"Output: {output}\n"
        f"Target Reels: {num_reels}\n"
        f"Mode: {'Multi-Cam' if multi_cam else 'Single Camera'}",
        title="Starting"
    ))

    jarvis = get_jarvis()
    result = jarvis.process(
        f"Create {num_reels} viral reels from video",
        video_path=str(input_path),
        video_path_2=str(video2) if video2 else None,
        output_dir=str(output),
        num_reels=num_reels
    )

    if result.success:
        reels = result.data.get('reels', [])
        subs = result.data.get('subtitles', [])
        console.print(Panel(
            f"[bold green]Success![/bold green]\n\n"
            f"Created {len(reels)} reels\n"
            f"Created {len(subs)} SRT files\n"
            f"Duration: {result.duration:.1f}s\n\n"
            f"Output: {output}",
            title="Complete"
        ))
        for reel in reels:
            console.print(f"  • {reel}")
        if result.data.get('xml_project'):
            console.print(f"\n  📁 Project XML: {result.data['xml_project']}")
    else:
        console.print(f"[red]Error: {result.error}[/red]")
        raise typer.Exit(1)


@app.command()
def chat(
    message: str = typer.Argument(None, help="Message to send (or interactive mode if empty)"),
    conversation_id: str = typer.Option("default", "--conv", "-c", help="Conversation ID"),
    new: bool = typer.Option(False, "--new", help="Start a new conversation"),
):
    """Chat with JARVIS"""
    jarvis = get_jarvis()

    if message:
        # Single message mode
        result = jarvis.process(
            message,
            conversation_id=conversation_id,
            new_conversation=new
        )
        if result.success:
            console.print(f"\n[cyan]JARVIS:[/cyan] {result.data}\n")
        else:
            console.print(f"[red]Error: {result.error}[/red]")
    else:
        # Interactive mode
        console.print(Panel(
            "[bold cyan]JARVIS Chat[/bold cyan]\n"
            "Type 'quit' or 'exit' to end the conversation.\n"
            "Type 'new' to start a fresh conversation.",
            title="Interactive Mode"
        ))

        while True:
            try:
                user_input = console.input("\n[green]You:[/green] ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit"):
                    console.print("[yellow]Goodbye![/yellow]")
                    break
                if user_input.lower() == "new":
                    conversation_id = f"conv_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    console.print(f"[yellow]Started new conversation: {conversation_id}[/yellow]")
                    continue

                result = jarvis.process(
                    user_input,
                    conversation_id=conversation_id
                )
                if result.success:
                    console.print(f"\n[cyan]JARVIS:[/cyan] {result.data}")
                else:
                    console.print(f"[red]Error: {result.error}[/red]")

            except KeyboardInterrupt:
                console.print("\n[yellow]Goodbye![/yellow]")
                break


@app.command()
def status():
    """Show JARVIS system status"""
    jarvis = get_jarvis()
    status = jarvis.get_status()

    console.print(Panel(
        f"[bold cyan]JARVIS Status[/bold cyan]\n\n"
        f"Initialized: {status['initialized']}\n"
        f"Modules: {', '.join(status['modules'])}\n"
        f"Tasks Completed: {status['memory_stats'].get('total_tasks', 0)}\n"
        f"Success Rate: {status['memory_stats'].get('success_rate', 0):.1%}",
        title="System Status"
    ))


if __name__ == "__main__":
    app()
