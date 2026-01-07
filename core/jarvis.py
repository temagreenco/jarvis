"""
JARVIS Core - The Brain
Central orchestrator for all capabilities.
"""
from typing import Optional
from pathlib import Path

from core.task_router import TaskRouter
from core.memory import Memory
from modules.base_module import TaskResult
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("jarvis")


class Jarvis:
    """
    JARVIS - The autonomous AI system.

    Principles:
    1. If asked to do something → DO IT
    2. If can't do it → LEARN HOW or BUILD THE CAPABILITY
    3. If blocked → ASK ONE clear question, then continue
    4. Never say "I can't" → Say "Here's how I'll solve it"
    5. Work autonomously → Report results, not problems
    """

    def __init__(self):
        self.router = TaskRouter()
        self.memory = Memory()
        self._initialized = False
        logger.info("JARVIS initializing...")

    def initialize(self) -> None:
        """Initialize JARVIS with all modules"""
        if self._initialized:
            return

        # Import and register modules here
        # This is done lazily to avoid circular imports
        try:
            from modules.video_editor import VideoEditorModule
            self.router.register(VideoEditorModule())
            logger.info("Video Editor module loaded")
        except ImportError as e:
            logger.warning(f"Could not load Video Editor: {e}")

        try:
            from modules.chat_module import ChatModule
            self.router.register(ChatModule(), default=True)
            logger.info("Chat module loaded")
        except ImportError as e:
            logger.warning(f"Could not load Chat module: {e}")

        self._initialized = True
        logger.info("JARVIS initialization complete")

    def process(self, task: str, **kwargs) -> TaskResult:
        """
        Process a task through JARVIS.
        Routes to appropriate module and executes.
        """
        if not self._initialized:
            self.initialize()

        logger.info(f"Processing task: {task[:100]}...")

        # Route and execute
        result = self.router.route(task, **kwargs)

        # Store in memory
        handler = self.router.find_handler(task)
        self.memory.add(
            task=task,
            module=handler.name if handler else "unknown",
            success=result.success,
            result=str(result.data)[:500] if result.data else None,
            error=result.error,
            duration=result.duration,
            metadata=kwargs
        )

        return result

    def get_status(self) -> dict:
        """Get JARVIS system status"""
        return {
            "initialized": self._initialized,
            "modules": self.router.list_modules(),
            "memory_stats": self.memory.get_stats()
        }


# Global JARVIS instance
_jarvis: Optional[Jarvis] = None


def get_jarvis() -> Jarvis:
    """Get or create JARVIS instance"""
    global _jarvis
    if _jarvis is None:
        _jarvis = Jarvis()
    return _jarvis
