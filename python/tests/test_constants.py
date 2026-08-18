"""Unit tests for constants.py module."""

import unittest
from unittest import mock

import constants


class TestConstants(unittest.TestCase):
  """Tests for constants, enums, and configuration keys."""

  def test_exit_codes(self):
    """Verifies defined exit codes and their numerical values."""
    self.assertEqual(int(constants.ExitCode.SUCCESS), 0)
    self.assertEqual(int(constants.ExitCode.UNHANDLED_ERROR), 1)
    self.assertEqual(int(constants.ExitCode.VALIDATION_ERROR), 2)
    self.assertEqual(int(constants.ExitCode.DEPLOYER_ERROR), 3)

  def test_config_keys_structure(self):
    """Verifies top-level configuration keys and mandatory subset."""
    self.assertEqual(constants.ConfigKeys.PROJECT, "project")
    self.assertEqual(constants.ConfigKeys.ZONE, "zone")
    self.assertEqual(constants.ConfigKeys.GCE_INSTANCES, "gce_instances")
    self.assertEqual(
        constants.ConfigKeys.ESXI_ROOT_PASSWORD_SECRET,
        "esxi_root_password_secret",
    )
    self.assertEqual(constants.ConfigKeys.PREFIX, "prefix")
    self.assertEqual(constants.ConfigKeys.SUBNET, "subnet")
    self.assertEqual(
        constants.ConfigKeys.VCF_DEPLOYMENT_CONFIG, "vcf_deployment_config"
    )

    for key in (
        constants.ConfigKeys.PROJECT,
        constants.ConfigKeys.ZONE,
        constants.ConfigKeys.GCE_INSTANCES,
        constants.ConfigKeys.ESXI_ROOT_PASSWORD_SECRET,
    ):
      self.assertIn(key, constants.ConfigKeys.REQUIRED_KEYS)

  def test_vcf_config_keys_structure(self):
    """Verifies VCF deployment configuration keys and mandatory subset."""
    self.assertEqual(
        constants.VCFConfigKeys.TARGET_GCE_INSTANCE, "target_gce_instance"
    )
    self.assertEqual(
        constants.VCFConfigKeys.VCF_APPLIANCE_ROOT_PASSWORD_SECRET,
        "vcf_appliance_root_password_secret",
    )
    self.assertEqual(
        constants.VCFConfigKeys.VCF_APPLIANCE_LOCAL_USER_PASSWORD_SECRET,
        "vcf_appliance_local_user_password_secret",
    )
    self.assertEqual(
        constants.VCFConfigKeys.VCF_INSTALLER_FQDN, "vcf_installer_fqdn"
    )
    self.assertEqual(
        constants.VCFConfigKeys.VCF_INSTALLER_IP_SOURCE,
        "vcf_installer_ip_source",
    )

    for key in (
        constants.VCFConfigKeys.TARGET_GCE_INSTANCE,
        constants.VCFConfigKeys.VCF_APPLIANCE_ROOT_PASSWORD_SECRET,
        constants.VCFConfigKeys.VCF_APPLIANCE_LOCAL_USER_PASSWORD_SECRET,
        constants.VCFConfigKeys.VCF_INSTALLER_FQDN,
        constants.VCFConfigKeys.VCF_INSTALLER_IP_SOURCE,
    ):
      self.assertIn(key, constants.VCFConfigKeys.REQUIRED_KEYS)

  def test_defaults(self):
    """Verifies retry and deployment operational defaults."""
    self.assertEqual(constants.RetryDefaults.MAX_ATTEMPTS, 5)
    self.assertEqual(constants.RetryDefaults.BASE_DELAY, 2.0)
    self.assertEqual(constants.RetryDefaults.MAX_DELAY, 60.0)

    self.assertEqual(constants.DeployerDefaults.LOGGER_NAME, "vcf_deployer")
    self.assertEqual(constants.DeployerDefaults.DEFAULT_CONFIG_FILE, "config.json")
    self.assertEqual(constants.DeployerDefaults.VALIDATION_MAX_ATTEMPTS, 3)
    self.assertEqual(
        constants.DeployerDefaults.POWER_ON_POLL_INTERVAL_SECONDS, 10
    )
    self.assertEqual(constants.DeployerDefaults.POWER_ON_TIMEOUT_SECONDS, 600)

  def test_networking_defaults(self):
    """Verifies networking ports, metadata server, and timeouts."""
    self.assertEqual(constants.NetworkingDefaults.DEFAULT_VSWITCH, "vSwitch0")
    self.assertEqual(constants.NetworkingDefaults.HTTPS_PORT, 443)
    self.assertEqual(constants.NetworkingDefaults.SSH_PORT, 22)
    self.assertEqual(
        constants.NetworkingDefaults.DEFAULT_METADATA_SERVER, "169.254.169.254"
    )
    self.assertEqual(constants.NetworkingDefaults.SSL_TIMEOUT_SECONDS, 10)
    self.assertEqual(constants.NetworkingDefaults.SSH_TIMEOUT_SECONDS, 300)
    self.assertEqual(constants.NetworkingDefaults.HTTP_TIMEOUT_SECONDS, 60)
    self.assertEqual(constants.NetworkingDefaults.MAX_FQDN_LENGTH, 255)
    self.assertIn(
        "{vlan_id}", constants.NetworkingDefaults.PORT_GROUP_PATTERN
    )

  def test_gcp_client_defaults(self):
    """Verifies GCP client wrapper default constants."""
    self.assertEqual(
        constants.GCPClientDefaults.COMPUTE_API_VERSION_ENV,
        "COMPUTE_API_VERSION",
    )
    self.assertEqual(
        constants.GCPClientDefaults.DEFAULT_COMPUTE_API_VERSION, "v1"
    )

  def test_validation_rules(self):
    """Verifies validation tags, labels, and password policy constants."""
    self.assertEqual(
        constants.ValidationRules.REQUIRED_GCE_TAGS, ("mm-gcve-node",)
    )
    self.assertEqual(
        constants.ValidationRules.REQUIRED_GCE_LABELS, {"gcve-node": "true"}
    )
    self.assertEqual(
        constants.ValidationRules.OFFLINE_DEPOT_ENV_VAR, "OFFLINE_DEPOT_ENV"
    )
    self.assertEqual(
        constants.ValidationRules.DEFAULT_OFFLINE_DEPOT_ENV, "prod"
    )
    self.assertEqual(constants.ValidationRules.MAX_INSPECTION_WORKERS, 10)
    self.assertEqual(constants.ValidationRules.MAX_TAG_GOVERNANCE_WORKERS, 10)
    self.assertIn(
        "{region}", constants.ValidationRules.DEPOT_HOST_TEMPLATE
    )
    self.assertEqual(
        constants.ValidationRules.DEPOT_HOST_TEMPLATES["prod"],
        "offline-depot.{region}.selfmanagedvmwareengine.goog",
    )
    self.assertEqual(
        constants.ValidationRules.DEPOT_HOST_TEMPLATES["staging"],
        "offline-depot.{region}.staging.smve-vcf.internal",
    )
    self.assertEqual(
        constants.ValidationRules.DEPOT_HOST_TEMPLATES["autopush"],
        "offline-depot.{region}.autopush.smve-vcf.internal",
    )
    self.assertEqual(
        constants.ValidationRules.DEPOT_INDEX_PATH,
        "/PROD/COMP/SDDC_MANAGER_VCF/",
    )
    self.assertEqual(
        constants.ValidationRules.ESXI_ROOT_PASSWORD_MIN_LEN, 7
    )
    self.assertEqual(
        constants.ValidationRules.ESXI_ROOT_PASSWORD_MAX_LEN, 39
    )
    self.assertEqual(
        constants.ValidationRules.VCF_ROOT_PASSWORD_MIN_LEN, 15
    )
    self.assertEqual(
        constants.ValidationRules.VCF_LOCAL_PASSWORD_MIN_LEN, 12
    )

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "staging"})
  def test_get_depot_host_template_from_offline_depot_env(self):
    """Verifies get_depot_host_template reads OFFLINE_DEPOT_ENV."""
    self.assertEqual(
        constants.ValidationRules.get_depot_host_template(),
        "offline-depot.{region}.staging.smve-vcf.internal",
    )

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "autopush"})
  def test_get_depot_host_template_from_autopush_env(self):
    """Verifies get_depot_host_template reads OFFLINE_DEPOT_ENV=autopush."""
    self.assertEqual(
        constants.ValidationRules.get_depot_host_template(),
        "offline-depot.{region}.autopush.smve-vcf.internal",
    )

  @mock.patch.dict("os.environ", {}, clear=True)
  def test_get_depot_host_template_default_prod(self):
    """Verifies get_depot_host_template defaults to prod when env is unset."""
    self.assertEqual(
        constants.ValidationRules.get_depot_host_template(),
        "offline-depot.{region}.selfmanagedvmwareengine.goog",
    )

  def test_vsan_constants(self):
    """Verifies vSAN storage pool strings, VDQ command, and default policies."""
    self.assertEqual(
        constants.VSANConstants.ELIGIBLE_FOR_STORAGE_POOL,
        "eligible for use by storage pool",
    )
    self.assertEqual(
        constants.VSANConstants.IN_USE_FOR_STORAGE_POOL,
        "in-use for storage pool",
    )
    self.assertEqual(constants.VSANConstants.VDQ_COMMAND, "/sbin/vdq -q")
    self.assertEqual(len(constants.VSANConstants.DEFAULT_VSAN_POLICIES), 5)

  def test_vm_deployer_defaults(self):
    """Verifies VM deployer datastore, guestinfo keys, and timeouts."""
    self.assertEqual(
        constants.VMDeployerDefaults.DEFAULT_DATASTORE_NAME, "vsanDatastore"
    )
    self.assertEqual(
        constants.VMDeployerDefaults.HTTP_USER_AGENT, "VCFDeployer/1.0"
    )
    self.assertEqual(
        constants.VMDeployerDefaults.GUESTINFO_OVF_ENV, "guestinfo.ovfEnv"
    )
    self.assertEqual(
        constants.VMDeployerDefaults.GUESTINFO_OVF_ENV_LEN,
        "guestinfo.ovfEnv/len",
    )
    self.assertEqual(
        constants.VMDeployerDefaults.NFC_LEASE_TIMEOUT_SECONDS, 120
    )
    self.assertEqual(
        constants.VMDeployerDefaults.NFC_LEASE_POLL_INTERVAL_SECONDS, 2
    )
    self.assertEqual(
        constants.VMDeployerDefaults.DISK_PROVISIONING_THIN, "thin"
    )
    self.assertEqual(constants.VMDeployerDefaults.TASK_TIMEOUT_SECONDS, 900)

  def test_ovf_property_keys(self):
    """Verifies OVF property key constants."""
    self.assertEqual(constants.OVFPropertyKeys.ROOT_PASSWORD, "ROOT_PASSWORD")
    self.assertEqual(
        constants.OVFPropertyKeys.LOCAL_USER_PASSWORD, "LOCAL_USER_PASSWORD"
    )
    self.assertEqual(constants.OVFPropertyKeys.VAMI_HOSTNAME, "vami.hostname")
    self.assertEqual(constants.OVFPropertyKeys.GUESTINFO_NTP, "guestinfo.ntp")
    self.assertEqual(
        constants.OVFPropertyKeys.VAMI_IP0_SDDC_MANAGER, "vami.ip0.SDDC-Manager"
    )

  def test_password_reset_defaults(self):
    """Verifies password reset defaults."""
    self.assertEqual(
        constants.PasswordResetDefaults.DEFAULT_INITIAL_SECRET,
        "Google1!Google1!",
    )
    self.assertEqual(constants.PasswordResetDefaults.DEFAULT_BATCH_SIZE, 10)
    self.assertEqual(constants.PasswordResetDefaults.DEFAULT_ROOT_USER, "root")


if __name__ == "__main__":
  unittest.main()
