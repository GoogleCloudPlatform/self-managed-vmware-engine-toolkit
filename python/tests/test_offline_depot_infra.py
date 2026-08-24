"""Unit tests for vcf_deployer/offline_depot_infra.py module."""

import unittest
from unittest import mock

import constants
import models
from vcf_deployer import offline_depot_infra


class TestOfflineDepotInfraManager(unittest.TestCase):
  """Tests for OfflineDepotInfraManager orchestration across prod, staging, and autopush."""

  def setUp(self):
    super().setUp()
    self.mock_config = mock.MagicMock()
    self.mock_config.project = "test-project"
    self.mock_config.region = "us-central1"
    self.mock_config.offline_depot_subnet_cidr = "10.0.100.0/29"

    self.mock_gcp = mock.MagicMock()
    self.mock_gcp.create_offline_depot_subnetwork.return_value = (
        "projects/test-project/regions/us-central1/subnetworks/offline-depot-subnet-us-central1"
    )
    self.mock_gcp.reserve_psc_internal_ip.return_value = (
        "projects/test-project/regions/us-central1/addresses/offline-depot-psc-ip-us-central1",
        "10.0.100.2",
    )
    self.mock_gcp.create_offline_depot_forwarding_rule.return_value = (
        "projects/test-project/regions/us-central1/forwardingRules/offline-depot-psc-ep-us-central1"
    )

    self.manager = offline_depot_infra.OfflineDepotInfraManager(
        config=self.mock_config,
        gcp=self.mock_gcp,
        vpc_network="projects/test-project/global/networks/test-vpc",
        cidr="10.0.100.0/29",
    )

  def test_setup_offline_depot_infrastructure_empty_cidr_returns_empty(self):
    """Verifies that empty/missing CIDR returns empty dict."""
    self.manager.cidr = ""
    res = self.manager.setup_offline_depot_infrastructure()
    self.assertEqual(res, {})
    self.mock_gcp.create_offline_depot_subnetwork.assert_not_called()

  def test_setup_offline_depot_infrastructure_invalid_cidr_raises_validation_error(
      self,
  ):
    """Verifies that invalid CIDR or CIDR > /29 raises ValidationError."""
    self.manager.cidr = "10.0.100.0/30"
    with self.assertRaises(models.ValidationError) as ctx:
      self.manager.setup_offline_depot_infrastructure()
    self.assertIn("is too small", str(ctx.exception))

  @mock.patch.dict("os.environ", {}, clear=True)
  def test_setup_offline_depot_infrastructure_prod_environment(self):
    """Verifies full execution for default Prod environment."""
    res = self.manager.setup_offline_depot_infrastructure()

    self.assertEqual(res["psc_ip"], "10.0.100.2")
    self.assertEqual(
        res["fqdn"], "offline-depot.us-central1.selfmanagedvmwareengine.goog."
    )
    self.assertEqual(
        res["subnet_uri"],
        "projects/test-project/regions/us-central1/subnetworks/offline-depot-subnet-us-central1",
    )

    self.mock_gcp.create_offline_depot_subnetwork.assert_called_once_with(
        project="test-project",
        region="us-central1",
        name="offline-depot-subnet-us-central1",
        network="projects/test-project/global/networks/test-vpc",
        ip_cidr_range="10.0.100.0/29",
    )
    self.mock_gcp.reserve_psc_internal_ip.assert_called_once_with(
        project="test-project",
        region="us-central1",
        name="offline-depot-psc-ip-us-central1",
        subnet_uri="projects/test-project/regions/us-central1/subnetworks/offline-depot-subnet-us-central1",
    )
    self.mock_gcp.create_offline_depot_forwarding_rule.assert_called_once_with(
        project="test-project",
        region="us-central1",
        name="offline-depot-psc-ep-us-central1",
        network="projects/test-project/global/networks/test-vpc",
        subnet_uri="projects/test-project/regions/us-central1/subnetworks/offline-depot-subnet-us-central1",
        ip_address_link="projects/test-project/regions/us-central1/addresses/offline-depot-psc-ip-us-central1",
        target_service_attachment="projects/smve-offline-depot/regions/us-central1/serviceAttachments/offline-depot-service-attachment-us-central1",
    )
    self.mock_gcp.create_offline_depot_private_dns_zone_and_record.assert_called_once_with(
        project="test-project",
        zone_name="offline-depot-us-central1-prod-zone",
        dns_name="us-central1.selfmanagedvmwareengine.goog.",
        network_uri="projects/test-project/global/networks/test-vpc",
        a_record_fqdn="offline-depot.us-central1.selfmanagedvmwareengine.goog.",
        target_ip="10.0.100.2",
        ttl=constants.OfflineDepotDefaults.DNS_RECORD_TTL_SECONDS,
    )

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "autopush"})
  def test_setup_offline_depot_infrastructure_autopush_environment(self):
    """Verifies execution targeting Autopush Service Attachment and domain."""
    res = self.manager.setup_offline_depot_infrastructure()

    self.assertEqual(res["psc_ip"], "10.0.100.2")
    self.assertEqual(
        res["fqdn"], "offline-depot.us-central1.autopush.smve-vcf.internal."
    )

    self.mock_gcp.create_offline_depot_forwarding_rule.assert_called_once_with(
        project="test-project",
        region="us-central1",
        name="offline-depot-psc-ep-us-central1",
        network="projects/test-project/global/networks/test-vpc",
        subnet_uri="projects/test-project/regions/us-central1/subnetworks/offline-depot-subnet-us-central1",
        ip_address_link="projects/test-project/regions/us-central1/addresses/offline-depot-psc-ip-us-central1",
        target_service_attachment="projects/smve-autopush-offline-depot/regions/us-central1/serviceAttachments/offline-depot-service-attachment-us-central1",
    )
    self.mock_gcp.create_offline_depot_private_dns_zone_and_record.assert_called_once_with(
        project="test-project",
        zone_name="offline-depot-us-central1-autopush-zone",
        dns_name="us-central1.autopush.smve-vcf.internal.",
        network_uri="projects/test-project/global/networks/test-vpc",
        a_record_fqdn="offline-depot.us-central1.autopush.smve-vcf.internal.",
        target_ip="10.0.100.2",
        ttl=constants.OfflineDepotDefaults.DNS_RECORD_TTL_SECONDS,
    )

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "staging"})
  def test_setup_offline_depot_infrastructure_staging_environment(self):
    """Verifies execution targeting Staging Service Attachment and domain."""
    res = self.manager.setup_offline_depot_infrastructure()

    self.assertEqual(res["psc_ip"], "10.0.100.2")
    self.assertEqual(
        res["fqdn"], "offline-depot.us-central1.staging.smve-vcf.internal."
    )

    self.mock_gcp.create_offline_depot_forwarding_rule.assert_called_once_with(
        project="test-project",
        region="us-central1",
        name="offline-depot-psc-ep-us-central1",
        network="projects/test-project/global/networks/test-vpc",
        subnet_uri="projects/test-project/regions/us-central1/subnetworks/offline-depot-subnet-us-central1",
        ip_address_link="projects/test-project/regions/us-central1/addresses/offline-depot-psc-ip-us-central1",
        target_service_attachment="projects/smve-staging-offline-depot/regions/us-central1/serviceAttachments/offline-depot-service-attachment-us-central1",
    )
    self.mock_gcp.create_offline_depot_private_dns_zone_and_record.assert_called_once_with(
        project="test-project",
        zone_name="offline-depot-us-central1-staging-zone",
        dns_name="us-central1.staging.smve-vcf.internal.",
        network_uri="projects/test-project/global/networks/test-vpc",
        a_record_fqdn="offline-depot.us-central1.staging.smve-vcf.internal.",
        target_ip="10.0.100.2",
        ttl=constants.OfflineDepotDefaults.DNS_RECORD_TTL_SECONDS,
    )


if __name__ == "__main__":
  unittest.main()
