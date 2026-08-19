"""Unit test package for VCF Deployment Automation suite."""

import os
import sys

# Ensure top-level 'python/' directory is in sys.path across all test modules
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
  sys.path.insert(0, parent_dir)
