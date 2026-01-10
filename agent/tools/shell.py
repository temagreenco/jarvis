"""
Shell Command Tool
==================

Lets the agent run bash commands. This is POWERFUL but requires CAUTION.

SECURITY CONSIDERATIONS:
------------------------
1. DANGEROUS COMMANDS: Some commands can destroy the system
   - rm -rf /  (delete everything)
   - mkfs      (format drives)
   - Fork bombs: :(){:|:&};:

2. COMMAND INJECTION: If we're not careful, malicious input could
   run unintended commands. We use subprocess with shell=True carefully.

3. TIMEOUTS: Commands that hang forever (e.g., `cat /dev/urandom`)
   must be killed after a timeout.

4. WORKING DIRECTORY: Commands run in a specific directory,
   not wherever the system happens to be.

WHY ALLOW SHELL ACCESS?
-----------------------
Many tasks REQUIRE shell commands:
- Git operations (git status, commit, push)
- Package management (pip install, npm install)
- Build tools (make, cargo build)
- System info (df, free, nvidia-smi)

The key is CONTROLLED access with safety limits.
"""

import asyncio
import shlex
from pathlib import Path

from .base import BaseTool, ToolParameter, ToolResult, ToolResultStatus
from config import settings


class ShellTool(BaseTool):
    """
    Execute shell commands.

    SAFETY FEATURES:
    - Blocks known dangerous commands
    - Enforces timeout limits
    - Runs in specific working directory
    - Captures both stdout and stderr

    EXAMPLES:
    - "ls -la" → List files
    - "git status" → Check git status
    - "python --version" → Check Python version
    - "nvidia-smi" → Check GPU status (useful on RunPod!)
    """

    name = "shell"
    description = (
        "Execute a shell command and return its output. "
        "Use for git operations, system commands, package management, etc."
    )
    parameters = [
        ToolParameter(
            name="command",
            type="string",
            description="The shell command to execute",
            required=True
        ),
        ToolParameter(
            name="working_dir",
            type="string",
            description="Directory to run command in (default: workspace)",
            required=False,
            default=None
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Max seconds to wait (default: from settings)",
            required=False,
            default=None
        )
    ]

    def is_command_blocked(self, command: str) -> tuple[bool, str]:
        """
        Check if a command is in the blocklist.

        WHY BLOCKLIST?
        --------------
        Some commands are NEVER safe:
        - "rm -rf /" could delete everything
        - Fork bombs crash the system
        - "mkfs" formats drives

        We check if the command CONTAINS these patterns.
        This isn't perfect (clever attackers can obfuscate),
        but it catches common accidents.

        DEFENSE IN DEPTH:
        On production systems, also use:
        - Container isolation (Docker)
        - Limited user permissions
        - Resource limits (cgroups)
        """
        command_lower = command.lower()

        for blocked in settings.tools.dangerous_commands_blocked:
            if blocked.lower() in command_lower:
                return True, f"Blocked dangerous command pattern: '{blocked}'"

        # Additional safety checks
        dangerous_patterns = [
            ("rm -rf /", "Recursive delete of root"),
            ("rm -rf /*", "Recursive delete of root contents"),
            ("> /dev/sd", "Writing to disk device"),
            ("chmod -R 777 /", "Dangerous permission change"),
            ("curl | sh", "Piping remote script to shell"),
            ("wget | sh", "Piping remote script to shell"),
        ]

        for pattern, reason in dangerous_patterns:
            if pattern in command_lower:
                return True, f"Blocked: {reason}"

        return False, ""

    async def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int | None = None
    ) -> ToolResult:
        """
        Execute a shell command.

        FLOW:
        1. Check command isn't blocked
        2. Validate working directory
        3. Run command with timeout
        4. Capture and return output

        WHY ASYNCIO.CREATE_SUBPROCESS_SHELL?
        ------------------------------------
        - Async: Doesn't block while waiting for command
        - Subprocess: Runs in separate process (isolation)
        - Shell: Allows pipes, redirects, etc. (|, >, &&)

        Note: shell=True has security implications but is needed
        for commands with pipes, redirects, etc.
        """
        # Check if shell commands are enabled
        if not settings.tools.shell_enabled:
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error="Shell commands are disabled in settings"
            )

        # Check against blocklist
        is_blocked, reason = self.is_command_blocked(command)
        if is_blocked:
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error=reason
            )

        # Determine working directory
        cwd = Path(working_dir) if working_dir else settings.agent.workspace

        if not cwd.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Working directory does not exist: '{cwd}'"
            )

        # Determine timeout
        cmd_timeout = timeout or settings.tools.max_execution_time

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd)
            )

            try:
                # Wait for completion with timeout
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=cmd_timeout
                )
            except asyncio.TimeoutError:
                # Kill the process if it times out
                process.kill()
                await process.wait()
                return ToolResult(
                    status=ToolResultStatus.TIMEOUT,
                    output=f"Command timed out after {cmd_timeout} seconds",
                    error="Execution exceeded time limit"
                )

            # Decode output
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Build result
            output_parts = []
            if stdout_text:
                output_parts.append(stdout_text)
            if stderr_text:
                output_parts.append(f"[STDERR]\n{stderr_text}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            # Check return code
            if process.returncode != 0:
                return ToolResult(
                    output=output,
                    status=ToolResultStatus.ERROR,
                    error=f"Command exited with code {process.returncode}",
                    metadata={
                        "return_code": process.returncode,
                        "command": command
                    }
                )

            return ToolResult(
                output=output,
                metadata={
                    "return_code": 0,
                    "command": command,
                    "working_dir": str(cwd)
                }
            )

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to execute command: {str(e)}"
            )
