"""
JARVIS CLI - Command Line Interface

Interactive chat and task execution from the terminal.
"""
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt

from core.jarvis import get_jarvis
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("cli")
console = Console()
app = typer.Typer(
    name="jarvis",
    help="JARVIS - Autonomous AI System",
    add_completion=False
)


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
    console.print(Panel(banner, title="[bold cyan]Autonomous AI System[/]", border_style="cyan"))


@app.command()
def chat(
    message: Optional[str] = typer.Argument(None, help="Message to send (or enter interactive mode)"),
    conversation: str = typer.Option("default", "-c", "--conversation", help="Conversation ID"),
    system_prompt: Optional[str] = typer.Option(None, "-s", "--system", help="Custom system prompt"),
):
    """
    Chat with JARVIS.

    If no message is provided, enters interactive chat mode.
    """
    jarvis = get_jarvis()
    jarvis.initialize()

    if message:
        # Single message mode
        _send_message(jarvis, message, conversation, system_prompt)
    else:
        # Interactive mode
        _interactive_chat(jarvis, conversation, system_prompt)


def _send_message(jarvis, message: str, conversation: str, system_prompt: Optional[str]):
    """Send a single message and print response"""
    with console.status("[cyan]Thinking...[/]"):
        result = jarvis.process(
            message,
            conversation_id=conversation,
            system_prompt=system_prompt
        )

    if result.success:
        response = result.data.get("response", "No response")
        console.print(Panel(
            Markdown(response),
            title="[bold green]JARVIS[/]",
            border_style="green"
        ))
    else:
        console.print(f"[red]Error: {result.error}[/]")


def _interactive_chat(jarvis, conversation: str, system_prompt: Optional[str]):
    """Interactive chat loop"""
    print_banner()
    console.print("[dim]Type 'exit' or 'quit' to end the conversation[/]")
    console.print("[dim]Type 'clear' to clear conversation history[/]")
    console.print("[dim]Type 'new' to start a new conversation[/]")
    console.print()

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/]")

            if not user_input.strip():
                continue

            # Handle special commands
            cmd = user_input.strip().lower()
            if cmd in ("exit", "quit", "bye"):
                console.print("[dim]Goodbye![/]")
                break
            elif cmd == "clear":
                from modules.chat import ChatModule
                chat_module = ChatModule()
                chat_module.clear_conversation(conversation)
                console.print("[dim]Conversation cleared.[/]")
                continue
            elif cmd == "new":
                conversation = Prompt.ask("New conversation ID", default="default")
                console.print(f"[dim]Started new conversation: {conversation}[/]")
                continue
            elif cmd == "status":
                status = jarvis.get_status()
                console.print(Panel(str(status), title="Status"))
                continue
            elif cmd == "help":
                _print_help()
                continue

            # Send message
            _send_message(jarvis, user_input, conversation, system_prompt)

        except KeyboardInterrupt:
            console.print("\n[dim]Use 'exit' to quit[/]")
        except EOFError:
            break


def _print_help():
    """Print help information"""
    help_text = """
**Commands:**
- `exit` / `quit` - End the conversation
- `clear` - Clear conversation history
- `new` - Start a new conversation
- `status` - Show JARVIS status
- `help` - Show this help

**Tips:**
- Ask any question or give any task
- JARVIS will route to the appropriate module
- For video editing, mention 'video' or 'reel' in your message
"""
    console.print(Panel(Markdown(help_text), title="Help"))


@app.command()
def process(
    task: str = typer.Argument(..., help="Task to process"),
    video: Optional[str] = typer.Option(None, "-v", "--video", help="Video file path for video tasks"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output directory"),
):
    """
    Process a task through JARVIS.

    This routes the task to the appropriate module based on content.
    """
    jarvis = get_jarvis()
    jarvis.initialize()

    kwargs = {}
    if video:
        kwargs["video_path"] = video
    if output:
        kwargs["output_dir"] = output

    with console.status(f"[cyan]Processing: {task[:50]}...[/]"):
        result = jarvis.process(task, **kwargs)

    if result.success:
        console.print(Panel(
            str(result.data),
            title="[bold green]Result[/]",
            border_style="green"
        ))
    else:
        console.print(f"[red]Error: {result.error}[/]")

    console.print(f"[dim]Duration: {result.duration:.2f}s[/]")


@app.command()
def status():
    """Show JARVIS system status."""
    jarvis = get_jarvis()
    jarvis.initialize()

    status = jarvis.get_status()

    console.print(Panel(
        f"Initialized: {status['initialized']}\n"
        f"Modules: {', '.join(m['name'] for m in status['modules'])}\n"
        f"Memory stats: {status['memory_stats']}",
        title="[bold cyan]JARVIS Status[/]"
    ))


@app.command()
def modules():
    """List available modules."""
    jarvis = get_jarvis()
    jarvis.initialize()

    status = jarvis.get_status()

    console.print("[bold]Available Modules:[/]\n")
    for module in status['modules']:
        console.print(f"  [cyan]{module['name']}[/] v{module['version']}")
        console.print(f"    {module['description']}")
        console.print()


@app.command()
def telegram():
    """Run the Telegram bot interface."""
    from interfaces.telegram_bot import run_bot

    console.print("[bold cyan]Starting JARVIS Telegram Bot...[/]")
    console.print("[dim]Press Ctrl+C to stop[/]")

    try:
        run_bot()
    except ValueError as e:
        console.print(f"[red]Error: {e}[/]")
        console.print("[dim]Set JARVIS_TELEGRAM_TOKEN in .env file[/]")
    except KeyboardInterrupt:
        console.print("\n[dim]Bot stopped[/]")


def main():
    """Main entry point"""
    app()


if __name__ == "__main__":
    main()
