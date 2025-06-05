# multi_agent_system/utils/logger.py

from loguru import logger
import sys

def setup_logging():
    logger.remove() # Remove default handler
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO", # Default level
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    logger.add(
        "logs/multi_agent_system.log",
        rotation="10 MB", # Rotate file every 10 MB
        retention="7 days", # Keep logs for 7 days
        level="DEBUG", # Log all debug messages to file
        compression="zip" # Compress old logs
    )
    logger.info("Logging configured.")