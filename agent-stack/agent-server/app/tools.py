import json
import os
import re
from pathlib import Path
from typing import Any

TOOL_JSON_RE = re.compile(r"\{[\s\S]*\}")


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
