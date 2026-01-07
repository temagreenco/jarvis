"""
JARVIS CLI - Command Line Interface
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

# Main app
app = typer.Typer(
    name="jarvis",
    help="JARVIS - Autonomous AI System",
    add_completion=False
)

# Chat subcommands
chat_app = typer.Typer(help="Chat with JARVIS")
app.add_typer(chat_app, name="chat")


@app.command()
def status():
    """Show JARVIS system status"""
    jarvis = get_jarvis()
    jarvis.initialize()
    status_info = jarvis.get_status()

    console.print(Panel.fit(
        f"[bold green]JARVIS Status[/bold green]\n\n"
        f"Initialized: {status_info['initialized']}\n"
        f"Modules: {len(status_info['modules'])}\n"
        f"Memory entries: {status_info['memory_stats'].get('total_tasks', 0)}",
        title="Status"
    ))

    if status_info["modules"]:
        console.print("\n[bold]Loaded Modules:[/bold]")
        for module in status_info["modules"]:
            console.print(f"  • {module['name']} v{module['version']} - {module['description']}")


@app.command()
def process(task: str = typer.Argument(..., help="Task to process")):
    """Process a task through JARVIS"""
    jarvis = get_jarvis()
    jarvis.initialize()

    with console.status("[bold green]Processing task..."):
        result = jarvis.process(task)

    if result.success:
        console.print(Panel(
            str(result.data) if result.data else "Task completed successfully",
            title="[green]Success[/green]",
            border_style="green"
        ))
    else:
        console.print(Panel(
            result.error or "Unknown error",
            title="[red]Failed[/red]",
            border_style="red"
        ))


@app.command()
def version():
    """Show JARVIS version"""
    console.print("[bold]JARVIS[/bold] v0.1.0")
    console.print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")


@chat_app.command("start")
def chat_start(
    conversation_id: Optional[str] = typer.Option(None, "--id", "-i", help="Continue existing conversation")
):
    """Start an interactive chat session"""
    from modules.chat_module import ChatModule

    chat_module = ChatModule()

    # Check Ollama
    if not chat_module.check_ollama_health():
        console.print("[bold red]Error:[/bold red] Ollama is not running. Please start Ollama first.")
        console.print("  Run: [cyan]ollama serve[/cyan]")
        raise typer.Exit(1)

    # Get or create conversation
    if conversation_id:
        conversation = chat_module.get_conversation(conversation_id)
        if not conversation:
            console.print(f"[yellow]Conversation {conversation_id} not found. Starting new conversation.[/yellow]")
            conversation = chat_module.new_conversation()
    else:
        conversation = chat_module.new_conversation()

    console.print(Panel.fit(
        "[bold green]JARVIS Chat[/bold green]\n\n"
        "Commands:\n"
        "  /new    - Start new conversation\n"
        "  /clear  - Clear current conversation\n"
        "  /history - Show conversation history\n"
        "  /quit   - Exit chat\n"
        "  /help   - Show this help",
        title="Welcome"
    ))
    console.print(f"[dim]Conversation ID: {conversation.id}[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold blue]You[/bold blue]")

            if not user_input.strip():
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.strip().lower()

                if command == "/quit" or command == "/exit":
                    console.print("[dim]Goodbye![/dim]")
                    break

                elif command == "/new":
                    conversation = chat_module.new_conversation()
                    console.print(f"[green]Started new conversation: {conversation.id}[/green]")
                    continue

                elif command == "/clear":
                    chat_module.clear_conversation(conversation.id)
                    console.print("[green]Conversation cleared[/green]")
                    continue

                elif command == "/history":
                    if not conversation.messages:
                        console.print("[dim]No messages in conversation[/dim]")
                    else:
                        for msg in conversation.messages:
                            role_color = "blue" if msg.role == "user" else "green"
                            console.print(f"[{role_color}]{msg.role.upper()}:[/{role_color}] {msg.content[:100]}...")
                    continue

                elif command == "/help":
                    console.print(
                        "/new    - Start new conversation\n"
                        "/clear  - Clear current conversation\n"
                        "/history - Show conversation history\n"
                        "/quit   - Exit chat\n"
                        "/help   - Show this help"
                    )
                    continue

                else:
                    console.print(f"[yellow]Unknown command: {command}[/yellow]")
                    continue

            # Send message
            with console.status("[dim]Thinking...[/dim]"):
                try:
                    response, conversation = chat_module.chat(user_input, conversation.id)
                    console.print(f"\n[bold green]JARVIS[/bold green]: ", end="")
                    console.print(Markdown(response))
                    console.print()
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")

        except KeyboardInterrupt:
            console.print("\n[dim]Use /quit to exit[/dim]")
            continue


@chat_app.command("ask")
def chat_ask(
    message: str = typer.Argument(..., help="Message to send"),
    conversation_id: Optional[str] = typer.Option(None, "--id", "-i", help="Conversation ID")
):
    """Send a single message to JARVIS"""
    from modules.chat_module import ChatModule

    chat_module = ChatModule()

    if not chat_module.check_ollama_health():
        console.print("[bold red]Error:[/bold red] Ollama is not running.")
        raise typer.Exit(1)

    with console.status("[dim]Thinking...[/dim]"):
        try:
            response, conversation = chat_module.chat(message, conversation_id)
            console.print(Markdown(response))
            console.print(f"\n[dim]Conversation ID: {conversation.id}[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


@chat_app.command("list")
def chat_list(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of conversations to show")
):
    """List recent conversations"""
    from modules.chat_module import ChatModule

    chat_module = ChatModule()
    conversations = chat_module.list_conversations(limit)

    if not conversations:
        console.print("[dim]No conversations found[/dim]")
        return

    console.print(f"[bold]Recent Conversations ({len(conversations)}):[/bold]\n")
    for conv in conversations:
        msg_count = len(conv.messages)
        title = conv.title or "[No title]"
        console.print(f"  [cyan]{conv.id[:8]}...[/cyan] {title} ({msg_count} messages)")


# Telegram subcommands
telegram_app = typer.Typer(help="Telegram bot commands")
app.add_typer(telegram_app, name="telegram")


@telegram_app.command("start")
def telegram_start():
    """Start the Telegram bot"""
    if not settings.telegram_token:
        console.print("[bold red]Error:[/bold red] JARVIS_TELEGRAM_TOKEN not set")
        console.print("Set it in your environment or .env file")
        raise typer.Exit(1)

    try:
        from interfaces.telegram_bot import run_bot
        console.print("[bold green]Starting Telegram bot...[/bold green]")
        run_bot()
    except ImportError as e:
        console.print(f"[red]Could not import Telegram bot: {e}[/red]")
        raise typer.Exit(1)


def main():
    """Entry point"""
    app()


if __name__ == "__main__":
    main()
