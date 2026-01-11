#!/usr/bin/env python3
"""
JARVIS CLI - Command Line Interface
Interactive chat and task execution interface.
"""
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from core.jarvis import get_jarvis
from config.settings import get_settings

app = typer.Typer(
    name="jarvis",
    help="JARVIS - Autonomous AI System",
    add_completion=False
)
console = Console()


def print_banner():
    """Print JARVIS welcome banner"""
    banner = """
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
    """
    console.print(Panel(banner, title="v0.1.0", border_style="blue"))


@app.command()
def chat(
    message: Optional[str] = typer.Argument(None, help="Initial message to send"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override chat model"),
    temperature: Optional[float] = typer.Option(None, "--temp", "-t", help="Response temperature (0.0-1.0)"),
    no_banner: bool = typer.Option(False, "--no-banner", help="Skip welcome banner")
):
    """Start an interactive chat session with JARVIS"""
    settings = get_settings()
    jarvis = get_jarvis()
    jarvis.initialize()

    if not no_banner:
        print_banner()
        console.print("[dim]Type 'exit' or 'quit' to end the session[/dim]")
        console.print("[dim]Type 'clear' to reset conversation history[/dim]")
        console.print("[dim]Type 'status' to see system status[/dim]")
        console.print()

    # Get the chat module directly for history management
    from modules.chat import ChatModule
    chat_module = None
    for module in jarvis.router.modules:
        if isinstance(module, ChatModule):
            chat_module = module
            break

    # Build kwargs for chat
    chat_kwargs = {}
    if temperature is not None:
        chat_kwargs["temperature"] = temperature

    # Process initial message if provided
    if message:
        _process_message(jarvis, message, chat_kwargs)

    # Interactive loop
    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ").strip()

            if not user_input:
                continue

            # Handle special commands
            if user_input.lower() in ("exit", "quit", "bye"):
                console.print("[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "clear":
                if chat_module:
                    chat_module.clear_history()
                console.print("[dim]Conversation history cleared.[/dim]")
                continue

            if user_input.lower() == "status":
                status = jarvis.get_status()
                console.print(Panel(str(status), title="System Status", border_style="green"))
                continue

            if user_input.lower() == "help":
                _show_help()
                continue

            # Process the message
            _process_message(jarvis, user_input, chat_kwargs)

        except KeyboardInterrupt:
            console.print("\n[dim]Session interrupted. Goodbye![/dim]")
            break
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break


def _process_message(jarvis, message: str, kwargs: dict):
    """Process a message and display the response"""
    with console.status("[bold green]Thinking...[/bold green]"):
        result = jarvis.process(message, **kwargs)

    if result.success:
        console.print()
        console.print("[bold green]JARVIS:[/bold green]", end=" ")
        # Try to render as markdown for better formatting
        try:
            console.print(Markdown(result.data))
        except Exception:
            console.print(result.data)
        console.print()
    else:
        console.print(f"[bold red]Error:[/bold red] {result.error}")


def _show_help():
    """Show help information"""
    help_text = """
## Available Commands

- **exit/quit/bye** - End the chat session
- **clear** - Reset conversation history
- **status** - Show system status
- **help** - Show this help message

## Chat Features

JARVIS uses a local LLM via Ollama for conversations. You can:
- Ask questions on any topic
- Request explanations
- Get help with tasks

## Modules

JARVIS has specialized modules for specific tasks:
- **Video Editor** - Create viral short-form content from videos

Just describe what you want to do, and JARVIS will route to the right module.
"""
    console.print(Panel(Markdown(help_text), title="Help", border_style="cyan"))


@app.command()
def process(
    task: str = typer.Argument(..., help="Task to process"),
):
    """Process a single task through JARVIS"""
    jarvis = get_jarvis()
    jarvis.initialize()

    with console.status("[bold green]Processing...[/bold green]"):
        result = jarvis.process(task)

    if result.success:
        console.print(Panel(str(result.data), title="Result", border_style="green"))
    else:
        console.print(Panel(str(result.error), title="Error", border_style="red"))


@app.command()
def status():
    """Show JARVIS system status"""
    jarvis = get_jarvis()
    jarvis.initialize()

    status = jarvis.get_status()

    console.print(Panel.fit(
        f"[bold]Initialized:[/bold] {status['initialized']}\n"
        f"[bold]Modules:[/bold] {', '.join(status['modules']) or 'None'}\n"
        f"[bold]Memory Stats:[/bold] {status['memory_stats']}",
        title="JARVIS Status",
        border_style="blue"
    ))


@app.command()
def modules():
    """List available modules"""
    jarvis = get_jarvis()
    jarvis.initialize()

    module_list = jarvis.router.list_modules()
    if module_list:
        console.print("[bold]Available Modules:[/bold]")
        for name in module_list:
            module = next((m for m in jarvis.router.modules if m.name == name), None)
            if module:
                console.print(f"  - [cyan]{module.name}[/cyan]: {module.description}")
    else:
        console.print("[dim]No modules loaded[/dim]")


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()
