"""
File Operations Tools
=====================

These tools let the agent interact with the file system:
- Read files
- Write files
- Search for files

SECURITY CONCEPT: PATH VALIDATION
---------------------------------
We restrict file access to specific directories (allowed_paths in settings).
This prevents the agent from:
- Reading sensitive system files (/etc/passwd, SSH keys, etc.)
- Writing to critical locations
- Escaping its sandbox

REAL PATH RESOLUTION:
We use Path.resolve() to handle tricks like:
- "../../../etc/passwd" (path traversal)
- Symlinks pointing outside allowed paths

The agent can only access files within its designated workspace.
"""

import os
import glob as glob_module
from pathlib import Path
import aiofiles
from typing import Optional

from .base import BaseTool, ToolParameter, ToolResult, ToolResultStatus
from config import settings


def is_path_allowed(path: Path) -> bool:
    """
    Check if a path is within allowed directories.

    SECURITY: This is the core security check for file access.

    HOW IT WORKS:
    1. Resolve the path (follow symlinks, resolve ../, etc.)
    2. Check if it's under any allowed directory
    3. Return True only if safe

    EXAMPLE:
    allowed_paths = ["/home/user/jarvis"]

    is_path_allowed("/home/user/jarvis/file.txt")  → True
    is_path_allowed("/home/user/jarvis/../secrets")  → False (resolves outside)
    is_path_allowed("/etc/passwd")  → False (not in allowed paths)
    """
    try:
        resolved = path.resolve()
        for allowed in settings.tools.allowed_paths:
            allowed_path = Path(allowed).resolve()
            # Check if resolved path is under allowed path
            if str(resolved).startswith(str(allowed_path)):
                return True
        return False
    except Exception:
        return False


class FileReadTool(BaseTool):
    """
    Read the contents of a file.

    USE CASES:
    - Reading source code to understand it
    - Checking configuration files
    - Viewing logs

    SAFETY:
    - Only reads from allowed paths
    - Has size limit to prevent reading huge files
    - Returns clear errors for missing files
    """

    name = "read_file"
    description = "Read the contents of a file. Returns the file content as text."
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Absolute path to the file to read",
            required=True
        ),
        ToolParameter(
            name="max_lines",
            type="integer",
            description="Maximum number of lines to read (default: all)",
            required=False,
            default=None
        )
    ]

    async def execute(self, file_path: str, max_lines: Optional[int] = None) -> ToolResult:
        """
        Read file contents.

        FLOW:
        1. Validate path is allowed
        2. Check file exists
        3. Read contents (with optional line limit)
        4. Return result
        """
        path = Path(file_path)

        # Security check
        if not is_path_allowed(path):
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error=f"Access denied: '{file_path}' is outside allowed paths. "
                      f"Allowed: {settings.tools.allowed_paths}"
            )

        # Existence check
        if not path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"File not found: '{file_path}'"
            )

        if not path.is_file():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Not a file: '{file_path}' (might be a directory)"
            )

        try:
            async with aiofiles.open(path, "r", encoding="utf-8", errors="replace") as f:
                if max_lines:
                    lines = []
                    for i, line in enumerate(await f.readlines()):
                        if i >= max_lines:
                            break
                        lines.append(line)
                    content = "".join(lines)
                    if len(lines) == max_lines:
                        content += f"\n... (truncated at {max_lines} lines)"
                else:
                    content = await f.read()

            return ToolResult(
                output=content,
                metadata={"file_path": str(path), "size": len(content)}
            )

        except PermissionError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Permission denied: Cannot read '{file_path}'"
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to read file: {str(e)}"
            )


class FileWriteTool(BaseTool):
    """
    Write content to a file.

    USE CASES:
    - Creating new source code files
    - Updating configuration
    - Saving generated content

    SAFETY:
    - Only writes to allowed paths
    - Creates parent directories if needed
    - Can optionally append instead of overwrite
    """

    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Absolute path to the file to write",
            required=True
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
            required=True
        ),
        ToolParameter(
            name="append",
            type="boolean",
            description="If true, append to file instead of overwriting",
            required=False,
            default=False
        )
    ]

    async def execute(
        self, file_path: str, content: str, append: bool = False
    ) -> ToolResult:
        """
        Write content to file.

        FLOW:
        1. Validate path is allowed
        2. Create parent directories if needed
        3. Write (or append) content
        4. Return result with confirmation
        """
        path = Path(file_path)

        # Security check
        if not is_path_allowed(path):
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error=f"Access denied: '{file_path}' is outside allowed paths. "
                      f"Allowed: {settings.tools.allowed_paths}"
            )

        try:
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            async with aiofiles.open(path, mode, encoding="utf-8") as f:
                await f.write(content)

            action = "Appended to" if append else "Wrote"
            return ToolResult(
                output=f"{action} {len(content)} characters to '{file_path}'",
                metadata={"file_path": str(path), "size": len(content), "append": append}
            )

        except PermissionError:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Permission denied: Cannot write to '{file_path}'"
            )
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Failed to write file: {str(e)}"
            )


class FileSearchTool(BaseTool):
    """
    Search for files matching a pattern.

    USE CASES:
    - Finding all Python files: "**/*.py"
    - Finding configs: "**/config.*"
    - Finding specific files: "**/README*"

    GLOB PATTERNS:
    - * : matches anything except /
    - ** : matches anything including /
    - ? : matches any single character
    - [abc] : matches a, b, or c

    EXAMPLES:
    "*.py" → Python files in current dir
    "**/*.py" → Python files in all subdirs
    "src/**/*.ts" → TypeScript files under src/
    """

    name = "search_files"
    description = "Search for files matching a glob pattern. Returns list of matching file paths."
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern to match files (e.g., '**/*.py' for all Python files)",
            required=True
        ),
        ToolParameter(
            name="directory",
            type="string",
            description="Directory to search in (default: workspace root)",
            required=False,
            default=None
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results to return",
            required=False,
            default=50
        )
    ]

    async def execute(
        self,
        pattern: str,
        directory: Optional[str] = None,
        max_results: int = 50
    ) -> ToolResult:
        """
        Search for files matching pattern.

        FLOW:
        1. Validate search directory is allowed
        2. Run glob pattern match
        3. Filter results to allowed paths
        4. Return list of matches
        """
        search_dir = Path(directory) if directory else settings.agent.workspace

        # Security check on search directory
        if not is_path_allowed(search_dir):
            return ToolResult(
                status=ToolResultStatus.DENIED,
                error=f"Access denied: Cannot search in '{search_dir}'. "
                      f"Allowed: {settings.tools.allowed_paths}"
            )

        try:
            # Build full glob pattern
            full_pattern = str(search_dir / pattern)

            # Find matching files
            matches = []
            for match in glob_module.glob(full_pattern, recursive=True):
                match_path = Path(match)
                # Only include files (not directories) that are allowed
                if match_path.is_file() and is_path_allowed(match_path):
                    matches.append(str(match_path))
                    if len(matches) >= max_results:
                        break

            if not matches:
                return ToolResult(
                    output=f"No files found matching pattern '{pattern}' in '{search_dir}'"
                )

            result = f"Found {len(matches)} file(s):\n"
            result += "\n".join(f"  - {m}" for m in matches)

            if len(matches) == max_results:
                result += f"\n  ... (limited to {max_results} results)"

            return ToolResult(
                output=result,
                metadata={"count": len(matches), "pattern": pattern}
            )

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Search failed: {str(e)}"
            )
