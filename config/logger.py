"""
Centralized logging configuration for the YouTube to Google Drive project.
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logger(name, log_level=logging.INFO):
    """
    Set up and return a logger with handlers for file and console.

    Args:
        name (str): Logger name (usually __name__)
        log_level (int): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        logging.Logger: Configured logger
    """
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid duplicating handlers if they already exist
    if logger.handlers:
        return logger

    # Detailed format for file
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Simple format for console (maintains current UX)
    console_formatter = logging.Formatter('%(message)s')

    # File handler with rotation (max 10MB, 5 backups)
    log_file = os.path.join(log_dir, f"{name.replace('.', '_')}_{datetime.now():%Y%m%d}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name):
    """
    Get an already configured logger or create a new one.

    Args:
        name (str): Logger name

    Returns:
        logging.Logger: Configured logger
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
