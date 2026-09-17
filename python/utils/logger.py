"""Logging configuration helper module.

Establishes uniform console stream and file-backed error diagnostic logging
formatter rules across all CLI and operational components.
"""

import datetime
import logging
import os
import sys
from typing import Optional, Union

import constants


def _parse_log_level(
    level_val: Union[int, str], default: int = logging.INFO
) -> int:
  """Resolves string or integer log level to a standard logging integer."""
  if isinstance(level_val, int):
    return level_val
  if isinstance(level_val, str):
    resolved = getattr(logging, level_val.strip().upper(), None)
    if isinstance(resolved, int):
      return resolved
  return default


def setup_logger(
    logger_name: str = constants.DeployerDefaults.LOGGER_NAME,
    level: Union[int, str] = logging.INFO,
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    file_level: Union[int, str] = logging.DEBUG,
    enable_file_logging: bool = True,
) -> logging.Logger:
  """Configures uniform root logger for deployment orchestration and jumpboxes.

  Attaches a console StreamHandler (default INFO level) for clean progress
  output and a FileHandler (default DEBUG level) for full diagnostic logs
  dumped on the jumpbox.

  Args:
      logger_name: Name of target logger namespace.
      level: Threshold logging severity level for console stream output.
      log_file: Optional explicit path to a log file. Overrides log_dir.
      log_dir: Optional directory path for timestamped log files (defaults to
        ./logs).
      file_level: Threshold logging severity level for the jumpbox log file.
      enable_file_logging: Whether to create and attach the jumpbox file
        handler.

  Returns:
      Configured logging.Logger instance with console and file handlers.
  """
  logger = logging.getLogger(logger_name)
  logger.propagate = False

  # Cleanly close and detach any existing handlers to avoid duplicate entries
  for handler in list(logger.handlers):
    try:
      handler.close()
    except Exception:  # pylint: disable=broad-exception-caught
      pass
    logger.removeHandler(handler)

  console_level = _parse_log_level(level, logging.INFO)
  resolved_file_level = _parse_log_level(file_level, logging.DEBUG)

  formatter = logging.Formatter(
      constants.DeployerDefaults.LOG_FORMAT,
      datefmt=constants.DeployerDefaults.LOG_DATE_FORMAT,
  )

  console_handler = logging.StreamHandler(sys.stdout)
  console_handler.setLevel(console_level)
  console_handler.setFormatter(formatter)
  logger.addHandler(console_handler)

  setattr(logger, "log_file_path", None)

  if enable_file_logging:
    if log_file and str(log_file).strip():
      resolved_log_file = os.path.abspath(
          os.path.expanduser(str(log_file).strip())
      )
    else:
      target_dir = os.path.expanduser(
          str(log_dir).strip()
          if (log_dir and str(log_dir).strip())
          else constants.DeployerDefaults.DEFAULT_LOG_DIR
      )
      timestamp = datetime.datetime.now().strftime(
          constants.DeployerDefaults.LOG_TIMESTAMP_FORMAT
      )
      filename = (
          f"{constants.DeployerDefaults.DEFAULT_LOG_FILENAME_PREFIX}_"
          f"{timestamp}.log"
      )
      resolved_log_file = os.path.abspath(os.path.join(target_dir, filename))

    try:
      log_parent_dir = os.path.dirname(resolved_log_file)
      if log_parent_dir:
        os.makedirs(log_parent_dir, exist_ok=True)
      file_handler = logging.FileHandler(
          resolved_log_file, mode="a", encoding="utf-8"
      )
      file_handler.setLevel(resolved_file_level)
      file_handler.setFormatter(formatter)
      logger.addHandler(file_handler)
      setattr(logger, "log_file_path", resolved_log_file)
    except OSError as exc:
      logger.warning(
          "Failed to initialize jumpbox log file at '%s': %s. Continuing with"
          " console logging only.",
          resolved_log_file,
          exc,
      )

  effective_logger_level = (
      min(console_level, resolved_file_level)
      if getattr(logger, "log_file_path", None)
      else console_level
  )
  logger.setLevel(effective_logger_level)

  return logger
