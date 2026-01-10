"""
Code Executor Tool
==================

Lets the agent write and execute Python code.

WHY CODE EXECUTION?
-------------------
This is what makes an agent truly powerful. Instead of having
pre-built tools for everything, the agent can:

1. Write custom code to solve problems
2. Use any Python library
3. Process data in complex ways
4. Create files, make API calls, etc.

SECURITY: SANDBOXING
--------------------
Running arbitrary code is DANGEROUS. Options for sandboxing:

1. SUBPROCESS (what we use):
   - Runs in separate process
   - Can set timeout
   - Limited isolation

2. DOCKER (better):
   - Full container isolation
   - Can limit CPU, memory, network
   - Requires Docker installed

3. FIRECRACKER/GVISOR (best):
   - VM-level isolation
   - Used by AWS Lambda, etc.
   - Complex to set up

For development/trusted environments, subprocess is fine.
For production, use Docker or better.

EXAMPLE USAGE:
--------------
User: "Calculate the first 20 Fibonacci numbers"

Agent decides to use code_executor:
{
    "tool": "python_execute",
    "parameters": {
        "code": "def fib(n):\\n    a, b = 0, 1\\n    result = []\\n    for _ in range(n):\\n        result.append(a)\\n        a, b = b, a + b\\n    return result\\n\\nprint(fib(20))"
    }
}

Result: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181]
"""

import asyncio
import tempfile
import os
from pathlib import Path

from .base import BaseTool, ToolParameter, ToolResult, ToolResultStatus
from config import settings


class PythonExecutorTool(BaseTool):
    """
    Execute Python code and return the output.

    CAPABILITIES:
    - Run any Python code
    - Access installed packages
    - Print output is captured
    - Exceptions are caught and reported

    LIMITATIONS:
    - Timeout enforced
    - No persistent state between calls
    - Running in subprocess (not same process)

    TIPS FOR THE LLM:
    - Use print() to output results
    - Import packages at the top
    - Handle exceptions if needed
    - Keep code focused and simple
    """

    name = "python_execute"
    description = (
        "Execute Python code and return the output. "
        "Use print() to output results. All standard library and installed packages are available."
    )
    parameters = [
        ToolParameter(
            name="code",
            type="string",
            description="Python code to execute",
            required=True
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Max seconds to run (default: from settings)",
            required=False,
            default=None
        )
    ]

    async def execute(self, code: str, timeout: int | None = None) -> ToolResult:
        """
        Execute Python code.

        FLOW:
        1. Check if code execution is enabled
        2. Write code to temporary file
        3. Run with Python subprocess
        4. Capture stdout/stderr
        5. Clean up and return result

        WHY TEMP FILE?
        --------------
        We could use `python -c "code"` but:
        - Escaping is tricky with quotes
        - Multiline code is awkward
        - Error messages show line numbers correctly with file

        The temp file is deleted after execution.
        """
        if not settings.tools.code_execution_enabled:
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error="Code execution is disabled in settings"
            )

        exec_timeout = timeout or settings.tools.max_execution_time

        # Create temporary file for the code
        # We use delete=False so we control when it's deleted
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                encoding="utf-8"
            ) as f:
                f.write(code)
                temp_path = f.name

            try:
                # Run the code
                process = await asyncio.create_subprocess_exec(
                    "python", temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(settings.agent.workspace)
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=exec_timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return ToolResult(
                        status=ToolResultStatus.TIMEOUT,
                        error=f"Code execution timed out after {exec_timeout} seconds"
                    )

                stdout_text = stdout.decode("utf-8", errors="replace")
                stderr_text = stderr.decode("utf-8", errors="replace")

                # Build output
                output_parts = []
                if stdout_text:
                    output_parts.append(stdout_text)
                if stderr_text:
                    output_parts.append(f"[STDERR]\n{stderr_text}")

                output = "\n".join(output_parts) if output_parts else "(no output)"

                if process.returncode != 0:
                    return ToolResult(
                        output=output,
                        status=ToolResultStatus.ERROR,
                        error=f"Code exited with error (return code {process.returncode})",
                        metadata={"return_code": process.returncode}
                    )

                return ToolResult(
                    output=output,
                    metadata={"return_code": 0}
                )

            finally:
                # Always clean up the temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to execute code: {str(e)}"
            )


class JavaScriptExecutorTool(BaseTool):
    """
    Execute JavaScript code using Node.js.

    Similar to PythonExecutorTool but for JavaScript.
    Requires Node.js to be installed.

    WHEN TO USE:
    - Web-related tasks
    - JSON processing (JS native)
    - When user specifically wants JS
    """

    name = "javascript_execute"
    description = (
        "Execute JavaScript code using Node.js. "
        "Use console.log() to output results."
    )
    parameters = [
        ToolParameter(
            name="code",
            type="string",
            description="JavaScript code to execute",
            required=True
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Max seconds to run",
            required=False,
            default=None
        )
    ]

    async def execute(self, code: str, timeout: int | None = None) -> ToolResult:
        """Execute JavaScript code using Node.js."""
        if not settings.tools.code_execution_enabled:
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error="Code execution is disabled in settings"
            )

        exec_timeout = timeout or settings.tools.max_execution_time

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".js",
                delete=False,
                encoding="utf-8"
            ) as f:
                f.write(code)
                temp_path = f.name

            try:
                process = await asyncio.create_subprocess_exec(
                    "node", temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(settings.agent.workspace)
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=exec_timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return ToolResult(
                        status=ToolResultStatus.TIMEOUT,
                        error=f"Execution timed out after {exec_timeout} seconds"
                    )

                stdout_text = stdout.decode("utf-8", errors="replace")
                stderr_text = stderr.decode("utf-8", errors="replace")

                output_parts = []
                if stdout_text:
                    output_parts.append(stdout_text)
                if stderr_text:
                    output_parts.append(f"[STDERR]\n{stderr_text}")

                output = "\n".join(output_parts) if output_parts else "(no output)"

                if process.returncode != 0:
                    return ToolResult(
                        output=output,
                        status=ToolResultStatus.ERROR,
                        error=f"Code exited with error",
                        metadata={"return_code": process.returncode}
                    )

                return ToolResult(output=output, metadata={"return_code": 0})

            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        except FileNotFoundError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="Node.js is not installed. Install with: apt install nodejs"
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to execute code: {str(e)}"
            )
