"""Unit tests for vcf_deployer/validator.py module."""

import unittest
from unittest import mock

from clients import gcp_client
import models
from vcf_deployer import validator


class TestPreDeploymentValidator(unittest.TestCase):
  """Tests for Phase 1 PreDeploymentValidator pre-flight gates and context extraction."""

  def setUp(self):
    super().setUp()
    self.mock_gcp = mock.MagicMock()
    self.mock_config = mock.MagicMock()
    self.mock_config.gce_nodes = []
    self.mock_gcp.resolve_gce_nodes.side_effect = (
        lambda insts, project=None, zone=None: gcp_client.GCPClient.resolve_gce_nodes(
            self.mock_gcp, insts, project or "p", zone or "z"
        )
    )
    self.validator = validator.PreDeploymentValidator(
        config=self.mock_config, gcp=self.mock_gcp
    )

  def test_validate_gce_nodes_empty_list_raises_validation_error(self):
    """Verifies ValidationError when gce_nodes is empty."""
    self.mock_config.gce_nodes = []
    with self.assertRaises(models.ValidationError) as ctx:
      self.validator._validate_gce_nodes()
    self.assertIn(
        "gce_nodes in configuration profile is empty",
        str(ctx.exception),
    )

  def test_validate_gce_nodes_invalid_ip_raises_validation_error(self):
    """Verifies ValidationError when GCE node returns an invalid primary IP."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.get_full_node_path.return_value = (
        "projects/p/zones/z/instances/esxi-1"
    )
    mock_details = mock.MagicMock()
    mock_details.primary_ip = "invalid_ip_string"
    self.mock_gcp.get_instance_details.return_value = mock_details

    with self.assertRaises(models.ValidationError) as ctx:
      self.validator._validate_gce_nodes()
    self.assertIn("returned malformed IPv4 address", str(ctx.exception))

  def test_validate_gce_nodes_valid(self):
    """Verifies single-pass inspection and boot image validation for all inventory nodes."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.get_full_node_path.return_value = (
        "projects/p/zones/z/instances/esxi-1"
    )
    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details

    details_map = self.validator._validate_gce_nodes()
    self.assertEqual(len(details_map), 1)
    self.assertIn("projects/p/zones/z/instances/esxi-1", details_map)
    self.assertEqual(
        details_map["projects/p/zones/z/instances/esxi-1"].primary_ip,
        "10.0.0.5",
    )

  def test_extract_and_audit_secrets_valid(self):
    """Verifies reading and auditing secrets from Secret Manager."""
    self.mock_config.esxi_root_password_secret = "esxi-root"
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    self.mock_config.vcf_deployment_config = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source="10.0.0.50",
        offline_depot_subnet_cidr="10.0.100.0/29",
    )

    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",  # esxi_root
        "ComplexVCF_Admin_P@ssword123",  # vcf_root
        "ComplexVCF_Local_P@ss123",  # vcf_local
    ]

    esxi_root, vcf_root, vcf_local = self.validator._extract_and_audit_secrets()
    self.assertEqual(esxi_root, "ValidESXiP@ss123!")
    self.assertEqual(vcf_root, "ComplexVCF_Admin_P@ssword123")
    self.assertEqual(vcf_local, "ComplexVCF_Local_P@ss123")

  def test_govern_gce_node_tags_patches_missing_tags_and_labels(self):
    """Verifies set_instance_tags and set_instance_labels when mandatory tags/labels are missing."""
    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="fp_tag",
        labels={},
        label_fingerprint="fp_label",
    )
    details_map = {"esxi-1": mock_details}

    self.validator._govern_gce_node_tags(details_map)

    self.mock_gcp.set_instance_tags.assert_called_once_with(
        project="p",
        zone="z",
        instance_name="esxi-1",
        new_tags=["mm-gcve-node"],
        fingerprint="fp_tag",
    )
    self.mock_gcp.set_instance_labels.assert_called_once_with(
        project="p",
        zone="z",
        instance_name="esxi-1",
        new_labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )

  def test_validate_gce_nodes_multiple_parallel(self):
    """Verifies parallel inspection of multiple GCE nodes preserving order."""
    self.mock_config.gce_nodes = ["esxi-1", "esxi-2", "esxi-3"]
    self.mock_config.get_full_node_path.side_effect = (
        lambda s: f"projects/p/zones/z/instances/{s}"
    )

    def get_details_side_effect(path):
      short = path.split("/")[-1]
      return models.GCEInstanceDetails(
          instance_resource_string=path,
          short_name=short,
          project="p",
          zone="z",
          primary_ip=f"10.0.0.{short[-1]}",
          boot_image_name="esxi-5-1-1-12345",
          subnetworks=[],
          tags=[],
          tags_fingerprint="",
      )

    self.mock_gcp.get_instance_details.side_effect = get_details_side_effect

    details_map = self.validator._validate_gce_nodes()
    self.assertEqual(len(details_map), 3)
    self.assertIn("projects/p/zones/z/instances/esxi-1", details_map)
    self.assertIn("projects/p/zones/z/instances/esxi-2", details_map)
    self.assertIn("projects/p/zones/z/instances/esxi-3", details_map)
    self.assertEqual(
        details_map["projects/p/zones/z/instances/esxi-2"].primary_ip,
        "10.0.0.2",
    )

  def test_govern_gce_node_tags_multiple_parallel(self):
    """Verifies parallel governance of tags/labels across multiple nodes."""
    details_map = {
        f"esxi-{i}": models.GCEInstanceDetails(
            instance_resource_string=f"projects/p/zones/z/instances/esxi-{i}",
            short_name=f"esxi-{i}",
            project="p",
            zone="z",
            primary_ip=f"10.0.0.{i}",
            boot_image_name="esxi-5-1-1-12345",
            subnetworks=[],
            tags=[],
            tags_fingerprint=f"fp_tag_{i}",
            labels={},
            label_fingerprint=f"fp_label_{i}",
        )
        for i in range(1, 4)
    }

    self.validator._govern_gce_node_tags(details_map)
    self.assertEqual(self.mock_gcp.set_instance_tags.call_count, 3)
    self.assertEqual(self.mock_gcp.set_instance_labels.call_count, 3)

  def test_validate_gce_nodes_with_prefix_dict(self):
    """Verifies node resolution when gce_nodes is a dict with prefix."""
    self.mock_gcp.resolve_gce_nodes.side_effect = None
    self.mock_config.gce_nodes = {"prefix": "esxi-"}
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.return_value = (
        "projects/p/zones/z/instances/esxi-1"
    )
    self.mock_gcp.resolve_gce_nodes.return_value = ["esxi-1"]

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details

    details_map = self.validator._validate_gce_nodes()
    self.assertEqual(len(details_map), 1)
    self.mock_gcp.resolve_gce_nodes.assert_called_once_with(
        {"prefix": "esxi-"}, project="p", zone="z"
    )

  def test_validate_gce_nodes_with_subnet_dict(self):
    """Verifies node resolution when gce_nodes is a dict with subnet."""
    self.mock_gcp.resolve_gce_nodes.side_effect = None
    self.mock_config.gce_nodes = {"subnet": "my-subnet"}
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.return_value = (
        "projects/p/zones/z/instances/esxi-1"
    )
    self.mock_gcp.resolve_gce_nodes.return_value = ["esxi-1"]

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details

  def test_validate_gce_nodes_with_both_prefix_and_subnet_dict(self):
    """Verifies node resolution when gce_nodes is a dict with both prefix and subnet."""
    self.mock_gcp.resolve_gce_nodes.side_effect = None
    self.mock_config.gce_nodes = {
        "prefix": "esxi-",
        "subnet": "my-subnet",
    }
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.return_value = (
        "projects/p/zones/z/instances/esxi-1"
    )
    self.mock_gcp.resolve_gce_nodes.return_value = ["esxi-1"]

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details

    details_map = self.validator._validate_gce_nodes()
    self.assertEqual(len(details_map), 1)
    self.mock_gcp.resolve_gce_nodes.assert_called_once_with(
        {"prefix": "esxi-", "subnet": "my-subnet"}, project="p", zone="z"
    )

  def test_validate_and_extract_no_vcf_config(self):
    """Verifies Phase 1 completion and context generation when VCF deployment config is omitted."""
    self.mock_config.gce_nodes = [
        "projects/p/zones/z/instances/esxi-1"
    ]
    self.mock_config.prefix = None
    self.mock_config.subnet = None
    self.mock_config.vcf_deployment_config = None
    self.mock_config.esxi_root_password_sm_path = (
        "secrets/esxi-root/versions/latest"
    )

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.return_value = "ValidESXiP@ss123!"

    ctx = self.validator.validate_and_extract()

    self.assertEqual(ctx.new_esxi_root_password, "ValidESXiP@ss123!")
    self.assertIsNone(ctx.target_esxi_ip)
    self.assertIsNone(ctx.vcf_installer_ip)

  @mock.patch("urllib.request.urlopen")
  def test_derive_vcf_ova_url_success(self, mock_urlopen):
    """Verifies deriving VCF OVA URL from offline depot index."""
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = (
        b'<a href="VCF-SDDC-Manager-Appliance-5.1.1.200.ova">link</a>\n'
        b'<a href="VCF-SDDC-Manager-Appliance-5.1.1.450.ova">link</a>'
    )
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    mock_details = models.GCEInstanceDetails(
        instance_resource_string=(
            "projects/p/zones/us-central1-a/instances/esxi-1"
        ),
        short_name="esxi-1",
        project="p",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )

    url = self.validator._derive_vcf_ova_url(mock_details)
    self.assertIn("VCF-SDDC-Manager-Appliance-5.1.1.450.ova", url)
    self.assertIn("offline-depot.us-central1.selfmanagedvmwareengine.goog", url)

  @mock.patch("urllib.request.urlopen")
  def test_derive_vcf_ova_url_no_matching_ova_raises_validation_error(
      self, mock_urlopen
  ):
    """Verifies ValidationError when no OVA files match the required VCF version prefix."""
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = (
        b'<a href="VCF-SDDC-Manager-Appliance-4.5.0.100.ova">link</a>'
    )
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )

    with self.assertRaises(models.ValidationError) as ctx:
      self.validator._derive_vcf_ova_url(mock_details)
    self.assertIn("No OVA files found matching prefix", str(ctx.exception))

  @mock.patch("urllib.request.urlopen")
  def test_derive_vcf_ova_url_http_error_raises_validation_error(
      self, mock_urlopen
  ):
    """Verifies ValidationError when fetching depot index fails with HTTP exception."""
    mock_urlopen.side_effect = Exception("HTTP 404 Not Found")
    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )

    with self.assertRaises(models.ValidationError) as ctx:
      self.validator._derive_vcf_ova_url(mock_details)
    self.assertIn(
        "Failed to fetch OVA index from offline depot server",
        str(ctx.exception),
    )

  @mock.patch("vcf_deployer.offline_depot_infra.OfflineDepotInfraManager")
  @mock.patch("utils.network_utils.capture_ssl_thumbprint")
  @mock.patch("utils.network_utils.extract_vlan_cidr_and_routing")
  @mock.patch.object(validator.PreDeploymentValidator, "_derive_vcf_ova_url")
  def test_validate_and_extract_full_vcf_flow(
      self, mock_derive_url, mock_extract_vlan, mock_capture_thumbprint, mock_infra_mgr_cls
  ):
    """Verifies full Phase 1 validation and ValidationContext generation for VCF deployment."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.region = "z"
    self.mock_config.get_full_node_path.side_effect = (
        lambda inst: inst
        if inst.startswith("projects/")
        else f"projects/p/zones/z/instances/{inst}"
    )
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.100.0/29",
    )
    self.mock_config.vcf_deployment_config = vcf_cfg
    self.mock_config.esxi_root_password_secret = "esxi-root"

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[
            models.SubnetworkInfo(
                subnetwork_uri="projects/p/regions/z/subnetworks/sub-1",
                vlan_id=0,
                network_uri="projects/p/global/networks/vpc-1",
                cidr="10.0.0.0/24",
            )
        ],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",
        "ComplexVCF_Admin_P@ssword123",
        "ComplexVCF_Local_P@ss123",
    ]
    mock_infra_mgr_cls.return_value.setup_offline_depot_infrastructure.return_value = {
        "psc_ip": "10.0.100.2",
        "fqdn": "offline-depot.z.selfmanagedvmwareengine.goog.",
        "subnet_uri": "projects/p/regions/z/subnetworks/sub-1",
    }
    self.mock_gcp.resolve_ip_source.return_value = "10.0.0.50"
    mock_derive_url.return_value = "https://10.0.100.2/vcf.ova"
    mock_extract_vlan.return_value = (
        100,
        "10.0.0.0/24",
        "255.255.255.0",
        "10.0.0.1",
    )
    mock_capture_thumbprint.return_value = "AA:BB:CC:DD"

    ctx = self.validator.validate_and_extract()

    self.assertEqual(ctx.target_esxi_ip, "10.0.0.5")
    self.assertEqual(ctx.vcf_installer_ip, "10.0.0.50")
    self.assertEqual(ctx.vcf_installer_ova_url, "https://10.0.100.2/vcf.ova")
    self.assertEqual(ctx.vlan_id, 100)
    self.assertEqual(ctx.sddc_manager_netmask, "255.255.255.0")
    self.assertEqual(ctx.sddc_manager_gateway, "10.0.0.1")
    self.assertEqual(ctx.vcf_vm_name, "sddc-manager")
    self.assertEqual(ctx.vcf_domain, "lab.local")
    self.assertEqual(ctx.ssl_thumbprint, "AA:BB:CC:DD")

  def test_validate_and_extract_target_instance_missing_raises_validation_error(
      self,
  ):
    """Verifies ValidationError when target_gce_node is not in gce_nodes."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.side_effect = (
        lambda inst: inst
        if inst.startswith("projects/")
        else f"projects/p/zones/z/instances/{inst}"
    )
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="non-existent",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.100.0/29",
    )
    self.mock_config.vcf_deployment_config = vcf_cfg
    self.mock_config.esxi_root_password_secret = "esxi-root"

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",
        "ComplexVCF_Admin_P@ssword123",
        "ComplexVCF_Local_P@ss123",
    ]

    with self.assertRaises(models.ValidationError) as ctx:
      self.validator.validate_and_extract()
    self.assertIn("Designated target_gce_node", str(ctx.exception))

  @mock.patch("urllib.request.urlopen")
  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "staging"})
  def test_derive_vcf_ova_url_staging(self, mock_urlopen):
    """Verifies that _derive_vcf_ova_url constructs staging host from OFFLINE_DEPOT_ENV."""
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = (
        b'<html><a href="VCF-SDDC-Manager-Appliance-5.1.1.1234.ova">link</a></html>'
    )
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    target_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/us-central1-a/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
        labels={},
        label_fingerprint="",
    )

    url = self.validator._derive_vcf_ova_url(target_details)
    self.assertEqual(
        url,
        "https://offline-depot.us-central1.staging.smve-vcf.internal/PROD/COMP/SDDC_MANAGER_VCF/VCF-SDDC-Manager-Appliance-5.1.1.1234.ova",
    )

  @mock.patch("urllib.request.urlopen")
  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "autopush"})
  def test_derive_vcf_ova_url_autopush(self, mock_urlopen):
    """Verifies that _derive_vcf_ova_url constructs autopush host from OFFLINE_DEPOT_ENV."""
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = (
        b'<html><a href="VCF-SDDC-Manager-Appliance-5.1.1.1234.ova">link</a></html>'
    )
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    target_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/us-central1-a/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
        labels={},
        label_fingerprint="",
    )

    url = self.validator._derive_vcf_ova_url(target_details)
    self.assertEqual(
        url,
        "https://offline-depot.us-central1.autopush.smve-vcf.internal/PROD/COMP/SDDC_MANAGER_VCF/VCF-SDDC-Manager-Appliance-5.1.1.1234.ova",
    )

  @mock.patch("urllib.request.urlopen")
  def test_derive_vcf_ova_url_with_psc_ip(self, mock_urlopen):
    """Verifies that _derive_vcf_ova_url uses PSC IP in URL when provided."""
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = (
        b'<html><a href="VCF-SDDC-Manager-Appliance-5.1.1.1234.ova">link</a></html>'
    )
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    target_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/us-central1-a/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="us-central1-a",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
        labels={},
        label_fingerprint="",
    )

    url = self.validator._derive_vcf_ova_url(
        target_details, depot_host_or_ip="10.0.100.2"
    )
    self.assertEqual(
        url,
        "https://10.0.100.2/PROD/COMP/SDDC_MANAGER_VCF/VCF-SDDC-Manager-Appliance-5.1.1.1234.ova",
    )
    req = mock_urlopen.call_args[0][0]
    self.assertEqual(
        req.headers.get("Host"),
        "offline-depot.us-central1.selfmanagedvmwareengine.goog",
    )

  @mock.patch("vcf_deployer.validator.offline_depot_infra.OfflineDepotInfraManager")
  @mock.patch.object(validator.PreDeploymentValidator, "_derive_vcf_ova_url")
  @mock.patch("utils.network_utils.capture_ssl_thumbprint")
  @mock.patch("utils.network_utils.extract_vlan_cidr_and_routing")
  def test_validate_and_extract_with_custom_dns_server(
      self,
      mock_extract_vlan,
      mock_capture_thumbprint,
      mock_derive_url,
      mock_infra_mgr_cls,
  ):
    """Verifies validate_and_extract populates ctx.dns_server when supplied."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.side_effect = lambda inst: f"projects/p/zones/z/instances/{inst}"
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.100.0/29",
        dns_server="10.0.0.2",
    )
    self.mock_config.vcf_deployment_config = vcf_cfg
    self.mock_config.esxi_root_password_secret = "esxi-root"

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[
            models.SubnetworkInfo(
                subnetwork_uri="projects/p/regions/z/subnetworks/sub-1",
                vlan_id=0,
                network_uri="projects/p/global/networks/vpc-1",
                cidr="10.0.0.0/24",
            )
        ],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",
        "ComplexVCF_Admin_P@ssword123",
        "ComplexVCF_Local_P@ss123",
    ]
    mock_infra_mgr_cls.return_value.setup_offline_depot_infrastructure.return_value = {
        "psc_ip": "10.0.100.2",
        "fqdn": "offline-depot.z.selfmanagedvmwareengine.goog.",
        "subnet_uri": "projects/p/regions/z/subnetworks/sub-1",
    }
    self.mock_gcp.resolve_ip_source.return_value = "10.0.0.50"
    mock_derive_url.return_value = "https://10.0.100.2/vcf.ova"
    mock_extract_vlan.return_value = (
        100,
        "10.0.0.0/24",
        "255.255.255.0",
        "10.0.0.1",
    )
    mock_capture_thumbprint.return_value = "AA:BB:CC:DD"

    ctx = self.validator.validate_and_extract()
    self.assertEqual(ctx.dns_server, "10.0.0.2")

  @mock.patch("vcf_deployer.validator.offline_depot_infra.OfflineDepotInfraManager")
  @mock.patch.object(validator.PreDeploymentValidator, "_derive_vcf_ova_url")
  @mock.patch("utils.network_utils.capture_ssl_thumbprint")
  @mock.patch("utils.network_utils.extract_vlan_cidr_and_routing")
  def test_validate_and_extract_offline_depot_infra(
      self,
      mock_extract_vlan,
      mock_capture_thumbprint,
      mock_derive_url,
      mock_infra_mgr_cls,
  ):
    """Verifies validate_and_extract passes offline_depot_subnet_cidr to OfflineDepotInfraManager."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.side_effect = lambda inst: f"projects/p/zones/z/instances/{inst}"
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.100.0/29",
    )
    self.mock_config.vcf_deployment_config = vcf_cfg
    self.mock_config.esxi_root_password_secret = "esxi-root"

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[
            models.SubnetworkInfo(
                subnetwork_uri="projects/p/regions/z/subnetworks/sub-1",
                vlan_id=0,
                network_uri="projects/p/global/networks/vpc-1",
                cidr="10.0.0.0/24",
            )
        ],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",
        "ComplexVCF_Admin_P@ssword123",
        "ComplexVCF_Local_P@ss123",
    ]
    mock_infra_mgr_cls.return_value.setup_offline_depot_infrastructure.return_value = {
        "psc_ip": "10.0.100.2",
        "fqdn": "offline-depot.z.selfmanagedvmwareengine.goog.",
        "subnet_uri": "projects/p/regions/z/subnetworks/sub-1",
    }
    self.mock_gcp.resolve_ip_source.return_value = "10.0.0.50"
    mock_derive_url.return_value = "https://10.0.100.2/vcf.ova"
    mock_extract_vlan.return_value = (
        100,
        "10.0.0.0/24",
        "255.255.255.0",
        "10.0.0.1",
    )
    mock_capture_thumbprint.return_value = "AA:BB:CC:DD"

    self.validator.validate_and_extract()
    mock_infra_mgr_cls.assert_called_once_with(
        config=self.mock_config,
        gcp=self.mock_gcp,
        vpc_network="projects/p/global/networks/vpc-1",
        cidr="10.0.100.0/29",
    )

  @mock.patch("vcf_deployer.validator.offline_depot_infra.OfflineDepotInfraManager")
  @mock.patch.object(validator.PreDeploymentValidator, "_derive_vcf_ova_url")
  @mock.patch("utils.network_utils.capture_ssl_thumbprint")
  @mock.patch("utils.network_utils.extract_vlan_cidr_and_routing")
  def test_validate_and_extract_invalid_dns_server_raises_validation_error(
      self,
      mock_extract_vlan,
      mock_capture_thumbprint,
      mock_derive_url,
      mock_infra_mgr_cls,
  ):
    """Verifies validate_and_extract raises ValidationError for invalid IPv4 format in dns_server."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.side_effect = lambda inst: f"projects/p/zones/z/instances/{inst}"
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.100.0/29",
        dns_server="not-an-ip",
    )
    self.mock_config.vcf_deployment_config = vcf_cfg
    self.mock_config.esxi_root_password_secret = "esxi-root"

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[
            models.SubnetworkInfo(
                subnetwork_uri="projects/p/regions/z/subnetworks/sub-1",
                vlan_id=0,
                network_uri="projects/p/global/networks/vpc-1",
                cidr="10.0.0.0/24",
            )
        ],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",
        "ComplexVCF_Admin_P@ssword123",
        "ComplexVCF_Local_P@ss123",
    ]
    mock_infra_mgr_cls.return_value.setup_offline_depot_infrastructure.return_value = {
        "psc_ip": "10.0.100.2",
        "fqdn": "offline-depot.z.selfmanagedvmwareengine.goog.",
        "subnet_uri": "projects/p/regions/z/subnetworks/sub-1",
    }
    self.mock_gcp.resolve_ip_source.return_value = "10.0.0.50"
    mock_derive_url.return_value = "https://10.0.100.2/vcf.ova"
    mock_extract_vlan.return_value = (
        100,
        "10.0.0.0/24",
        "255.255.255.0",
        "10.0.0.1",
    )
    mock_capture_thumbprint.return_value = "AA:BB:CC:DD"

    with self.assertRaises(models.ValidationError) as ctx_err:
      self.validator.validate_and_extract()
    self.assertIn("Invalid dns_server 'not-an-ip'", str(ctx_err.exception))

  def test_validate_and_extract_overlapping_offline_depot_subnet_cidr_raises_validation_error(
      self,
  ):
    """Verifies validate_and_extract raises ValidationError when offline depot CIDR overlaps an existing subnet."""
    self.mock_config.gce_nodes = ["esxi-1"]
    self.mock_config.project = "p"
    self.mock_config.zone = "z"
    self.mock_config.get_full_node_path.side_effect = lambda inst: f"projects/p/zones/z/instances/{inst}"
    self.mock_config.get_full_secret_path.side_effect = lambda s: f"secrets/{s}"
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.0.0/29",
    )
    self.mock_config.vcf_deployment_config = vcf_cfg
    self.mock_config.esxi_root_password_secret = "esxi-root"

    mock_details = models.GCEInstanceDetails(
        instance_resource_string="projects/p/zones/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.5",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[
            models.SubnetworkInfo(
                subnetwork_uri="projects/p/regions/z/subnetworks/mgmt-subnet",
                vlan_id=0,
                network_uri="projects/p/global/networks/vpc-1",
                cidr="10.0.0.0/24",
            )
        ],
        tags=["mm-gcve-node"],
        tags_fingerprint="fp_tag",
        labels={"gcve-node": "true"},
        label_fingerprint="fp_label",
    )
    self.mock_gcp.get_instance_details.return_value = mock_details
    self.mock_gcp.get_secret_payload.side_effect = [
        "ValidESXiP@ss123!",
        "ComplexVCF_Admin_P@ssword123",
        "ComplexVCF_Local_P@ss123",
    ]

    with self.assertRaises(models.ValidationError) as ctx_err:
      self.validator.validate_and_extract()
    self.assertIn(
        "overlaps with or is already used by existing subnet",
        str(ctx_err.exception),
    )
    self.assertIn("projects/p/regions/z/subnetworks/mgmt-subnet", str(ctx_err.exception))


if __name__ == "__main__":
  unittest.main()

