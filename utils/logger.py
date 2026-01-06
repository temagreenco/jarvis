"""
JARVIS Logging - Clean, informative logs
"""
import sys
from loguru import logger
from pathlib import Path

# Remove default handler
logger.remove()

# Console handler with colors
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# File handler for debugging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logger.add(
    log_dir / "jarvis_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="1 day",
    retention="7 days",
    compression="zip",
)


def get_logger(name: str):
    """Get a logger with module name"""
    return logger.bind(name=name)
