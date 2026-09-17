"""Unit tests for utils/logger.py module."""

import logging
import os
import tempfile
import unittest
from unittest import mock

import constants
from utils import logger as logger_mod


class TestLogger(unittest.TestCase):
  """Tests for jumpbox console and file logging setup."""

  def setUp(self):
    super().setUp()
    self._temp_dir = tempfile.TemporaryDirectory()

  def tearDown(self):
    test_logger = logging.getLogger("test_jumpbox_logger")
    for handler in list(test_logger.handlers):
      handler.close()
      test_logger.removeHandler(handler)
    self._temp_dir.cleanup()
    super().tearDown()

  def test_parse_log_level(self):
    """Verifies string and integer log level resolution."""
    self.assertEqual(logger_mod._parse_log_level(logging.DEBUG), logging.DEBUG)
    self.assertEqual(logger_mod._parse_log_level("DEBUG"), logging.DEBUG)
    self.assertEqual(logger_mod._parse_log_level("info"), logging.INFO)
    self.assertEqual(logger_mod._parse_log_level("WARNING"), logging.WARNING)
    self.assertEqual(
        logger_mod._parse_log_level("INVALID_LEVEL", default=logging.ERROR),
        logging.ERROR,
    )

  def test_setup_logger_creates_timestamped_file_in_log_dir(self):
    """Verifies default timestamped log file creation and DEBUG level capture."""
    log = logger_mod.setup_logger(
        logger_name="test_jumpbox_logger",
        level="INFO",
        log_dir=self._temp_dir.name,
        file_level="DEBUG",
    )
    log_file_path = getattr(log, "log_file_path", None)
    self.assertIsNotNone(log_file_path)
    self.assertTrue(os.path.exists(log_file_path))
    self.assertTrue(
        os.path.basename(log_file_path).startswith(
            constants.DeployerDefaults.DEFAULT_LOG_FILENAME_PREFIX
        )
    )

    log.debug("Detailed debug message for jumpbox file")
    log.info("Progress info message")

    for handler in log.handlers:
      handler.flush()

    with open(log_file_path, "r", encoding="utf-8") as f:
      content = f.read()
    self.assertIn("Detailed debug message for jumpbox file", content)
    self.assertIn("Progress info message", content)

  def test_setup_logger_explicit_log_file(self):
    """Verifies explicit --log-file path overrides log_dir."""
    explicit_path = os.path.join(self._temp_dir.name, "sub", "custom.log")
    log = logger_mod.setup_logger(
        logger_name="test_jumpbox_logger",
        level="INFO",
        log_file=explicit_path,
        log_dir=self._temp_dir.name,
    )
    self.assertEqual(getattr(log, "log_file_path", None), explicit_path)
    self.assertTrue(os.path.exists(explicit_path))

  def test_setup_logger_disable_file_logging(self):
    """Verifies enable_file_logging=False attaches only console handler."""
    log = logger_mod.setup_logger(
        logger_name="test_jumpbox_logger",
        enable_file_logging=False,
    )
    self.assertIsNone(getattr(log, "log_file_path", None))
    self.assertEqual(len(log.handlers), 1)
    self.assertIsInstance(log.handlers[0], logging.StreamHandler)

  @mock.patch("os.makedirs", side_effect=OSError("Permission denied"))
  def test_setup_logger_graceful_fallback_on_oserror(self, mock_makedirs):
    """Verifies logger falls back to console logging if file creation fails."""
    log = logger_mod.setup_logger(
        logger_name="test_jumpbox_logger",
        log_dir="/root/forbidden/logs",
    )
    self.assertIsNone(getattr(log, "log_file_path", None))
    self.assertEqual(len(log.handlers), 1)


if __name__ == "__main__":
  unittest.main()
