#!/usr/bin/env python
import argparse
import ast
import os
from pathlib import Path
import re
from typing import Iterable, Set, Dict, List, Tuple

ENTRYPOINTS = [
    "api/server.py",
    "workers/worker.py",
]
PS_ENTRYPOINTS = [
    "scripts/submit_auto_clips_job.ps1",
]

FILE_REF_EXTS = (".json", ".yml", ".yaml", ".ps1", ".sh", ".py", ".md", ".txt")


def repo_path_to_module(repo: Path, file_path: Path) -> str:
    rel = file_path.relative_to(repo).as_posix()
    if rel.endswith("/__init__.py"):
        rel = rel[: -len("/__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def module_to_path(repo: Path, module: str) -> Path | None:
    if not module:
        return None
    parts = module.split(".")
    py_path = repo.joinpath(*parts).with_suffix(".py")
    if py_path.exists():
        return py_path
    pkg_init = repo.joinpath(*parts, "__init__.py")
    if pkg_init.exists():
        return pkg_init
    return None


def resolve_relative_module(current_module: str, module: str | None, level: int) -> str | None:
    if level <= 0:
        return module
    base_parts = current_module.split(".")
    if len(base_parts) < level:
        return None
    prefix = base_parts[: -level]
    if module:
        return ".".join(prefix + module.split("."))
    return ".".join(prefix)


def iter_string_literals(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def find_file_refs(repo: Path, text: str) -> Set[Path]:
    found: Set[Path] = set()
    for match in re.findall(r"['\"]([^'\"]+)['\"]", text):
        if any(ext in match for ext in FILE_REF_EXTS):
            candidate = (repo / match).resolve()
            if candidate.exists():
                found.add(candidate)
    return found


def parse_python_file(path: Path) -> Tuple[Set[str], Set[Path]]:
    src = path.read_text(encoding="utf-8-sig", errors="ignore")
    tree = ast.parse(src)
    imports: Set[str] = set()
    file_refs: Set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "", node.level))
    for text in iter_string_literals(tree):
        file_refs.update(find_file_refs(path.parent, text))
    return imports, file_refs


def collect_used_files(repo: Path) -> Tuple[Set[Path], Set[Path]]:
    used_py: Set[Path] = set()
    file_refs: Set[Path] = set()

    entry_files = [repo / p for p in ENTRYPOINTS]
    queue: List[Path] = [p for p in entry_files if p.exists()]
    module_map: Dict[Path, str] = {}

    while queue:
        path = queue.pop()
        if path in used_py:
            continue
        used_py.add(path)
        current_module = module_map.get(path)
        if not current_module:
            try:
                current_module = repo_path_to_module(repo, path)
            except Exception:
                current_module = ""
        imports, refs = parse_python_file(path)
        file_refs.update(refs)
        for imp in imports:
            if isinstance(imp, tuple):
                module, level = imp
                resolved = resolve_relative_module(current_module, module, level)
                target_module = resolved
            else:
                target_module = imp
            if not target_module:
                continue
            target_path = module_to_path(repo, target_module)
            if target_path and target_path.exists():
                if target_path not in used_py:
                    module_map[target_path] = target_module
                    queue.append(target_path)
    return used_py, file_refs


def collect_ps_file_refs(repo: Path) -> Set[Path]:
    refs: Set[Path] = set()
    for rel in PS_ENTRYPOINTS:
        path = repo / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        refs.update(find_file_refs(repo, text))
    return refs


def categorize_paths(repo: Path, used_py: Set[Path], file_refs: Set[Path]) -> Dict[str, List[str]]:
    all_refs = set(used_py) | set(file_refs)

    core_runtime = set()
    pipeline = set()
    optional = set()
    debug_output = set()

    for path in all_refs:
        rel = path.relative_to(repo).as_posix()
        if rel.startswith("_debug/") or rel.startswith("_backup/") or rel.endswith(".log"):
            debug_output.add(rel)
            continue
        if rel.startswith("modules/") or rel.startswith("workers/") or rel.startswith("api/"):
            core_runtime.add(rel)
            continue
        if rel in ("docker-compose.yml", "docker-compose.cpu.yml", "Dockerfile", "Dockerfile.cpu", "requirements.txt", ".env.example", "jarvis_presets.json"):
            core_runtime.add(rel)
            continue
        if rel.startswith("config/") or rel.startswith("utils/"):
            core_runtime.add(rel)
            continue
        if rel.startswith("prompts/") or rel.startswith("examples/") or rel.startswith("core/"):
            optional.add(rel)
            continue
        if rel.startswith("scripts/"):
            if rel in ("scripts/submit_auto_clips_job.ps1", "scripts/submit_cut_job.ps1", "scripts/create_minio_buckets.ps1"):
                core_runtime.add(rel)
            else:
                optional.add(rel)
            continue
        if any(rel.endswith(ext) for ext in FILE_REF_EXTS):
            optional.add(rel)
            continue

    # Pipeline-specific files
    for rel in [
        "modules/clip_candidates.py",
        "modules/sentence_splitter.py",
        "modules/segment_selector.py",
        "modules/transcribe.py",
        "modules/reels_renderer.py",
        "modules/face_tracker.py",
        "modules/video_cutter.py",
        "modules/silence_detect.py",
        "modules/minio_client.py",
        "modules/job_queue.py",
        "modules/db_models.py",
    ]:
        if (repo / rel).exists():
            pipeline.add(rel)

    return {
        "Core runtime files (must keep)": sorted(core_runtime),
        "Pipeline auto-clips (must keep)": sorted(pipeline),
        "Optional (remove if not needed)": sorted(optional),
        "Debug/output (safe to delete)": sorted(debug_output),
    }


def write_report(repo: Path, output: Path, used_py: Set[Path], file_refs: Set[Path]) -> None:
    categories = categorize_paths(repo, used_py, file_refs)
    lines: List[str] = []
    lines.append("# Files Used Report")
    lines.append("")
    lines.append("Entry points:")
    for entry in ENTRYPOINTS + PS_ENTRYPOINTS:
        lines.append(f"- {entry}")
    lines.append("")
    lines.append(f"Python files analyzed: {len(used_py)}")
    lines.append(f"File references found: {len(file_refs)}")
    lines.append("")
    for section, items in categories.items():
        lines.append(f"## {section}")
        if not items:
            lines.append("(none)")
        else:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.getcwd())
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    used_py, file_refs = collect_used_files(repo)
    file_refs |= collect_ps_file_refs(repo)

    output = args.output
    if output is None:
        output_path = repo / "FILES_USED_REPORT.md"
    else:
        output_path = Path(output)
    write_report(repo, output_path, used_py, file_refs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
