"""
JARVIS Memory System - Learn from past tasks
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, asdict, field
from utils.logger import get_logger

logger = get_logger("memory")


@dataclass
class MemoryEntry:
    """A single memory entry"""
    timestamp: str
    task: str
    module: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    metadata: dict = field(default_factory=dict)


class Memory:
    """
    Simple file-based memory system.
    Stores task history and learnings.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path(__file__).parent.parent / "data" / "memory.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[MemoryEntry] = []
        self._load()

    def _load(self) -> None:
        """Load memory from disk"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.entries = [MemoryEntry(**e) for e in data]
                logger.debug(f"Loaded {len(self.entries)} memory entries")
            except Exception as e:
                logger.warning(f"Failed to load memory: {e}")
                self.entries = []

    def _save(self) -> None:
        """Save memory to disk"""
        try:
            with open(self.storage_path, "w") as f:
                json.dump([asdict(e) for e in self.entries], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def add(
        self,
        task: str,
        module: str,
        success: bool,
        result: Any = None,
        error: Optional[str] = None,
        duration: float = 0.0,
        metadata: Optional[dict] = None
    ) -> None:
        """Add a memory entry"""
        entry = MemoryEntry(
            timestamp=datetime.now().isoformat(),
            task=task,
            module=module,
            success=success,
            result=result,
            error=error,
            duration=duration,
            metadata=metadata or {}
        )
        self.entries.append(entry)
        self._save()
        logger.debug(f"Added memory entry for task: {task[:50]}...")

    def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Search memory for similar tasks"""
        # Simple substring matching for now
        # TODO: Add semantic search with embeddings
        results = []
        query_lower = query.lower()
        for entry in reversed(self.entries):
            if query_lower in entry.task.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_recent(self, limit: int = 10) -> list[MemoryEntry]:
        """Get most recent entries"""
        return list(reversed(self.entries[-limit:]))

    def get_failures(self, limit: int = 10) -> list[MemoryEntry]:
        """Get recent failures for learning"""
        failures = [e for e in self.entries if not e.success]
        return list(reversed(failures[-limit:]))

    def get_stats(self) -> dict:
        """Get memory statistics"""
        total = len(self.entries)
        successes = sum(1 for e in self.entries if e.success)
        return {
            "total_tasks": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": successes / total if total > 0 else 0,
            "modules_used": list(set(e.module for e in self.entries))
        }
