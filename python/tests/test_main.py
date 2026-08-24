"""Unit tests for vcf_deployer/main.py module."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import constants
import models
from vcf_deployer import main as main_mod


class TestMain(unittest.TestCase):
  """Tests for master orchestrator entry point, retry mechanics, and config loading."""

  def test_retry_with_backoff_success_first_attempt(self):
    """Verifies immediate execution success without retrying."""
    mock_func = mock.MagicMock(return_value="success_result")
    res = main_mod.retry_with_backoff(mock_func, max_attempts=3)
    self.assertEqual(res, "success_result")
    mock_func.assert_called_once()

  def test_retry_with_backoff_non_retryable_error_aborts_immediately(self):
    """Verifies NonRetryableError and ValidationError abort immediately on attempt 1."""
    mock_func = mock.MagicMock(
        side_effect=models.ValidationError("Validation error")
    )
    with self.assertRaises(models.ValidationError):
      main_mod.retry_with_backoff(mock_func, max_attempts=3)
    self.assertEqual(mock_func.call_count, 1)

    mock_func2 = mock.MagicMock(
        side_effect=models.NonRetryableError("Terminal error")
    )
    with self.assertRaises(models.NonRetryableError):
      main_mod.retry_with_backoff(mock_func2, max_attempts=3)
    self.assertEqual(mock_func2.call_count, 1)

  @mock.patch("time.sleep")
  def test_retry_with_backoff_transient_error_retries_and_succeeds(
      self, mock_sleep
  ):
    """Verifies retrying with exponential backoff on transient errors."""
    mock_func = mock.MagicMock(
        side_effect=[
            models.RetryableError("Transient network glitch"),
            models.RetryableError("Timeout"),
            "success_result",
        ]
    )
    res = main_mod.retry_with_backoff(mock_func, max_attempts=3, base_delay=0.1)
    self.assertEqual(res, "success_result")
    self.assertEqual(mock_func.call_count, 3)
    self.assertEqual(mock_sleep.call_count, 2)

  @mock.patch("time.sleep")
  def test_retry_with_backoff_exhaustion(self, mock_sleep):
    """Verifies RetryableError raised after exhausting all retry attempts."""
    mock_func = mock.MagicMock(
        side_effect=models.RetryableError("Persistent fault")
    )
    with self.assertRaises(models.RetryableError) as ctx:
      main_mod.retry_with_backoff(mock_func, max_attempts=3, base_delay=0.1)
    self.assertIn("Exhausted max attempts (3)", str(ctx.exception))
    self.assertEqual(mock_func.call_count, 3)

  def test_load_config_valid_file(self):
    """Verifies loading and parsing of a valid config.json document."""
    valid_data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": ["esxi-1"],
        "esxi_root_password_secret": "esxi-root",
        "vcf_deployment_config": {
            "target_gce_node": "esxi-1",
            "offline_depot_subnet_cidr": "10.0.100.0/29",
            "vcf_appliance_root_password_secret": "vcf-root",
            "vcf_appliance_local_user_password_secret": "vcf-local",
            "vcf_installer_fqdn": "sddc-manager.lab.local",
            "vcf_installer_ip_source": {"reserved_address": "vcf-ip"},
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(valid_data, tf)
      temp_path = tf.name

    try:
      config = main_mod.load_config(temp_path)
      self.assertIsInstance(config, models.DeployerConfig)
      self.assertEqual(len(config.gce_nodes), 1)
      self.assertIsNotNone(config.vcf_deployment_config)
      self.assertEqual(
          config.vcf_deployment_config.vcf_installer_fqdn,
          "sddc-manager.lab.local",
      )
    finally:
      os.remove(temp_path)

  def test_load_config_with_prefix_dict(self):
    """Verifies loading config with gce_nodes as dict containing prefix."""
    data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": {"prefix": "esxi-"},
        "esxi_root_password_secret": "esxi-root",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(data, tf)
      temp_path = tf.name

    try:
      config = main_mod.load_config(temp_path)
      self.assertEqual(config.gce_nodes, {"prefix": "esxi-"})
    finally:
      os.remove(temp_path)

  def test_load_config_with_subnet_dict(self):
    """Verifies loading config with gce_nodes as dict containing subnet."""
    data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": {"subnet": "my-subnet"},
        "esxi_root_password_secret": "esxi-root",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(data, tf)
      temp_path = tf.name

    try:
      config = main_mod.load_config(temp_path)
      self.assertEqual(config.gce_nodes, {"subnet": "my-subnet"})
    finally:
      os.remove(temp_path)

  def test_load_config_with_both_prefix_and_subnet(self):
    """Verifies loading config with gce_nodes dict containing both prefix and subnet."""
    data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": {"prefix": "esxi-", "subnet": "my-subnet"},
        "esxi_root_password_secret": "esxi-root",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(data, tf)
      temp_path = tf.name

    try:
      config = main_mod.load_config(temp_path)
      self.assertEqual(
          config.gce_nodes, {"prefix": "esxi-", "subnet": "my-subnet"}
      )
    finally:
      os.remove(temp_path)

  def test_load_config_with_empty_gce_nodes_dict_raises_validation_error(self):
    """Verifies ValidationError when gce_nodes dict contains neither prefix nor subnet."""
    data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": {"invalid": "key"},
        "esxi_root_password_secret": "esxi-root",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(data, tf)
      temp_path = tf.name

    try:
      with self.assertRaises(models.ValidationError) as ctx:
        main_mod.load_config(temp_path)
      self.assertIn("must contain 'prefix' and/or 'subnet'", str(ctx.exception))
    finally:
      os.remove(temp_path)

  def test_load_config_missing_file_raises_validation_error(self):
    """Verifies ValidationError when config file does not exist."""
    with self.assertRaises(models.ValidationError) as ctx:
      main_mod.load_config("/non_existent_path_12345.json")
    self.assertIn(
        "Failed to read or decode JSON configuration file", str(ctx.exception)
    )

  def test_load_config_missing_mandatory_keys_raises_validation_error(self):
    """Verifies ValidationError when mandatory top-level key is missing."""
    invalid_data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": [],  # empty
        "esxi_root_password_secret": "esxi-root",
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(invalid_data, tf)
      temp_path = tf.name

    try:
      with self.assertRaises(models.ValidationError) as ctx:
        main_mod.load_config(temp_path)
      self.assertIn(
          "Mandatory configuration key 'gce_nodes'",
          str(ctx.exception),
      )
    finally:
      os.remove(temp_path)

  @mock.patch("vcf_deployer.main.load_config")
  @mock.patch("vcf_deployer.main.gcp_client.GCPClient")
  @mock.patch("vcf_deployer.main.validator.PreDeploymentValidator")
  @mock.patch("vcf_deployer.main.password_resetter.PasswordResetter")
  def test_run_pipeline_success_no_vcf_config(
      self, mock_pwd_mgr, mock_val_cls, mock_gcp_cls, mock_load_cfg
  ):
    """Verifies pipeline execution with exit code 0 when VCF config is omitted."""
    mock_cfg = models.DeployerConfig(
        project="p",
        zone="z",
        gce_nodes=["esxi-1"],
        esxi_root_password_secret="esxi-root",
        vcf_deployment_config=None,
    )
    mock_load_cfg.return_value = mock_cfg

    mock_val_inst = mock.MagicMock()
    mock_val_cls.return_value = mock_val_inst
    mock_ctx = models.ValidationContext(
        esxi_nodes={},
        new_esxi_root_password="NewP@ssword123!",
    )
    mock_val_inst.validate_and_extract.return_value = mock_ctx

    exit_code = main_mod.run_pipeline("dummy_config.json")
    self.assertEqual(exit_code, 0)
    mock_gcp_cls.assert_called_once()
    mock_pwd_mgr.return_value.reset_esxi_inventory_passwords.assert_called_once()

  @mock.patch("vcf_deployer.main.load_config")
  def test_run_pipeline_validation_error_returns_exit_code_2(
      self, mock_load_cfg
  ):
    """Verifies exit code 2 when pipeline aborts due to ValidationError."""
    mock_load_cfg.side_effect = models.ValidationError(
        "Missing mandatory config key"
    )
    exit_code = main_mod.run_pipeline("invalid_config.json")
    self.assertEqual(exit_code, 2)

  @mock.patch("vcf_deployer.main.load_config")
  def test_run_pipeline_deployer_error_returns_exit_code_3(self, mock_load_cfg):
    """Verifies exit code 3 when pipeline aborts due to DeployerError / Operational failure."""
    mock_load_cfg.side_effect = models.DeployerError("Operational fault")
    exit_code = main_mod.run_pipeline("invalid_config.json")
    self.assertEqual(exit_code, 3)

  @mock.patch("vcf_deployer.main.load_config")
  @mock.patch("vcf_deployer.main.gcp_client.GCPClient")
  @mock.patch("vcf_deployer.main.validator.PreDeploymentValidator")
  @mock.patch("vcf_deployer.main.esxi_client.ESXiClient")
  @mock.patch("vcf_deployer.main.network_setup.NetworkManager")
  @mock.patch("vcf_deployer.main.vsan_setup.VSANManager")
  @mock.patch("vcf_deployer.main.vm_deployer.VMDeployer")
  @mock.patch("vcf_deployer.main.password_resetter.PasswordResetter")
  def test_run_pipeline_full_vcf_flow(
      self,
      mock_pwd_mgr,
      mock_vm_mgr,
      mock_vsan_mgr,
      mock_net_mgr,
      mock_esxi_cli,
      mock_val_cls,
      mock_gcp_cls,
      mock_load_cfg,
  ):
    """Verifies full Phase 1-3 pipeline execution with VCF deployment profile."""
    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node="esxi-1",
        vcf_appliance_root_password_secret="vcf-root",
        vcf_appliance_local_user_password_secret="vcf-local",
        vcf_installer_fqdn="sddc-manager.lab.local",
        vcf_installer_ip_source={"forwarding_rule": "fr-1"},
        offline_depot_subnet_cidr="10.0.100.0/29",
    )
    mock_cfg = models.DeployerConfig(
        project="p",
        zone="z",
        gce_nodes=["esxi-1"],
        esxi_root_password_secret="esxi-root",
        vcf_deployment_config=vcf_cfg,
    )
    mock_load_cfg.return_value = mock_cfg

    mock_ctx = models.ValidationContext(
        esxi_nodes={},
        new_esxi_root_password="NewESXiRoot123!",
        target_esxi_ip="10.0.0.5",
        vcf_installer_ip="10.0.0.50",
        vcf_installer_ova_url="https://depot/vcf.ova",
        vlan_id=100,
        port_group_name="vlan-100-a1b2",
        sddc_manager_netmask="255.255.255.0",
        sddc_manager_gateway="10.0.0.1",
        vcf_vm_name="sddc-manager",
        vcf_domain="lab.local",
        vcf_searchpath="lab.local",
        ssl_thumbprint="AA:BB:CC",
        vcf_appliance_root_password="VCFRootP@ssword123!",
        vcf_appliance_local_password="VCFLocalP@ssword123!",
    )
    mock_val_inst = mock.MagicMock()
    mock_val_inst.validate_and_extract.return_value = mock_ctx
    mock_val_cls.return_value = mock_val_inst

    mock_net_mgr.return_value.configure_networking.return_value = (
        "vlan-100-a1b2"
    )
    mock_vm_mgr.return_value.deploy_ova.return_value = mock.MagicMock()

    exit_code = main_mod.run_pipeline("config.json")
    self.assertEqual(exit_code, 0)
    mock_gcp_cls.assert_called_once()
    mock_esxi_cli.assert_called_once_with(
        host_ip="10.0.0.5",
        user="root",
        password=constants.PasswordResetDefaults.DEFAULT_INITIAL_SECRET,
        fallback_password="NewESXiRoot123!",
    )
    mock_net_mgr.return_value.configure_networking.assert_called_once()
    mock_vsan_mgr.return_value.setup_vsan.assert_called_once()
    mock_vm_mgr.return_value.deploy_ova.assert_called_once()
    mock_vm_mgr.return_value.configure_ovf_environment.assert_called_once()
    mock_vm_mgr.return_value.power_on_and_wait_for_ip.assert_called_once()
    mock_pwd_mgr.return_value.reset_esxi_inventory_passwords.assert_called_once()

  @mock.patch("vcf_deployer.main.load_config")
  def test_run_pipeline_unhandled_exception_returns_exit_code_1(
      self, mock_load_cfg
  ):
    """Verifies exit code 1 when an unexpected unhandled exception occurs."""
    mock_load_cfg.side_effect = RuntimeError("Unexpected OS crash")
    exit_code = main_mod.run_pipeline("invalid_config.json")
    self.assertEqual(exit_code, 1)

  def test_load_config_missing_vcf_fields_raises_validation_error(self):
    """Verifies ValidationError when vcf_deployment_config lacks required fields."""
    invalid_vcf_data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": ["esxi-1"],
        "esxi_root_password_secret": "esxi-root",
        "vcf_deployment_config": {
            "target_gce_node": "esxi-1",
            # missing required fields
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(invalid_vcf_data, tf)
      temp_path = tf.name

    try:
      with self.assertRaises(models.ValidationError) as ctx:
        main_mod.load_config(temp_path)
      self.assertIn("Mandatory VCF configuration field", str(ctx.exception))
    finally:
      os.remove(temp_path)

  def test_load_config_invalid_cidr_raises_validation_error(self):
    """Verifies ValidationError when offline_depot_subnet_cidr prefix > 29."""
    invalid_cidr_data = {
        "project": "p",
        "zone": "z",
        "gce_nodes": ["esxi-1"],
        "esxi_root_password_secret": "esxi-root",
        "vcf_deployment_config": {
            "target_gce_node": "esxi-1",
            "offline_depot_subnet_cidr": "10.0.100.0/30",
            "vcf_appliance_root_password_secret": "vcf-root",
            "vcf_appliance_local_user_password_secret": "vcf-local",
            "vcf_installer_fqdn": "sddc-manager.lab.local",
            "vcf_installer_ip_source": {"reserved_address": "vcf-ip"},
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
      json.dump(invalid_cidr_data, tf)
      temp_path = tf.name

    try:
      with self.assertRaises(models.ValidationError) as ctx:
        main_mod.load_config(temp_path)
      self.assertIn("is too small", str(ctx.exception))
    finally:
      os.remove(temp_path)

  @mock.patch("sys.exit")
  @mock.patch("vcf_deployer.main.run_pipeline")
  def test_main_cli_entrypoint(self, mock_run_pipe, mock_sys_exit):
    """Verifies main() CLI parser passing --config argument to run_pipeline."""
    mock_run_pipe.return_value = 0
    with mock.patch.object(
        sys, "argv", ["main.py", "--config", "custom_config.json"]
    ):
      main_mod.main()
    mock_run_pipe.assert_called_once_with(config_file_path="custom_config.json")
    mock_sys_exit.assert_called_once_with(0)


if __name__ == "__main__":
  unittest.main()
