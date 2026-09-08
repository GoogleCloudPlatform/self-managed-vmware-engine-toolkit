"""Unit tests for utils/network_utils.py module."""

import unittest
from unittest import mock

import models
from utils import network_utils


class TestNetworkUtils(unittest.TestCase):
  """Tests for network routing, subnetwork containment, and SSL thumbprint extraction."""

  def setUp(self):
    super().setUp()
    self.mock_gcp = mock.MagicMock()
    self.target_details = models.GCEInstanceDetails(
        instance_resource_string=(
            "projects/proj/zones/us-central1-a/instances/esxi-1"
        ),
        short_name="esxi-1",
        project="proj",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[
            models.SubnetworkInfo(
                subnetwork_uri=(
                    "projects/proj/regions/us-central1/subnetworks/sub-primary"
                ),
                vlan_id=0,
                network_uri="projects/proj/global/networks/vpc-1",
                cidr="10.0.0.0/24",
            ),
            models.SubnetworkInfo(
                subnetwork_uri=(
                    "projects/proj/regions/us-central1/subnetworks/sub-dynamic"
                ),
                vlan_id=100,
                network_uri="projects/proj/global/networks/vpc-1",
                cidr="172.16.100.0/24",
            ),
        ],
        tags=["esxi-node"],
        tags_fingerprint="fp1",
    )

  def test_extract_vlan_cidr_and_routing_primary_nic(self):
    """Verifies subnetwork containment and routing extraction for primary NIC (VLAN 0)."""
    vlan_id, cidr, netmask, gateway = (
        network_utils.extract_vlan_cidr_and_routing(
            "10.0.0.50", self.target_details, self.mock_gcp
        )
    )
    self.assertEqual(vlan_id, 0)
    self.assertEqual(cidr, "10.0.0.0/24")
    self.assertEqual(netmask, "255.255.255.0")
    self.assertEqual(gateway, "10.0.0.1")

  def test_extract_vlan_cidr_and_routing_dynamic_nic(self):
    """Verifies subnetwork containment for dynamic alias NIC (VLAN > 0)."""
    vlan_id, cidr, netmask, gateway = (
        network_utils.extract_vlan_cidr_and_routing(
            "172.16.100.25", self.target_details, self.mock_gcp
        )
    )
    self.assertEqual(vlan_id, 100)
    self.assertEqual(cidr, "172.16.100.0/24")
    self.assertEqual(netmask, "255.255.255.0")
    self.assertEqual(gateway, "172.16.100.1")

  def test_extract_vlan_cidr_and_routing_invalid_ip_format(self):
    """Verifies ValidationError when VCF IP format is invalid."""
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.extract_vlan_cidr_and_routing(
          "invalid-ip", self.target_details, self.mock_gcp
      )
    self.assertIn("not valid IPv4", str(ctx.exception))

  def test_extract_vlan_cidr_and_routing_unmatched_subnet(self):
    """Verifies ValidationError when VCF IP is outside all attached subnets."""
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.extract_vlan_cidr_and_routing(
          "192.168.1.100", self.target_details, self.mock_gcp
      )
    self.assertIn(
        "does not fall within any primary or dynamic NIC subnetwork",
        str(ctx.exception),
    )

  def test_extract_vlan_cidr_and_routing_reserved_gcp_ip(self):
    """Verifies ValidationError when VCF IP lands on GCP reserved network/gateway addresses."""
    # .1 is the gateway IP in GCP subnetwork
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.extract_vlan_cidr_and_routing(
          "10.0.0.1", self.target_details, self.mock_gcp
      )
    self.assertIn(
        "falls on a reserved GCP subnetwork address", str(ctx.exception)
    )

  @mock.patch("socket.create_connection")
  @mock.patch("ssl._create_unverified_context")
  def test_capture_ssl_thumbprint_success(self, mock_ssl_ctx, mock_socket):
    """Verifies SHA-256 certificate thumbprint extraction over SSL socket."""
    self.assertIsNotNone(mock_socket)
    mock_ssock = mock.MagicMock()
    # 32 bytes of DER cert data
    fake_cert_bytes = b"01234567890123456789012345678901"
    mock_ssock.getpeercert.return_value = fake_cert_bytes

    mock_context_inst = mock.MagicMock()
    mock_context_inst.wrap_socket.return_value.__enter__.return_value = (
        mock_ssock
    )
    mock_ssl_ctx.return_value = mock_context_inst

    thumbprint = network_utils.capture_ssl_thumbprint(
        "https://depot.example.com/ova"
    )
    self.assertIsInstance(thumbprint, str)
    self.assertEqual(len(thumbprint.split(":")), 32)

  @mock.patch("socket.create_connection")
  def test_capture_ssl_thumbprint_connection_failure_retryable_error(
      self, mock_socket
  ):
    """Verifies RetryableError on socket connection failure."""
    mock_socket.side_effect = TimeoutError("Connection timed out")
    with self.assertRaises(models.RetryableError) as ctx:
      network_utils.capture_ssl_thumbprint("https://unreachable.depot.com")
    self.assertIn("Failed to connect", str(ctx.exception))

  def test_validate_subnet_cidr_size_valid(self):
    """Verifies valid CIDRs with prefix length <= 29 pass validation."""
    network_utils.validate_subnet_cidr_size("10.0.100.0/29")
    network_utils.validate_subnet_cidr_size("10.0.0.0/24")
    network_utils.validate_subnet_cidr_size("172.16.0.0/16")

  def test_validate_subnet_cidr_size_too_small_raises_validation_error(self):
    """Verifies ValidationError when prefix length > 29 (/30, /31, /32)."""
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_size("10.0.100.0/30")
    self.assertIn("is too small", str(ctx.exception))

    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_size("10.0.100.0/32")
    self.assertIn("is too small", str(ctx.exception))

  def test_validate_subnet_cidr_size_invalid_format_raises_validation_error(self):
    """Verifies ValidationError on empty or malformed CIDR."""
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_size("")
    self.assertIn("missing or empty", str(ctx.exception))

    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_size("not-a-cidr")
    self.assertIn("Invalid subnet CIDR format", str(ctx.exception))

  def test_validate_subnet_cidr_not_in_use_success(self):
    """Verifies that non-overlapping CIDR passes validation."""
    mock_gcp = mock.MagicMock()
    existing = [
        models.SubnetworkInfo(
            subnetwork_uri="projects/p/regions/r/subnetworks/sub-1",
            vlan_id=0,
            network_uri="projects/p/global/networks/vpc",
            cidr="10.0.0.0/24",
        )
    ]
    network_utils.validate_subnet_cidr_not_in_use(
        "10.0.100.0/29", existing, mock_gcp
    )
    mock_gcp.fetch_subnetwork_cidr.assert_not_called()

  def test_validate_subnet_cidr_not_in_use_overlapping_raises_validation_error(
      self,
  ):
    """Verifies ValidationError when offline depot CIDR overlaps an existing subnet."""
    mock_gcp = mock.MagicMock()
    existing = [
        models.SubnetworkInfo(
            subnetwork_uri="projects/p/regions/r/subnetworks/mgmt-sub",
            vlan_id=0,
            network_uri="projects/p/global/networks/vpc",
            cidr="10.0.0.0/24",
        )
    ]
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_not_in_use(
          "10.0.0.0/29", existing, mock_gcp
      )
    self.assertIn(
        "overlaps with or is already used by existing subnet",
        str(ctx.exception),
    )
    self.assertIn("projects/p/regions/r/subnetworks/mgmt-sub", str(ctx.exception))

  def test_validate_subnet_cidr_not_in_use_fetches_cidr_if_missing(self):
    """Verifies fetch_subnetwork_cidr is invoked when subnet CIDR is empty."""
    mock_gcp = mock.MagicMock()
    mock_gcp.fetch_subnetwork_cidr.return_value = "10.0.0.0/24"
    existing = [
        models.SubnetworkInfo(
            subnetwork_uri="projects/p/regions/r/subnetworks/mgmt-sub",
            vlan_id=0,
            network_uri="projects/p/global/networks/vpc",
        )
    ]
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_not_in_use(
          "10.0.0.0/29", existing, mock_gcp
      )
    mock_gcp.fetch_subnetwork_cidr.assert_called_once_with(
        "projects/p/regions/r/subnetworks/mgmt-sub"
    )
    self.assertIn("overlaps with or is already used by existing subnet", str(ctx.exception))

  def test_validate_subnet_cidr_not_in_use_invalid_cidr_raises_validation_error(
      self,
  ):
    """Verifies ValidationError when target CIDR format is invalid."""
    mock_gcp = mock.MagicMock()
    with self.assertRaises(models.ValidationError) as ctx:
      network_utils.validate_subnet_cidr_not_in_use(
          "invalid-cidr", [], mock_gcp
      )
    self.assertIn("Invalid subnet CIDR format", str(ctx.exception))

  def test_validate_subnet_cidr_not_in_use_empty_cidr_noop(self):
    """Verifies that empty CIDR returns without performing checks."""
    mock_gcp = mock.MagicMock()
    network_utils.validate_subnet_cidr_not_in_use("", [], mock_gcp)
    mock_gcp.fetch_subnetwork_cidr.assert_not_called()


if __name__ == "__main__":
  unittest.main()

