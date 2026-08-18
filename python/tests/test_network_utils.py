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


if __name__ == "__main__":
  unittest.main()
