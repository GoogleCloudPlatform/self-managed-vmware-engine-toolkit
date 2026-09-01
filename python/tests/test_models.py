"""Unit tests for models.py module."""

import unittest

import models


class TestModels(unittest.TestCase):
  """Tests for data models, configuration schemas, and exception hierarchy."""

  def test_exception_inheritance(self):
    """Verifies exception hierarchy and details dictionary handling."""
    err = models.DeployerError("Base operational error", details={"code": 500})
    self.assertIsInstance(err, Exception)
    self.assertEqual(err.details.get("code"), 500)

    val_err = models.ValidationError("Validation failed")
    self.assertIsInstance(val_err, models.DeployerError)

    ret_err = models.RetryableError("Transient error")
    self.assertIsInstance(ret_err, models.DeployerError)

    non_ret_err = models.NonRetryableError("Terminal error")
    self.assertIsInstance(non_ret_err, models.DeployerError)

  def test_vcf_deployment_config_instantiation(self):
    """Verifies VCFDeploymentConfig dataclass field assignment."""
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source="vcf-ip",
        offline_depot_subnet_cidr="10.0.100.0/29",
    )
    self.assertEqual(vcf_cfg.target_gce_node, "esxi-1")
    self.assertEqual(vcf_cfg.vcf_installer_fqdn, "sddc-manager.lab.local")
    self.assertEqual(vcf_cfg.vcf_installer_ip_source, "vcf-ip")
    self.assertEqual(vcf_cfg.offline_depot_subnet_cidr, "10.0.100.0/29")
    self.assertIsNone(vcf_cfg.dns_server)

    vcf_cfg_with_dns = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source="vcf-ip",
        offline_depot_subnet_cidr="10.0.100.0/29",
        dns_server="10.0.0.2",
    )
    self.assertEqual(vcf_cfg_with_dns.dns_server, "10.0.0.2")

  def test_deployer_config_instantiation_and_helpers(self):
    """Verifies master DeployerConfig dataclass, region property, and path helpers."""
    cfg = models.DeployerConfig(
        project="p-123",
        zone="us-central1-a",
        gce_nodes=["esxi-1"],
        esxi_root_password_secret="esxi-root",
    )
    self.assertEqual(len(cfg.gce_nodes), 1)
    self.assertEqual(cfg.region, "us-central1")
    self.assertIsNone(cfg.vcf_deployment_config)

    # Path helper tests
    self.assertEqual(
        cfg.get_full_node_path("esxi-1"),
        "projects/p-123/zones/us-central1-a/instances/esxi-1",
    )
    self.assertEqual(
        cfg.get_full_node_path("projects/other/zones/z/instances/esxi-2"),
        "projects/other/zones/z/instances/esxi-2",
    )
    self.assertEqual(
        cfg.get_full_secret_path("my-secret"),
        "projects/p-123/secrets/my-secret/versions/latest",
    )
    self.assertEqual(
        cfg.get_full_secret_path("projects/p-123/secrets/custom/versions/1"),
        "projects/p-123/secrets/custom/versions/1",
    )

  def test_validation_context_immutability(self):
    """Verifies ValidationContext frozen dataclass immutability."""
    ctx = models.ValidationContext(
        esxi_nodes={},
        new_esxi_root_password="NewP@ssword123!",
        target_esxi_ip="10.0.0.5",
        vcf_installer_ip="10.0.0.50",
    )
    self.assertEqual(ctx.target_esxi_ip, "10.0.0.5")
    self.assertEqual(ctx.vcf_installer_ip, "10.0.0.50")
    self.assertEqual(ctx.esxi_nodes, {})
    # Dataclass is frozen; setting attribute should raise FrozenInstanceError
    with self.assertRaises(AttributeError):
      ctx.target_esxi_ip = "10.0.0.6"  # type: ignore


if __name__ == "__main__":
  unittest.main()
