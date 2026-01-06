"""
Base Module - Template for all JARVIS capabilities
Every module inherits from this.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time

from utils.logger import get_logger


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class TaskResult:
    """Result of a module task execution"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    metadata: dict = field(default_factory=dict)


class BaseModule(ABC):
    """
    Base class for all JARVIS modules.

    Every capability (video editing, content creation, code agent, etc.)
    inherits from this and implements the required methods.
    """

    name: str = "base"
    description: str = "Base module template"
    version: str = "0.1.0"

    def __init__(self):
        self.logger = get_logger(f"module.{self.name}")
        self.status = TaskStatus.PENDING
        self._start_time: Optional[float] = None

    @abstractmethod
    def can_handle(self, task: str) -> bool:
        """
        Check if this module can handle the given task.
        Returns True if this module should process the task.
        """
        pass

    @abstractmethod
    def execute(self, task: str, **kwargs) -> TaskResult:
        """
        Execute the task and return result.
        This is the main entry point for task execution.
        """
        pass

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """
        Validate inputs before execution.
        Override in subclass for specific validation.
        Returns (is_valid, error_message)
        """
        return True, None

    def pre_execute(self, task: str, **kwargs) -> None:
        """Hook called before execution"""
        self._start_time = time.time()
        self.status = TaskStatus.RUNNING
        self.logger.info(f"Starting task: {task[:100]}...")

    def post_execute(self, result: TaskResult) -> TaskResult:
        """Hook called after execution"""
        if self._start_time:
            result.duration = time.time() - self._start_time
        self.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        self.logger.info(f"Task completed in {result.duration:.2f}s - Success: {result.success}")
        return result

    def run(self, task: str, **kwargs) -> TaskResult:
        """
        Full execution pipeline with hooks and error handling.
        Don't override this - override execute() instead.
        """
        try:
            # Validate
            is_valid, error = self.validate_inputs(**kwargs)
            if not is_valid:
                return TaskResult(success=False, error=error)

            # Pre-execution hook
            self.pre_execute(task, **kwargs)

            # Execute
            result = self.execute(task, **kwargs)

            # Post-execution hook
            return self.post_execute(result)

        except Exception as e:
            self.logger.error(f"Task failed with error: {e}")
            self.status = TaskStatus.FAILED
            return TaskResult(
                success=False,
                error=str(e),
                duration=time.time() - (self._start_time or time.time())
            )

    def get_status(self) -> dict:
        """Get current module status"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "status": self.status.value,
        }
