"""Unit tests for vcf_deployer/network_setup.py module."""

import unittest
from unittest import mock

import models
from vcf_deployer import network_setup


class TestNetworkManager(unittest.TestCase):
  """Tests for Phase 2a ESXi NetworkManager port group configuration."""

  def setUp(self):
    super().setUp()
    self.mock_esxi = mock.MagicMock()
    self.mock_net_sys = mock.MagicMock()
    self.mock_net_sys.networkInfo.portgroup = []
    self.mock_esxi.get_network_system.return_value = self.mock_net_sys
    self.net_mgr = network_setup.NetworkManager(esxi=self.mock_esxi)

  @mock.patch("vcf_deployer.network_setup.vim")
  def test_configure_networking_success(self, mock_vim):
    """Verifies successful creation of port group on target vSwitch."""
    mock_spec = mock.MagicMock()
    mock_vim.host.PortGroup.Specification.return_value = mock_spec

    result_pg = self.net_mgr.configure_networking(
        vlan_id=100, port_group_name="vlan-100-a1b2", vswitch_name="vSwitch0"
    )

    self.assertEqual(result_pg, "vlan-100-a1b2")
    self.mock_esxi.connect_pyvmomi.assert_called_once()
    self.mock_net_sys.AddPortGroup.assert_called_once()
    self.assertEqual(mock_spec.name, "vlan-100-a1b2")
    self.assertEqual(mock_spec.vlanId, 100)
    self.assertEqual(mock_spec.vswitchName, "vSwitch0")

  @mock.patch("vcf_deployer.network_setup.vim")
  def test_configure_networking_existing_found_skips_creation(self, mock_vim):
    """Verifies existing port group matching regex format is reused and creation skipped."""
    mock_existing_pg = mock.MagicMock()
    mock_existing_pg.spec.name = "vlan-100-c3d4"
    mock_existing_pg.spec.vlanId = 100
    mock_existing_pg.spec.vswitchName = "vSwitch0"
    self.mock_net_sys.networkInfo.portgroup = [mock_existing_pg]

    result_pg = self.net_mgr.configure_networking(
        vlan_id=100, port_group_name="vlan-100-a1b2", vswitch_name="vSwitch0"
    )

    self.assertEqual(result_pg, "vlan-100-c3d4")
    self.mock_esxi.connect_pyvmomi.assert_called_once()
    self.mock_net_sys.AddPortGroup.assert_not_called()

  @mock.patch("vcf_deployer.network_setup.vim", None)
  def test_add_port_group_missing_pyvmomi_raises_non_retryable(self):
    """Verifies NonRetryableError when pyVmomi package is missing."""
    with self.assertRaises(models.NonRetryableError) as ctx:
      self.net_mgr._add_port_group(
          self.mock_net_sys, "vlan-100-a1b2", 100, "vSwitch0"
      )
    self.assertIn("pyVmomi package is not installed", str(ctx.exception))

  @mock.patch("vcf_deployer.network_setup.vim")
  def test_add_port_group_api_error_raises_non_retryable(self, mock_vim):
    """Verifies NonRetryableError when AddPortGroup throws an exception."""
    self.mock_net_sys.AddPortGroup.side_effect = Exception(
        "SOAP fault: Invalid switch"
    )
    with self.assertRaises(models.NonRetryableError) as ctx:
      self.net_mgr._add_port_group(
          self.mock_net_sys, "vlan-100-a1b2", 100, "vSwitch0"
      )
    self.assertIn("Failed to add port group", str(ctx.exception))

  def test_get_existing_port_groups(self):
    """Verifies parsing of existing port groups from HostNetworkSystem."""
    mock_net_sys = mock.MagicMock()
    mock_pg1 = mock.MagicMock()
    mock_pg1.spec.name = "vlan-100-a1b2"
    mock_pg1.spec.vlanId = 100
    mock_pg1.spec.vswitchName = "vSwitch0"

    mock_pg2 = mock.MagicMock()
    mock_pg2.spec.name = "Management Network"
    mock_pg2.spec.vlanId = 0
    mock_pg2.spec.vswitchName = "vSwitch0"

    mock_net_sys.networkInfo.portgroup = [mock_pg1, mock_pg2]

    pgs = self.net_mgr._get_existing_port_groups(mock_net_sys)
    self.assertEqual(len(pgs), 2)
    self.assertEqual(pgs[0]["name"], "vlan-100-a1b2")
    self.assertEqual(pgs[0]["vlan_id"], 100)

  def test_get_existing_port_groups_empty(self):
    """Verifies handling of empty or missing networkInfo."""
    mock_net_sys = mock.MagicMock()
    mock_net_sys.networkInfo = None
    pgs = self.net_mgr._get_existing_port_groups(mock_net_sys)
    self.assertEqual(pgs, [])


if __name__ == "__main__":
  unittest.main()
