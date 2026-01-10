#!/usr/bin/env python3
"""
JARVIS Agent - Main Entry Point
================================

HOW TO RUN:
-----------
# Interactive mode (chat in terminal)
python main.py

# Single command
python main.py --message "What files are here?"

# With custom settings
AGENT_LLM_MODEL=qwen2.5:72b python main.py

BEFORE RUNNING:
---------------
1. Make sure your LLM backend is running:

   # Option A: Ollama (simple)
   ollama serve &
   ollama pull llama3.1:8b

   # Option B: vLLM (fast, for production)
   python -m vllm.entrypoints.openai.api_server \
     --model meta-llama/Llama-3.1-70B-Instruct

2. Install dependencies:
   pip install -r requirements.txt

ON RUNPOD:
----------
RunPod pods come with Ollama often pre-installed.
Check with: which ollama

If not, install:
curl -fsSL https://ollama.com/install.sh | sh
"""

import asyncio
import argparse
import sys

# Add parent directory to path for imports
# This allows running as: python main.py
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.agent import Agent
from config import settings


def print_banner():
    """Print startup banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║          ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗         ║
    ║          ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝         ║
    ║          ██║███████║██████╔╝██║   ██║██║███████╗         ║
    ║     ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║         ║
    ║     ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║         ║
    ║      ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝         ║
    ║                                                           ║
    ║           Autonomous AI Assistant v0.1.0                  ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_config():
    """Print current configuration."""
    print("\nConfiguration:")
    print(f"  LLM Provider: {settings.llm.provider}")
    print(f"  LLM Model: {settings.llm.model}")
    print(f"  LLM URL: {settings.llm.base_url}")
    print(f"  Max Iterations: {settings.agent.max_iterations}")
    print(f"  Workspace: {settings.agent.workspace}")
    print()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="JARVIS - Autonomous AI Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Interactive mode
  python main.py -m "List all files"      # Single message
  python main.py --verbose                # Show reasoning steps
  python main.py --quiet                  # Minimal output
        """
    )

    parser.add_argument(
        "-m", "--message",
        type=str,
        help="Single message to process (non-interactive)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed reasoning steps"
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Minimal output (no banner, etc.)"
    )

    parser.add_argument(
        "--config",
        action="store_true",
        help="Show current configuration and exit"
    )

    args = parser.parse_args()

    # Show config and exit if requested
    if args.config:
        print_config()
        return

    # Determine verbosity
    verbose = args.verbose if args.verbose else settings.agent.verbose
    if args.quiet:
        verbose = False

    # Print banner unless quiet
    if not args.quiet:
        print_banner()
        print_config()

    # Create agent
    try:
        agent = Agent(verbose=verbose)
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        print("\nMake sure your LLM backend is running:")
        print("  ollama serve    # if using Ollama")
        return

    # Single message mode
    if args.message:
        try:
            response = await agent.chat(args.message)
            if not verbose:
                print(f"\n{response}")
        except Exception as e:
            print(f"Error: {e}")
        return

    # Interactive mode
    try:
        await agent.interactive()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")


if __name__ == "__main__":
    asyncio.run(main())
