"""Unit tests for vcf_deployer/vsan_setup.py module."""

import json
import unittest
from unittest import mock

import constants
import models
from vcf_deployer import vsan_setup


class TestVSANManager(unittest.TestCase):
  """Tests for Phase 2b VSANManager ESA cluster initialization and disk claiming."""

  def setUp(self):
    super().setUp()
    self.mock_esxi = mock.MagicMock()
    self.vsan_mgr = vsan_setup.VSANManager(esxi=self.mock_esxi)

  def test_check_and_init_cluster_already_enabled(self):
    """Verifies skipping cluster init when vSAN is already enabled."""
    self.mock_esxi.execute_esxcli.return_value = (
        "vSAN Cluster Information\n  Enabled: true\n  Node UUID: 12345"
    )
    self.vsan_mgr._check_and_init_cluster()
    self.mock_esxi.execute_esxcli.assert_called_once_with(
        ["vsan", "cluster", "get"]
    )

  def test_check_and_init_cluster_new_init(self):
    """Verifies initializing new vSAN cluster when state is disabled."""
    self.mock_esxi.execute_esxcli.side_effect = [
        "vSAN Cluster Information\n  Enabled: false",
        "Cluster initialized successfully",
    ]
    self.vsan_mgr._check_and_init_cluster()
    self.assertEqual(self.mock_esxi.execute_esxcli.call_count, 2)
    self.mock_esxi.execute_esxcli.assert_has_calls([
        mock.call(["vsan", "cluster", "get"]),
        mock.call(["vsan", "cluster", "new", "-x"]),
    ])

  def test_query_vdq_via_ssh_success(self):
    """Verifies SSH /sbin/vdq -q output parsing into eligible and in-use disk lists."""
    vdq_json = json.dumps([
        {
            "Name": "naa.6000c290000000000000000000000001",
            "State": "Eligible for use by storage pool",
        },
        {
            "Name": "naa.6000c290000000000000000000000002",
            "State": "Eligible for use by storage pool",
        },
        {
            "Name": "naa.6000c290000000000000000000000003",
            "State": "In-use for storage pool",
        },
    ])
    self.mock_esxi.execute_ssh_command.return_value = vdq_json
    eligible, in_use = self.vsan_mgr._query_vdq_via_ssh()

    self.assertEqual(len(eligible), 2)
    self.assertEqual(len(in_use), 1)
    self.assertIn("naa.6000c290000000000000000000000001", eligible)
    self.assertIn("naa.6000c290000000000000000000000003", in_use)

  def test_query_vdq_via_ssh_decode_error(self):
    """Verifies NonRetryableError when /sbin/vdq -q returns invalid JSON."""
    self.mock_esxi.execute_ssh_command.return_value = "Invalid Non-JSON Output"
    with self.assertRaises(models.NonRetryableError) as ctx:
      self.vsan_mgr._query_vdq_via_ssh()
    self.assertIn("Failed to decode /sbin/vdq -q output", str(ctx.exception))

  def test_claim_disks_in_bulk(self):
    """Verifies bulk disk claiming via esxcli vsan storagepool add."""
    eligible_disks = [
        "naa.6000c290000000000000000000000001",
        "naa.6000c290000000000000000000000002",
    ]
    self.vsan_mgr._claim_disks_in_bulk(eligible_disks)
    self.mock_esxi.execute_esxcli.assert_called_once_with([
        "vsan",
        "storagepool",
        "add",
        "-d",
        "naa.6000c290000000000000000000000001",
        "-d",
        "naa.6000c290000000000000000000000002",
    ])

  def test_setup_vsan_full_flow(self):
    """Verifies end-to-end setup_vsan flow including policy bindings."""
    self.mock_esxi.execute_esxcli.return_value = "Enabled: true"
    vdq_json = json.dumps([{
        "Name": "naa.6000c290000000000000000000000001",
        "State": "Eligible for use by storage pool",
    }])
    self.mock_esxi.execute_ssh_command.return_value = vdq_json

    self.vsan_mgr.setup_vsan()

    # Verify storagepool add was called
    self.mock_esxi.execute_esxcli.assert_any_call([
        "vsan",
        "storagepool",
        "add",
        "-d",
        "naa.6000c290000000000000000000000001",
    ])
    # Verify default policies were set (5 policy calls)
    policy_calls = [
        c
        for c in self.mock_esxi.execute_esxcli.call_args_list
        if c[0][0] and c[0][0][0] == "vsan" and c[0][0][1] == "policy"
    ]
    self.assertEqual(
        len(policy_calls), len(constants.VSANConstants.DEFAULT_VSAN_POLICIES)
    )

  def test_setup_vsan_no_disks_found_raises_error(self):
    """Verifies NonRetryableError when no eligible or in-use disks exist."""
    self.mock_esxi.execute_esxcli.return_value = "Enabled: true"
    self.mock_esxi.execute_ssh_command.return_value = "[]"

    with self.assertRaises(models.NonRetryableError) as ctx:
      self.vsan_mgr.setup_vsan()
    self.assertIn(
        "No eligible or in-use disks found to add to Storage Pool",
        str(ctx.exception),
    )


if __name__ == "__main__":
  unittest.main()
