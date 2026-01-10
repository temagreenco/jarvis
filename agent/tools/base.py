"""
Base Tool Class
===============

WHAT IS A TOOL?
---------------
A "tool" is a capability that the agent can use. Think of it like giving
the AI hands to interact with the world:

- FileReadTool: Lets the agent READ files
- ShellTool: Lets the agent RUN commands
- CodeExecutorTool: Lets the agent WRITE and RUN code

HOW THE LLM USES TOOLS:
-----------------------
1. The LLM sees a list of available tools (name + description + parameters)
2. Based on the task, it DECIDES which tool to use
3. It generates the parameters for that tool
4. We EXECUTE the tool and return the result
5. The LLM sees the result and continues reasoning

EXAMPLE FLOW:
-------------
User: "What files are in the current directory?"

LLM thinks: "I need to see files. I should use the shell tool with 'ls -la'"

LLM outputs:
{
    "tool": "shell",
    "parameters": {"command": "ls -la"}
}

We execute: subprocess.run(["ls", "-la"])

Result: "total 32\ndrwxr-xr-x 7 user..."

LLM sees result and responds: "The directory contains 7 items..."


WHY THIS PATTERN?
-----------------
This is called "function calling" or "tool use" - it's how modern AI agents
work. The LLM's job is to REASON and DECIDE. Our code's job is to EXECUTE.

The LLM never directly runs code - it just tells us what to run, and we
handle it safely (with sandboxing, validation, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ToolResultStatus(Enum):
    """
    Possible outcomes when a tool runs.

    SUCCESS: Tool worked, result is valid
    ERROR: Tool failed (bad input, exception, etc.)
    DENIED: Tool blocked for security reasons
    TIMEOUT: Tool took too long
    """
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    """
    What a tool returns after execution.

    IMPORTANT FIELDS:

    - output: The actual result (file contents, command output, etc.)
    - status: Did it work? (success/error/denied/timeout)
    - error: If failed, what went wrong?

    WHY A DATACLASS?
    ----------------
    Dataclasses give us:
    1. Clear structure (we know exactly what a result contains)
    2. Type hints (IDE autocomplete, error catching)
    3. Easy serialization (can convert to dict/JSON)
    """

    output: str = ""
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> str:
        """
        Format result for the LLM to read.

        The LLM needs to understand what happened. We format results
        clearly so it can decide what to do next.
        """
        if self.status == ToolResultStatus.SUCCESS:
            return f"[SUCCESS]\n{self.output}"
        elif self.status == ToolResultStatus.ERROR:
            return f"[ERROR] {self.error}\n{self.output}"
        elif self.status == ToolResultStatus.DENIED:
            return f"[DENIED] {self.error}"
        elif self.status == ToolResultStatus.TIMEOUT:
            return f"[TIMEOUT] Execution exceeded time limit.\n{self.output}"
        return self.output


@dataclass
class ToolParameter:
    """
    Describes ONE parameter a tool accepts.

    EXAMPLE:
    For a file read tool, you might have:
    - name: "file_path"
    - type: "string"
    - description: "Absolute path to the file to read"
    - required: True

    WHY DESCRIBE PARAMETERS?
    ------------------------
    The LLM needs to know:
    1. What inputs the tool needs
    2. What TYPE each input should be
    3. Which inputs are required vs optional

    This is like a function signature, but described in a way
    the LLM can understand.
    """

    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None  # If only certain values are allowed


class BaseTool(ABC):
    """
    Abstract Base Class for all tools.

    TO CREATE A NEW TOOL:
    ---------------------
    1. Inherit from BaseTool
    2. Set `name` and `description` (class attributes)
    3. Define `parameters` (what inputs it needs)
    4. Implement `execute()` (what it actually does)

    EXAMPLE:
    --------
    class MyTool(BaseTool):
        name = "my_tool"
        description = "Does something cool"
        parameters = [
            ToolParameter(
                name="input",
                type="string",
                description="The input to process"
            )
        ]

        async def execute(self, input: str) -> ToolResult:
            # Do the thing
            result = process(input)
            return ToolResult(output=result)
    """

    # Subclasses MUST override these
    name: str = "base_tool"
    description: str = "Base tool - do not use directly"
    parameters: list[ToolParameter] = []

    def __init__(self):
        """
        Initialize the tool.

        Override this in subclasses if you need setup
        (e.g., loading config, creating connections).
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Run the tool with given parameters.

        MUST BE IMPLEMENTED by subclasses.

        WHY ASYNC?
        ----------
        Many tools do I/O (file reads, network calls, subprocess).
        Async allows us to:
        1. Run multiple tools concurrently
        2. Not block while waiting for I/O
        3. Handle timeouts gracefully

        PARAMETERS:
        -----------
        **kwargs: The parameters defined in self.parameters

        RETURNS:
        --------
        ToolResult: The outcome (success/error + output)
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def get_schema(self) -> dict:
        """
        Generate JSON schema for this tool.

        WHY JSON SCHEMA?
        ----------------
        LLMs (especially via OpenAI-compatible APIs) expect tools
        described in JSON Schema format. This is a standard way to
        describe the "shape" of data.

        WHAT THE LLM SEES:
        ------------------
        {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file"
                    }
                },
                "required": ["file_path"]
            }
        }

        The LLM reads this and knows:
        - There's a tool called "read_file"
        - It takes a "file_path" string
        - That parameter is required
        """
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def validate_params(self, **kwargs) -> tuple[bool, str]:
        """
        Check if provided parameters are valid.

        VALIDATION CHECKS:
        ------------------
        1. All required parameters are present
        2. No unknown parameters were passed
        3. (Could add type checking here too)

        WHY VALIDATE?
        -------------
        LLMs sometimes make mistakes:
        - Forget required parameters
        - Use wrong parameter names
        - Pass wrong types

        We catch these early with clear error messages,
        so the LLM can correct itself.
        """
        param_names = {p.name for p in self.parameters}
        required_names = {p.name for p in self.parameters if p.required}

        # Check for unknown parameters
        for key in kwargs:
            if key not in param_names:
                return False, f"Unknown parameter: '{key}'. Valid parameters: {param_names}"

        # Check for missing required parameters
        missing = required_names - set(kwargs.keys())
        if missing:
            return False, f"Missing required parameters: {missing}"

        return True, ""

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
