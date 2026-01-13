import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOL_JSON_RE = re.compile(r"\{[\s\S]*\}")

# Safety: blocked commands
BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){", "fork bomb",
    "chmod -R 777 /", "wget", "curl", "> /dev/sd", "shutdown", "reboot",
]


def ensure_workspace(base: str, run_id: str) -> str:
    ws = Path(base) / "workspaces" / run_id
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


def read_file_safe(workspace: str, rel_path: str) -> str:
    p = (Path(workspace) / rel_path).resolve()
    if not str(p).startswith(str(Path(workspace).resolve())):
        raise ValueError("Path escape blocked")
    if not p.exists() or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def write_file_safe(workspace: str, rel_path: str, content: str) -> None:
    p = (Path(workspace) / rel_path).resolve()
    if not str(p).startswith(str(Path(workspace).resolve())):
        raise ValueError("Path escape blocked")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def list_files(workspace: str) -> list[str]:
    root = Path(workspace)
    out = []
    for p in root.rglob("*"):
        if p.is_file():
            out.append(str(p.relative_to(root)))
    return sorted(out)


def extract_tool_call(text: str) -> dict[str, Any] | None:
    m = TOOL_JSON_RE.search(text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict) and "tool" in obj:
            return obj
    except Exception:
        return None
    return None


def run_command_safe(workspace: str, command: str, timeout: int = 30) -> dict[str, Any]:
    """
    Run a shell command safely within the workspace.
    Returns: {"exit_code": int, "stdout": str, "stderr": str}
    """
    # Safety checks
    for blocked in BLOCKED_COMMANDS:
        if blocked in command.lower():
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"BLOCKED: Command contains forbidden pattern: {blocked}"
            }

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],  # Limit output size
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"TIMEOUT: Command exceeded {timeout}s limit"
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"ERROR: {str(e)}"
        }


def install_package(package: str) -> dict[str, Any]:
    """
    Install a Python package using pip.
    Returns: {"success": bool, "message": str}
    """
    # Safety: only allow alphanumeric package names
    if not re.match(r'^[a-zA-Z0-9_\-\[\]<>=,.]+$', package):
        return {"success": False, "message": f"Invalid package name: {package}"}

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return {"success": True, "message": f"Installed {package}"}
        else:
            return {"success": False, "message": result.stderr[:1000]}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Installation timed out"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def run_python_file(workspace: str, filename: str, args: list[str] = None) -> dict[str, Any]:
    """
    Run a Python file in the workspace.
    Returns: {"exit_code": int, "stdout": str, "stderr": str}
    """
    filepath = (Path(workspace) / filename).resolve()
    if not str(filepath).startswith(str(Path(workspace).resolve())):
        return {"exit_code": -1, "stdout": "", "stderr": "Path escape blocked"}

    if not filepath.exists():
        return {"exit_code": -1, "stdout": "", "stderr": f"File not found: {filename}"}

    cmd = [sys.executable, str(filepath)]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "Execution timed out (60s)"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def run_pytest(workspace: str, test_path: str = "") -> dict[str, Any]:
    """
    Run pytest in the workspace.
    Returns: {"exit_code": int, "stdout": str, "stderr": str, "passed": bool}
    """
    cmd = [sys.executable, "-m", "pytest", "-v"]
    if test_path:
        cmd.append(test_path)

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "passed": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "Tests timed out", "passed": False}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e), "passed": False}
