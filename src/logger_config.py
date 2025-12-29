"""
Centralized logging configuration for the entire project.

This module provides a single point of configuration for all logging
in the application. It ensures consistent log formatting and output
across all modules.

Usage:
    In your main application file (e.g., main.py or app.py):

        from src.logger_config import setup_logging
        setup_logging(log_file="logs/log.log", log_level=logging.DEBUG, console_output=True))

    In any module where you need logging:

        import logging
        logger = logging.getLogger(__name__)
        logger.info("Message")
        logger.debug("Debug message")
        logger.error("Error message")
"""

import logging
import sys
from pathlib import Path


def setup_logging(
    log_level: int = logging.INFO,
    component: str = "default",
    console_output: bool = True
) -> logging.Logger:
    """
    Sets up logging for the application.

    Args:
        log_level (int): Logging level (e.g., logging.INFO, logging.DEBUG).
        component (str): Name of the component (e.g., 'streamlit', 'data_collector').
                         This will create a folder structure: logs/{component}/{date}/
        console_output (bool): Whether to output logs to console.

    Returns:
        logging.Logger: The root logger.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Log format
    log_format = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(log_format)
        root_logger.addHandler(console_handler)

    # File handler
    if component:
        from datetime import datetime
        # Base logs directory
        base_logs_dir = Path(__file__).resolve().parent.parent / "logs"

        # Logs directory structure: logs/{component}/{YYYY-MM-DD}/
        today_str = datetime.now().strftime("%Y-%m-%d")
        log_dir = base_logs_dir / component / today_str
        log_dir.mkdir(parents=True, exist_ok=True)

        # Log filename: {YYYYMMDD_HHMMSS}_{component}.log
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{timestamp_str}_{component}.log"
        log_file_path = log_dir / log_filename

        file_handler = logging.FileHandler(str(log_file_path))
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_format)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

if __name__ == "__main__":
    # Example usage
    setup_logging(log_level=logging.DEBUG, component="test")

    logger = get_logger(__name__)

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")