"""
ReAct Reasoning Loop
====================

This is the BRAIN of the agent - the core logic that makes it work.

WHAT IS ReAct?
--------------
ReAct = Reasoning + Acting

It's a pattern where the agent:
1. THINKS about what to do (reasoning)
2. ACTS by using a tool (acting)
3. OBSERVES the result (observation)
4. REPEATS until task is complete

PAPER: "ReAct: Synergizing Reasoning and Acting in Language Models"
https://arxiv.org/abs/2210.03629

EXAMPLE FLOW:
-------------
User: "How many Python files are in this project?"

ITERATION 1:
  Think: "I need to count Python files. I should search for *.py files."
  Act: search_files(pattern="**/*.py")
  Observe: "Found 15 files: file1.py, file2.py, ..."

ITERATION 2:
  Think: "I found 15 Python files. I can now answer the user."
  Act: None (just respond)
  Response: "There are 15 Python files in this project."

WHY REACT?
----------
1. TRANSPARENCY: We can see the agent's reasoning
2. GROUNDING: Actions are based on real observations
3. CORRECTION: Agent can adjust based on results
4. DEBUGGING: Easy to see where things go wrong

ALTERNATIVE PATTERNS:
---------------------
- Chain of Thought (CoT): Think step-by-step, no tools
- Plan and Execute: Make full plan first, then execute
- Tree of Thoughts: Explore multiple reasoning paths

ReAct is popular because it's simple and effective.
"""

from dataclasses import dataclass, field
from typing import Callable, Any
import json

from .llm import LLMClient, Message, LLMResponse, ToolCall
from tools.base import BaseTool, ToolResult, ToolResultStatus
from config import settings


@dataclass
class ReActStep:
    """
    One step in the ReAct loop.

    FIELDS:
    - thought: What the agent is thinking (reasoning)
    - tool_name: Which tool to use (or None)
    - tool_input: Parameters for the tool
    - observation: Result from tool execution
    - error: Any error that occurred

    WHY TRACK STEPS?
    ----------------
    1. Debugging: See exactly what happened
    2. Logging: Keep history of agent actions
    3. Learning: Could train on successful patterns
    """
    thought: str | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    observation: str | None = None
    error: str | None = None


@dataclass
class ReActResult:
    """
    Final result of the ReAct loop.

    FIELDS:
    - success: Did we complete the task?
    - response: Final answer to user
    - steps: All reasoning steps taken
    - iterations: How many loops we went through
    """
    success: bool
    response: str
    steps: list[ReActStep] = field(default_factory=list)
    iterations: int = 0


class ReActLoop:
    """
    The ReAct reasoning loop implementation.

    HOW IT WORKS:
    -------------
    1. Initialize with LLM client and tools
    2. Call run() with user message
    3. Loop:
       a. Send conversation + tools to LLM
       b. If LLM wants to use tool → execute it, add result
       c. If LLM responds → return response
       d. If max iterations → stop
    4. Return final result

    CONFIGURATION:
    --------------
    - max_iterations: Prevent infinite loops
    - verbose: Print reasoning steps (helpful for debugging)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tools: list[BaseTool],
        verbose: bool = True
    ):
        """
        Initialize the ReAct loop.

        PARAMETERS:
        -----------
        llm_client: For communicating with the LLM
        tools: Available tools the agent can use
        verbose: Print step-by-step reasoning
        """
        self.llm = llm_client
        self.tools = {tool.name: tool for tool in tools}
        self.tool_schemas = [tool.get_schema() for tool in tools]
        self.verbose = verbose
        self.max_iterations = settings.agent.max_iterations

    async def run(
        self,
        user_message: str,
        system_prompt: str,
        conversation_history: list[Message] | None = None
    ) -> ReActResult:
        """
        Run the ReAct loop for a user request.

        FLOW:
        -----
        1. Build initial messages (system + history + user)
        2. Loop until done or max iterations:
           - Ask LLM for next action
           - Execute tool if requested
           - Check if task complete
        3. Return result

        PARAMETERS:
        -----------
        user_message: What the user wants
        system_prompt: Instructions for the agent
        conversation_history: Previous messages (for context)

        RETURNS:
        --------
        ReActResult with success status, response, and all steps
        """
        # Build message list
        messages = [Message(role="system", content=system_prompt)]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append(Message(role="user", content=user_message))

        steps: list[ReActStep] = []
        iterations = 0

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"USER: {user_message}")
            print(f"{'='*60}\n")

        while iterations < self.max_iterations:
            iterations += 1
            step = ReActStep()

            if self.verbose:
                print(f"\n--- Iteration {iterations} ---")

            try:
                # Ask LLM for next action
                response = await self.llm.chat(
                    messages=messages,
                    tools=self.tool_schemas if self.tools else None
                )

                # Case 1: LLM wants to use a tool
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        step = await self._execute_tool_call(tool_call, step)
                        steps.append(step)

                        # Add tool call to messages
                        messages.append(Message(
                            role="assistant",
                            content=response.content or "",
                            tool_calls=[{
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": json.dumps(tool_call.arguments)
                                }
                            }]
                        ))

                        # Add tool result to messages
                        messages.append(Message(
                            role="tool",
                            content=step.observation or step.error or "",
                            tool_call_id=tool_call.id
                        ))

                # Case 2: LLM gives final response (no tool calls)
                elif response.content:
                    if self.verbose:
                        print(f"\nFINAL RESPONSE:\n{response.content}")

                    return ReActResult(
                        success=True,
                        response=response.content,
                        steps=steps,
                        iterations=iterations
                    )

                # Case 3: Empty response (shouldn't happen)
                else:
                    if self.verbose:
                        print("WARNING: Empty response from LLM")
                    continue

            except Exception as e:
                step.error = str(e)
                steps.append(step)

                if self.verbose:
                    print(f"ERROR: {e}")

                # Add error to messages so LLM can recover
                messages.append(Message(
                    role="assistant",
                    content=f"Error occurred: {e}. Let me try a different approach."
                ))

        # Max iterations reached
        return ReActResult(
            success=False,
            response="I wasn't able to complete the task within the iteration limit. "
                     "Please try breaking it into smaller steps.",
            steps=steps,
            iterations=iterations
        )

    async def _execute_tool_call(
        self,
        tool_call: ToolCall,
        step: ReActStep
    ) -> ReActStep:
        """
        Execute a single tool call.

        FLOW:
        -----
        1. Find the tool by name
        2. Validate parameters
        3. Execute the tool
        4. Record result in step

        ERROR HANDLING:
        ---------------
        - Unknown tool → record error
        - Invalid params → record error
        - Execution fails → record error

        The error is recorded, not raised, so the LLM can see it
        and try a different approach.
        """
        step.tool_name = tool_call.name
        step.tool_input = tool_call.arguments

        if self.verbose:
            print(f"\nTOOL: {tool_call.name}")
            print(f"INPUT: {json.dumps(tool_call.arguments, indent=2)}")

        # Find the tool
        tool = self.tools.get(tool_call.name)
        if not tool:
            step.error = f"Unknown tool: {tool_call.name}. Available: {list(self.tools.keys())}"
            if self.verbose:
                print(f"ERROR: {step.error}")
            return step

        # Validate parameters
        is_valid, error = tool.validate_params(**tool_call.arguments)
        if not is_valid:
            step.error = f"Invalid parameters: {error}"
            if self.verbose:
                print(f"ERROR: {step.error}")
            return step

        # Execute the tool
        try:
            result = await tool.execute(**tool_call.arguments)
            step.observation = result.to_message()

            if self.verbose:
                # Truncate long output for display
                display_output = step.observation
                if len(display_output) > 500:
                    display_output = display_output[:500] + "\n... (truncated)"
                print(f"RESULT:\n{display_output}")

        except Exception as e:
            step.error = f"Tool execution failed: {str(e)}"
            if self.verbose:
                print(f"ERROR: {step.error}")

        return step


class PlanAndExecute:
    """
    Alternative reasoning pattern: Plan first, then execute.

    DIFFERENCE FROM REACT:
    ----------------------
    ReAct: Think → Act → Observe → Think → Act → ...
    PlanAndExecute: Plan all steps → Execute step 1 → Execute step 2 → ...

    WHEN TO USE:
    ------------
    - Complex tasks with many steps
    - Tasks where order matters
    - When you want to review plan before execution

    NOT IMPLEMENTED YET - just showing the concept.
    You could implement this for more complex planning needs.
    """
    pass  # TODO: Implement if needed
