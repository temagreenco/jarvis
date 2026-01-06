"""
JARVIS CLI - Command Line Interface

Usage:
    jarvis process --video /path/to/video.mp4 --reels 5
    jarvis status
    jarvis serve --port 8000
"""
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.jarvis import get_jarvis
from config.settings import settings

app = typer.Typer(
    name="jarvis",
    help="JARVIS - Autonomous AI System for viral content creation",
    no_args_is_help=True,
)
console = Console()


@app.command()
def process(
    video: Path = typer.Option(..., "--video", "-v", help="Path to source video file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    reels: int = typer.Option(8, "--reels", "-n", help="Number of reels to generate"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without processing"),
) -> None:
    """Process a video and create viral short-form reels."""
    if not video.exists():
        console.print(f"[red]Error:[/red] Video file not found: {video}")
        raise typer.Exit(1)

    output_dir = output or settings.output_dir

    if dry_run:
        console.print(f"[yellow]Dry run mode[/yellow]")
        console.print(f"  Video: {video}")
        console.print(f"  Output: {output_dir}")
        console.print(f"  Reels: {reels}")
        console.print("[green]Validation passed![/green]")
        return

    jarvis = get_jarvis()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing video...", total=None)

        result = jarvis.process(
            task="Create viral reels from video",
            video_path=str(video),
            output_dir=str(output_dir),
            num_reels=reels,
        )

        progress.update(task, completed=True)

    if result.success:
        console.print("\n[green]Success![/green]")
        console.print(f"Duration: {result.duration:.2f}s")

        if result.data:
            table = Table(title="Generated Reels")
            table.add_column("File", style="cyan")
            table.add_column("Hook", style="green")

            reels_list = result.data.get("reels", [])
            moments = result.data.get("moments", [])

            for i, reel_path in enumerate(reels_list):
                hook = moments[i]["hook"][:50] + "..." if i < len(moments) else ""
                table.add_row(Path(reel_path).name, hook)

            console.print(table)
            console.print(f"\nOutput directory: {output_dir}")
    else:
        console.print(f"\n[red]Failed:[/red] {result.error}")
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Show JARVIS system status."""
    jarvis = get_jarvis()
    status_info = jarvis.get_status()

    console.print("\n[bold cyan]JARVIS System Status[/bold cyan]\n")

    # System info
    table = Table(show_header=False)
    table.add_column("Property", style="dim")
    table.add_column("Value")

    table.add_row("Initialized", "Yes" if status_info["initialized"] else "No")
    table.add_row("Total Tasks", str(status_info["memory_stats"]["total_tasks"]))
    table.add_row("Success Rate", f"{status_info['memory_stats']['success_rate']:.1%}")

    console.print(table)

    # Modules
    console.print("\n[bold]Registered Modules:[/bold]")
    for module in status_info["modules"]:
        status_color = "green" if module["status"] == "pending" else "yellow"
        console.print(f"  [{status_color}]{module['name']}[/{status_color}] v{module['version']} - {module['description']}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the JARVIS HTTP API server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error:[/red] uvicorn not installed. Run: pip install uvicorn")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Starting JARVIS API Server[/bold cyan]")
    console.print(f"  Host: {host}")
    console.print(f"  Port: {port}")
    console.print(f"  Docs: http://{host}:{port}/docs\n")

    uvicorn.run(
        "api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of entries to show"),
    failures: bool = typer.Option(False, "--failures", "-f", help="Show only failures"),
) -> None:
    """Show task history from memory."""
    jarvis = get_jarvis()

    if failures:
        entries = jarvis.memory.get_failures(limit)
        title = "Recent Failures"
    else:
        entries = jarvis.memory.get_recent(limit)
        title = "Recent Tasks"

    if not entries:
        console.print("[dim]No entries found.[/dim]")
        return

    table = Table(title=title)
    table.add_column("Time", style="dim")
    table.add_column("Module", style="cyan")
    table.add_column("Task", max_width=40)
    table.add_column("Status")
    table.add_column("Duration", justify="right")

    for entry in entries:
        status_str = "[green]OK[/green]" if entry.success else f"[red]{entry.error[:20]}...[/red]"
        table.add_row(
            entry.timestamp[:19],
            entry.module,
            entry.task[:40] + "..." if len(entry.task) > 40 else entry.task,
            status_str,
            f"{entry.duration:.2f}s",
        )

    console.print(table)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
