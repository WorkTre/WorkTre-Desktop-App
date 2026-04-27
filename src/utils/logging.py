"""
src/utils/logging.py
Logging utilities.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from ..config import settings
from ..platform.utils import get_log_file_path


def setup_logging(app_name: str = "WorkTre", level: str = "INFO",
                 log_to_file: bool = True, log_to_console: bool = True) -> logging.Logger:
    """
    Setup application logging.

    Args:
        app_name: Application name
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file
        log_to_console: Whether to log to console

    Returns:
        Configured logger
    """
    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger(app_name)
    logger.setLevel(log_level)

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    )
    colored_formatter = _create_colored_formatter()

    # File handler (detailed)
    if log_to_file:
        try:
            log_file = get_log_file_path(app_name)
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(detailed_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file logging: {e}")

    # Console handler (colored if supported)
    if log_to_console and sys.stdout:
        if hasattr(sys.stdout, 'reconfigure') and sys.platform == 'win32':
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        # Try to use colored formatter if colorama is available
        try:
            import colorama
            colorama.init()
            console_handler.setFormatter(colored_formatter)
        except ImportError:
            console_handler.setFormatter(simple_formatter)

        logger.addHandler(console_handler)

    # Log startup message
    logger.info(f"Logging initialized for {app_name} (level: {level})")

    return logger


def _create_colored_formatter() -> logging.Formatter:
    """Create colored log formatter."""
    try:
        import colorama
        from colorama import Fore, Style

        class ColoredFormatter(logging.Formatter):
            """Custom formatter with colors."""

            COLORS = {
                'DEBUG': Fore.CYAN,
                'INFO': Fore.GREEN,
                'WARNING': Fore.YELLOW,
                'ERROR': Fore.RED,
                'CRITICAL': Fore.RED + Style.BRIGHT,
            }

            def format(self, record):
                # Add color to levelname
                levelname = record.levelname
                if levelname in self.COLORS:
                    record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"

                # Format the message
                message = super().format(record)

                # Reset color at the end
                return f"{message}{Style.RESET_ALL}"

        return ColoredFormatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

    except ImportError:
        # Fallback to simple formatter
        return logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (uses root logger if None)

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(name)
    return logging.getLogger()

__all__ = ['setup_logging', 'get_logger']

class LogContext:
    """Context manager for logging operations."""

    def __init__(self, logger: logging.Logger, operation: str, level: str = "INFO"):
        self.logger = logger
        self.operation = operation
        self.level = level
        self.start_time = None

    def __enter__(self):
        self.start_time = logging.time.time()
        log_func = getattr(self.logger, self.level.lower(), self.logger.info)
        log_func(f"Starting: {self.operation}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = logging.time.time() - self.start_time
        if exc_type is None:
            log_func = getattr(self.logger, self.level.lower(), self.logger.info)
            log_func(f"Completed: {self.operation} (took {elapsed:.2f}s)")
        else:
            self.logger.error(f"Failed: {self.operation} (took {elapsed:.2f}s) - {exc_val}")
        return False  # Don't suppress exceptions


def log_operation(operation: str, level: str = "INFO"):
    """
    Decorator to log function execution.

    Args:
        operation: Description of the operation
        level: Logging level

    Returns:
        Decorator function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            with LogContext(logger, operation, level):
                return func(*args, **kwargs)
        return wrapper
    return decorator