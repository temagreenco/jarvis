"""
JARVIS CLI - Command Line Interface

Main entry point for interacting with JARVIS from the terminal.
"""
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from core.jarvis import get_jarvis
from modules.chat_module import ChatModule
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("cli")
console = Console()
app = typer.Typer(
    name="jarvis",
    help="JARVIS - Your Autonomous AI Assistant",
    add_completion=False
)

# Chat subcommand group
chat_app = typer.Typer(help="Chat with JARVIS")
app.add_typer(chat_app, name="chat")


@app.command()
def status():
    """Show JARVIS system status"""
    jarvis = get_jarvis()
    jarvis.initialize()
    status_info = jarvis.get_status()

    console.print(Panel.fit(
        f"""[bold green]JARVIS Status[/bold green]

[bold]Initialized:[/bold] {status_info['initialized']}
[bold]Active Modules:[/bold] {', '.join(status_info['modules']) if status_info['modules'] else 'None'}

[bold]Memory Stats:[/bold]
  • Total Tasks: {status_info['memory_stats'].get('total_tasks', 0)}
  • Successes: {status_info['memory_stats'].get('successes', 0)}
  • Failures: {status_info['memory_stats'].get('failures', 0)}
  • Success Rate: {status_info['memory_stats'].get('success_rate', 0):.1%}""",
        title="[bold blue]JARVIS[/bold blue]",
        border_style="blue"
    ))


@app.command()
def process(
    task: str = typer.Argument(..., help="The task to process"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output")
):
    """Process a task through JARVIS"""
    jarvis = get_jarvis()

    if verbose:
        console.print(f"[dim]Processing task: {task}[/dim]")

    result = jarvis.process(task)

    if result.success:
        console.print(Panel.fit(
            f"[green]Task completed successfully![/green]\n\n{result.data}",
            title="[bold green]Result[/bold green]",
            border_style="green"
        ))
    else:
        console.print(Panel.fit(
            f"[red]Task failed:[/red] {result.error}",
            title="[bold red]Error[/bold red]",
            border_style="red"
        ))
        raise typer.Exit(1)


@chat_app.command("start")
def chat_start(
    conversation_id: Optional[str] = typer.Option(None, "--id", "-i", help="Conversation ID to continue")
):
    """Start an interactive chat session with JARVIS"""
    chat_module = ChatModule()

    # Get or create conversation
    conv_id = conversation_id or chat_module.new_conversation()

    console.print(Panel.fit(
        f"""Welcome to JARVIS Chat!

[bold]Conversation ID:[/bold] {conv_id}

Commands:
  • Type your message and press Enter
  • Type [bold]/new[/bold] to start a fresh conversation
  • Type [bold]/clear[/bold] to clear history
  • Type [bold]/quit[/bold] or [bold]/exit[/bold] to exit
  • Type [bold]/help[/bold] for more commands""",
        title="[bold blue]JARVIS Chat[/bold blue]",
        border_style="blue"
    ))

    while True:
        try:
            # Get user input
            user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ("/quit", "/exit", "/q"):
                    console.print("[dim]Goodbye![/dim]")
                    break

                elif command == "/new":
                    conv_id = chat_module.new_conversation()
                    console.print(f"[green]Started new conversation: {conv_id}[/green]")
                    continue

                elif command == "/clear":
                    chat_module.clear_conversation(conv_id)
                    console.print("[green]Conversation history cleared.[/green]")
                    continue

                elif command == "/help":
                    console.print("""
[bold]Chat Commands:[/bold]
  /new      - Start a new conversation
  /clear    - Clear conversation history
  /history  - Show recent messages
  /quit     - Exit chat
  /help     - Show this help""")
                    continue

                elif command == "/history":
                    conv = chat_module.store.get_or_create(conv_id)
                    if conv.messages:
                        console.print("\n[bold]Recent Messages:[/bold]")
                        for msg in conv.messages[-10:]:
                            role_color = "cyan" if msg.role == "user" else "green"
                            console.print(f"[{role_color}]{msg.role}:[/{role_color}] {msg.content[:100]}...")
                    else:
                        console.print("[dim]No messages yet.[/dim]")
                    continue

                else:
                    console.print(f"[yellow]Unknown command: {command}[/yellow]")
                    continue

            # Process chat message
            with console.status("[bold blue]Thinking...[/bold blue]"):
                result = chat_module.run(
                    task="chat",
                    message=user_input,
                    conversation_id=conv_id
                )

            if result.success:
                response = result.data.get("response", "No response generated.")
                console.print(f"\n[bold green]JARVIS:[/bold green] {response}")
            else:
                console.print(f"\n[bold red]Error:[/bold red] {result.error}")

        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted. Type /quit to exit.[/dim]")
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break


@chat_app.command("ask")
def chat_ask(
    message: str = typer.Argument(..., help="Message to send"),
    conversation_id: str = typer.Option("default", "--id", "-i", help="Conversation ID")
):
    """Send a single message to JARVIS"""
    chat_module = ChatModule()

    with console.status("[bold blue]Thinking...[/bold blue]"):
        result = chat_module.run(
            task="chat",
            message=message,
            conversation_id=conversation_id
        )

    if result.success:
        response = result.data.get("response", "No response generated.")
        console.print(Markdown(response))
    else:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        raise typer.Exit(1)


@chat_app.command("list")
def chat_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of conversations to show")
):
    """List recent conversations"""
    chat_module = ChatModule()
    conversations = chat_module.list_conversations(limit)

    if not conversations:
        console.print("[dim]No conversations found.[/dim]")
        return

    console.print("[bold]Recent Conversations:[/bold]\n")
    for conv in conversations:
        console.print(f"  [cyan]{conv['id']}[/cyan] - {conv['message_count']} messages")
        if conv['last_message']:
            console.print(f"    [dim]{conv['last_message']}...[/dim]")


@app.command()
def telegram():
    """Start the Telegram bot interface"""
    from interfaces.telegram_bot import run_telegram_bot

    if not settings.telegram_token:
        console.print("[red]Error: Telegram token not configured.[/red]")
        console.print("Set JARVIS_TELEGRAM_TOKEN environment variable.")
        raise typer.Exit(1)

    console.print("[bold blue]Starting JARVIS Telegram Bot...[/bold blue]")
    run_telegram_bot()


@app.command()
def version():
    """Show JARVIS version"""
    console.print("[bold blue]JARVIS[/bold blue] v0.1.0")


def main():
    """Main entry point"""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("CLI error")
        sys.exit(1)


if __name__ == "__main__":
    main()
