#!/usr/bin/env python3
"""
Crispy Example - Generate viral video scripts for beauty professionals

Usage:
    python examples/crispy_example.py

Make sure to set your API keys in .env file first!
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

# Import Crispy components
from modules.script_generator import ScriptGeneratorModule
from prompts.beauty_prompts import register_beauty_prompts
from core.prompt_registry import get_registry

console = Console()


async def main():
    # Initialize
    console.print("\n[bold cyan]🎬 Crispy - AI Script Generator for Beauty Professionals[/bold cyan]\n")

    # Register prompts
    register_beauty_prompts()

    # Create module
    generator = ScriptGeneratorModule()

    # Show available options
    options = generator.get_available_options()
    console.print("[dim]Available options:[/dim]")
    console.print(f"  Niches: {', '.join(options['niches'])}")
    console.print(f"  Statuses: {', '.join(options['statuses'])}")
    console.print(f"  Goals: {', '.join(options['goals'])}")
    console.print(f"  Tones: {', '.join(options['tones'])}")
    console.print(f"  Providers: {', '.join(options['providers'])}")
    console.print()

    # Example generation
    console.print("[bold green]Generating scripts...[/bold green]\n")

    try:
        result = await generator.generate_scripts(
            niche="nails",
            status="practitioner",
            goal="exposure",
            tone="casual",
            topic="גל ציפורניים",
            num_scripts=3,
            provider="openai"  # or "gemini", "claude"
        )

        # Display results
        console.print(f"[dim]Provider: {result.provider_used} | Model: {result.model_used}[/dim]")
        console.print(f"[dim]Tokens: {result.tokens_used} | Cost: ${result.cost_usd:.4f}[/dim]\n")

        for i, script in enumerate(result.scripts, 1):
            console.print(Panel(
                f"[bold yellow]🎣 HOOK:[/bold yellow]\n{script.hook}\n\n"
                f"[bold blue]📝 BODY:[/bold blue]\n{script.body}\n\n"
                f"[bold green]📢 CTA:[/bold green]\n{script.cta}\n\n"
                f"[dim]Hashtags: {' '.join(script.hashtags)}[/dim]\n"
                f"[dim]Duration: {script.duration_estimate}[/dim]",
                title=f"Script {i}",
                border_style="cyan"
            ))
            console.print()

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("\n[dim]Make sure you have set your API keys in .env file![/dim]")
        console.print("[dim]Copy .env.example to .env and add your keys.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
