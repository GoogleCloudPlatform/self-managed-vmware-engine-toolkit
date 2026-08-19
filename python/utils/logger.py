"""Logging configuration helper module.

Establishes uniform console stream and file-backed error diagnostic logging
formatter rules across all CLI and operational components.
"""

import logging
import sys

import constants


def setup_logger(
    logger_name: str = constants.DeployerDefaults.LOGGER_NAME,
    level: int = logging.INFO,
) -> logging.Logger:
  """Configures uniform root logger for deployment orchestration and jumpboxes.

  Args:
      logger_name: Name of target logger namespace.
      level: Threshold logging severity level.

  Returns:
      Configured logging.Logger instance with attached console stream handler.
  """
  logger = logging.getLogger(logger_name)
  logger.setLevel(level)

  if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        constants.DeployerDefaults.LOG_FORMAT,
        datefmt=constants.DeployerDefaults.LOG_DATE_FORMAT,
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

  return logger
