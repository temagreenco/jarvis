"""
Main Agent Orchestrator
=======================

This ties everything together into a usable agent.

ARCHITECTURE:
-------------
                    ┌─────────────────┐
                    │     Agent       │  ← Main entry point
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ LLMClient│  │ ReActLoop│  │  Tools   │
        └──────────┘  └──────────┘  └──────────┘
              │              │              │
              │              │              │
              ▼              ▼              ▼
        ┌─────────────────────────────────────┐
        │          LLM Backend                │
        │   (Ollama / vLLM / OpenAI)         │
        └─────────────────────────────────────┘

HOW TO USE:
-----------
# Simple usage
agent = Agent()
response = await agent.chat("What files are in this directory?")
print(response)

# Interactive mode
await agent.interactive()

WHAT THE AGENT DOES:
--------------------
1. Receives user input
2. Runs ReAct loop (Think → Act → Observe)
3. Returns final response
4. Maintains conversation history
"""

from dataclasses import dataclass, field
from typing import Callable
import asyncio

from .llm import LLMClient, Message
from .reasoning import ReActLoop, ReActResult
from tools import ALL_TOOLS, BaseTool
from prompts import get_system_prompt
from config import settings


@dataclass
class ConversationTurn:
    """
    One exchange in the conversation.

    USER → AGENT response pair.
    Also tracks what tools were used (for debugging/logging).
    """
    user_message: str
    agent_response: str
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0


class Agent:
    """
    The main JARVIS agent.

    LIFECYCLE:
    ----------
    1. Create: agent = Agent()
    2. Use: response = await agent.chat("Hello")
    3. Continue: response = await agent.chat("Now do X")
    4. Reset: agent.reset() to clear history

    FEATURES:
    ---------
    - Maintains conversation history
    - Supports tool use via ReAct loop
    - Configurable via settings
    - Verbose mode for debugging
    """

    def __init__(
        self,
        tools: list[BaseTool] | None = None,
        verbose: bool | None = None
    ):
        """
        Initialize the agent.

        PARAMETERS:
        -----------
        tools: Custom tools to use. If None, uses ALL_TOOLS.
        verbose: Show reasoning steps. If None, uses settings.

        WHY ALLOW CUSTOM TOOLS?
        -----------------------
        You might want to:
        - Test with limited tools
        - Add custom tools for specific use cases
        - Disable certain capabilities
        """
        self.verbose = verbose if verbose is not None else settings.agent.verbose

        # Initialize LLM client
        self.llm = LLMClient()

        # Initialize tools
        if tools is None:
            self.tools = [ToolClass() for ToolClass in ALL_TOOLS]
        else:
            self.tools = tools

        # Initialize ReAct loop
        self.react = ReActLoop(
            llm_client=self.llm,
            tools=self.tools,
            verbose=self.verbose
        )

        # Conversation state
        self.history: list[Message] = []
        self.turns: list[ConversationTurn] = []
        self.system_prompt = get_system_prompt()

        if self.verbose:
            print(f"Agent initialized with {len(self.tools)} tools:")
            for tool in self.tools:
                print(f"  - {tool.name}: {tool.description[:50]}...")

    async def chat(self, message: str) -> str:
        """
        Send a message and get a response.

        This is the main interface for using the agent.

        FLOW:
        -----
        1. Run ReAct loop with message
        2. Store result in history
        3. Return response text

        PARAMETERS:
        -----------
        message: User's input

        RETURNS:
        --------
        Agent's response text
        """
        # Run the ReAct loop
        result = await self.react.run(
            user_message=message,
            system_prompt=self.system_prompt,
            conversation_history=self.history if self.history else None
        )

        # Update history
        self.history.append(Message(role="user", content=message))
        self.history.append(Message(role="assistant", content=result.response))

        # Trim history if too long
        max_history = settings.agent.conversation_history_limit * 2  # *2 for user+assistant pairs
        if len(self.history) > max_history:
            self.history = self.history[-max_history:]

        # Track turn
        tools_used = [step.tool_name for step in result.steps if step.tool_name]
        self.turns.append(ConversationTurn(
            user_message=message,
            agent_response=result.response,
            tools_used=tools_used,
            iterations=result.iterations
        ))

        return result.response

    async def interactive(self):
        """
        Run an interactive chat session.

        WHAT THIS DOES:
        ---------------
        Starts a REPL (Read-Eval-Print Loop):
        1. Print prompt
        2. Read user input
        3. Process with agent
        4. Print response
        5. Repeat

        SPECIAL COMMANDS:
        -----------------
        - 'exit' or 'quit': End session
        - 'reset': Clear conversation history
        - 'tools': List available tools
        - 'history': Show conversation history
        """
        print("\n" + "="*60)
        print("JARVIS Agent - Interactive Mode")
        print("="*60)
        print("Commands: 'exit', 'reset', 'tools', 'history'")
        print("="*60 + "\n")

        while True:
            try:
                # Get user input
                user_input = input("\nYou: ").strip()

                # Handle special commands
                if user_input.lower() in ('exit', 'quit'):
                    print("\nGoodbye!")
                    break

                elif user_input.lower() == 'reset':
                    self.reset()
                    print("Conversation history cleared.")
                    continue

                elif user_input.lower() == 'tools':
                    print("\nAvailable tools:")
                    for tool in self.tools:
                        print(f"  - {tool.name}: {tool.description}")
                    continue

                elif user_input.lower() == 'history':
                    if not self.turns:
                        print("No conversation history.")
                    else:
                        print(f"\nConversation ({len(self.turns)} turns):")
                        for i, turn in enumerate(self.turns, 1):
                            print(f"\n[{i}] You: {turn.user_message[:100]}...")
                            print(f"    Agent: {turn.agent_response[:100]}...")
                            if turn.tools_used:
                                print(f"    Tools: {', '.join(turn.tools_used)}")
                    continue

                elif not user_input:
                    continue

                # Process message
                response = await self.chat(user_input)
                print(f"\nJARVIS: {response}")

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'exit' to quit.")
                continue

            except Exception as e:
                print(f"\nError: {e}")
                continue

    def reset(self):
        """
        Clear conversation history.

        USE WHEN:
        ---------
        - Starting a new task
        - Agent seems confused
        - Testing
        """
        self.history = []
        self.turns = []

        if self.verbose:
            print("Agent reset - conversation history cleared.")

    def add_tool(self, tool: BaseTool):
        """
        Add a new tool to the agent.

        HOW TO USE:
        -----------
        from tools.base import BaseTool, ToolParameter

        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something"
            parameters = [...]

            async def execute(self, **kwargs):
                ...

        agent.add_tool(MyTool())

        WHY DYNAMIC TOOLS?
        ------------------
        You might want to add tools based on:
        - User permissions
        - Current task
        - Available services
        """
        self.tools.append(tool)
        # Rebuild ReAct loop with new tools
        self.react = ReActLoop(
            llm_client=self.llm,
            tools=self.tools,
            verbose=self.verbose
        )

        if self.verbose:
            print(f"Added tool: {tool.name}")

    def get_stats(self) -> dict:
        """
        Get usage statistics.

        RETURNS:
        --------
        Dict with:
        - total_turns: Number of exchanges
        - total_iterations: Total ReAct iterations
        - tools_used: Count of each tool used
        """
        tools_used: dict[str, int] = {}
        total_iterations = 0

        for turn in self.turns:
            total_iterations += turn.iterations
            for tool_name in turn.tools_used:
                tools_used[tool_name] = tools_used.get(tool_name, 0) + 1

        return {
            "total_turns": len(self.turns),
            "total_iterations": total_iterations,
            "tools_used": tools_used,
            "history_length": len(self.history)
        }


# Convenience function for quick usage
async def quick_chat(message: str) -> str:
    """
    Quick one-shot chat without creating an Agent instance.

    USAGE:
    ------
    from core.agent import quick_chat
    response = await quick_chat("What's 2+2?")
    print(response)

    NOTE:
    -----
    Creates a new agent each time - no conversation history.
    For multi-turn conversations, create an Agent instance.
    """
    agent = Agent(verbose=False)
    return await agent.chat(message)
