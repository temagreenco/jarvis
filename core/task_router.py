"""
Task Router - Routes tasks to appropriate modules
"""
from typing import Optional
from modules.base_module import BaseModule, TaskResult
from utils.logger import get_logger

logger = get_logger("task_router")


class TaskRouter:
    """
    Routes incoming tasks to the appropriate module.
    Uses module's can_handle() to determine routing.
    """

    def __init__(self):
        self.modules: dict[str, BaseModule] = {}
        self.default_module: Optional[str] = None

    def register(self, module: BaseModule, default: bool = False) -> None:
        """Register a module with the router"""
        self.modules[module.name] = module
        if default:
            self.default_module = module.name
        logger.info(f"Registered module: {module.name}")

    def unregister(self, name: str) -> None:
        """Unregister a module"""
        if name in self.modules:
            del self.modules[name]
            if self.default_module == name:
                self.default_module = None
            logger.info(f"Unregistered module: {name}")

    def find_handler(self, task: str) -> Optional[BaseModule]:
        """Find the module that can handle this task"""
        for module in self.modules.values():
            if module.can_handle(task):
                logger.debug(f"Task matched to module: {module.name}")
                return module

        # Fall back to default if no match
        if self.default_module:
            logger.debug(f"Using default module: {self.default_module}")
            return self.modules[self.default_module]

        return None

    def route(self, task: str, **kwargs) -> TaskResult:
        """Route a task to appropriate module and execute"""
        handler = self.find_handler(task)

        if not handler:
            logger.warning(f"No handler found for task: {task[:100]}")
            return TaskResult(
                success=False,
                error="No module found to handle this task"
            )

        logger.info(f"Routing task to: {handler.name}")
        return handler.run(task, **kwargs)

    def list_modules(self) -> list[dict]:
        """List all registered modules"""
        return [module.get_status() for module in self.modules.values()]
