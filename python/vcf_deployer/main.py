"""Master Orchestrator entry point for VCF Deployment Automation.

Runs directly on customer Jumpboxes to execute automated VCF Installer
deployment, ESXi networking and vSAN ESA initialization, streaming OVA
deployment, vCenter-less OVF bootstrapping, and inventory root password
rotation. Implements comprehensive error classification and retry mechanics
utilizing exponential backoff with random jitter.
"""

import argparse
import json
import logging
import random
import re
import sys
import time
from typing import Any, Callable

from clients import esxi_client
from clients import gcp_client
import constants
import models
from utils import logger as logger_mod
from utils import network_utils
from vcf_deployer import network_setup
from vcf_deployer import password_resetter
from vcf_deployer import validator
from vcf_deployer import vm_deployer
from vcf_deployer import vsan_setup

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_attempts: int = constants.RetryDefaults.MAX_ATTEMPTS,
    base_delay: float = constants.RetryDefaults.BASE_DELAY,
    max_delay: float = constants.RetryDefaults.MAX_DELAY,
    **kwargs: Any,
) -> Any:
  """Executes target function utilizing exponential backoff with random jitter.

  Differentiates between models.RetryableError (transient network faults,
  HTTP 429, 500, 503, and socket timeouts) and models.NonRetryableError /
  models.ValidationError (HTTP 400, 401, 403, 404, or configuration errors).

  Args:
      func: Callable function or method to execute within retry boundary.
      *args: Positional arguments to forward to func.
      max_attempts: Maximum evaluation iterations before failing open (max 5).
      base_delay: Initial waiting multiplier in seconds (default 2.0s).
      max_delay: Cap on maximum sleep duration per iteration (default 60.0s).
      **kwargs: Keyword arguments to forward to func.

  Returns:
      Result output returned by func upon successful execution.

  Raises:
      models.NonRetryableError: Immediately without retry on terminal faults.
      models.ValidationError: Immediately without retry on Phase 1 verify fail.
      models.RetryableError: If transient operational faults persist at max.
  """
  func_name = getattr(func, "__name__", str(func))
  for attempt in range(1, max_attempts + 1):
    try:
      return func(*args, **kwargs)
    except (
        models.NonRetryableError,
        models.ValidationError,
    ) as fatal_exc:
      logger.error(
          "Terminal non-retryable exception encountered in '%s' on attempt"
          " %d/%d: %s",
          func_name,
          attempt,
          max_attempts,
          fatal_exc,
      )
      raise
    except (models.RetryableError, Exception) as transient_exc:  # pylint: disable=broad-exception-caught
      if attempt == max_attempts:
        logger.critical(
            "Exhausted all %d retry attempts for '%s'. Final exception: %s",
            max_attempts,
            func_name,
            transient_exc,
        )
        raise models.RetryableError(
            f"Exhausted max attempts ({max_attempts}) for '{func_name}':"
            f" {transient_exc}"
        ) from transient_exc

      # Exponential backoff: base_delay * 2^(attempt - 1) + random jitter
      delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
      jitter = random.uniform(
          constants.RetryDefaults.JITTER_MIN,
          constants.RetryDefaults.JITTER_MAX,
      )
      wait_time = round(delay + jitter, 2)

      logger.warning(
          "Transient fault in '%s' on attempt %d/%d: %s. Retrying with backoff"
          " and jitter in %.2fs...",
          func_name,
          attempt,
          max_attempts,
          transient_exc,
          wait_time,
      )
      time.sleep(wait_time)


def load_config(config_file_path: str) -> models.DeployerConfig:
  """Parses and verifies structural integrity of target config.json document.

  Args:
      config_file_path: File system path pointing to master JSON profile.

  Returns:
      Structured models.DeployerConfig memory dataclass instance.

  Raises:
      models.ValidationError: If JSON formatting is invalid or required keys
      are missing.
  """
  logger.info(
      "Loading and parsing deployment configuration from '%s'...",
      config_file_path,
  )
  try:
    with open(config_file_path, "r", encoding="utf-8") as file:
      content = file.read()
      # Strip JS/JSONC comments (// ... and /* ... */)
      content = re.sub(r"//.*", "", content)
      content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
      data = json.loads(content)
  except Exception as exc:
    raise models.ValidationError(
        "Failed to read or decode JSON configuration file at"
        f" '{config_file_path}': {exc}"
    )

  for key in constants.ConfigKeys.REQUIRED_KEYS:
    if (
        key not in data
        or data[key] is None
        or data[key] == ""
        or data[key] == []
        or data[key] == {}
    ):
      raise models.ValidationError(
          f"Mandatory configuration key '{key}' is missing or empty in profile."
      )

  gce_node_input = data[constants.ConfigKeys.GCE_NODES]
  if isinstance(gce_node_input, dict):
    has_prefix = constants.ConfigKeys.PREFIX in gce_node_input and bool(
        gce_node_input[constants.ConfigKeys.PREFIX]
    )
    has_subnet = constants.ConfigKeys.SUBNET in gce_node_input and bool(
        gce_node_input[constants.ConfigKeys.SUBNET]
    )
    if not (has_prefix or has_subnet):
      raise models.ValidationError(
          f"'{constants.ConfigKeys.GCE_NODES}' dictionary must contain"
          f" '{constants.ConfigKeys.PREFIX}' and/or"
          f" '{constants.ConfigKeys.SUBNET}' key with non-empty values."
      )
  elif isinstance(gce_node_input, list):
    if not gce_node_input:
      raise models.ValidationError(
          f"Mandatory configuration key '{constants.ConfigKeys.GCE_NODES}'"
          " is missing or empty in profile."
      )
  elif not isinstance(gce_node_input, str):
    raise models.ValidationError(
        f"Invalid {constants.ConfigKeys.GCE_NODES}: must be a list of"
        " node names or a dictionary containing"
        f" '{constants.ConfigKeys.PREFIX}' and/or"
        f" '{constants.ConfigKeys.SUBNET}'."
    )

  vcf_cfg = None
  if (
      constants.ConfigKeys.VCF_DEPLOYMENT_CONFIG in data
      and data[constants.ConfigKeys.VCF_DEPLOYMENT_CONFIG]
  ):
    vcf_data = data[constants.ConfigKeys.VCF_DEPLOYMENT_CONFIG]
    for vkey in constants.VCFConfigKeys.REQUIRED_KEYS:
      if vkey not in vcf_data or not vcf_data[vkey]:
        raise models.ValidationError(
            f"Mandatory VCF configuration field '{vkey}' is missing or empty!"
        )

    cidr = str(vcf_data[constants.VCFConfigKeys.OFFLINE_DEPOT_SUBNET_CIDR]).strip()
    network_utils.validate_subnet_cidr_size(cidr)

    vcf_cfg = models.VCFDeploymentConfig(
        target_gce_node=vcf_data[
            constants.VCFConfigKeys.TARGET_GCE_NODE
        ],
        vcf_appliance_root_password_secret=vcf_data[
            constants.VCFConfigKeys.VCF_APPLIANCE_ROOT_PASSWORD_SECRET
        ],
        vcf_appliance_local_user=(
            vcf_data.get(constants.VCFConfigKeys.VCF_APPLIANCE_LOCAL_USER)
            or "vcf"
        ),
        vcf_appliance_local_user_password_secret=vcf_data[
            constants.VCFConfigKeys.VCF_APPLIANCE_LOCAL_USER_PASSWORD_SECRET
        ],
        vcf_installer_fqdn=str(
            vcf_data[constants.VCFConfigKeys.VCF_INSTALLER_FQDN]
        ).strip().rstrip("."),
        vcf_installer_ip_source=vcf_data[
            constants.VCFConfigKeys.VCF_INSTALLER_IP_SOURCE
        ],
        offline_depot_subnet_cidr=cidr,
        dns_server=vcf_data.get(constants.VCFConfigKeys.DNS_SERVER),
    )

  config = models.DeployerConfig(
      project=data[constants.ConfigKeys.PROJECT],
      zone=data[constants.ConfigKeys.ZONE],
      gce_nodes=data[constants.ConfigKeys.GCE_NODES],
      esxi_root_password_secret=data[
          constants.ConfigKeys.ESXI_ROOT_PASSWORD_SECRET
      ],
      vcf_deployment_config=vcf_cfg,
  )
  logger.debug(
      "Successfully loaded configuration profile for %s in %s/%s.",
      config.gce_nodes,
      config.project,
      config.zone,
  )
  return config


def run_pipeline(config_file_path: str) -> int:
  """Orchestrates execution across Phase 1, Phase 2 (a-e), and Phase 3.

  Args:
      config_file_path: Target path to master JSON deployment document.

  Returns:
      Integer process return exit code (0 for success, non-zero for failure).
  """
  logger_mod.setup_logger(logger_name=constants.DeployerDefaults.LOGGER_NAME)
  logger.info("=" * 70)
  logger.info("VCF Deployment Automation & Jumpbox Suite Initialized")
  logger.info("=" * 70)

  try:
    # Step 0: Parse configuration file
    config = load_config(config_file_path)
    gcp_cli = gcp_client.GCPClient(require_explicit_auth=True)

    # ======================================================================
    # Phase 1: Pre-Deployment Validation & Extraction
    # ======================================================================
    pre_val = validator.PreDeploymentValidator(config=config, gcp=gcp_cli)
    ctx: models.ValidationContext = retry_with_backoff(
        pre_val.validate_and_extract,
        max_attempts=constants.DeployerDefaults.VALIDATION_MAX_ATTEMPTS,
    )

    # ======================================================================
    # Phase 2: VCF Installer Deployment (Phase 2b active)
    # ======================================================================
    if config.vcf_deployment_config and ctx.target_esxi_ip:
      logger.info(
          "VCF profile detected. Advancing to Phase 2 against host %s...",
          ctx.target_esxi_ip,
      )

      # Initial connection uses default password before Phase 3 rotation,
      # with fallback to new password if host was already configured.
      esxi_cli = esxi_client.ESXiClient(
          host_ip=ctx.target_esxi_ip,
          user=constants.PasswordResetDefaults.DEFAULT_ROOT_USER,
          password=constants.PasswordResetDefaults.DEFAULT_INITIAL_SECRET,
          fallback_password=ctx.new_esxi_root_password,
      )

      try:
        # Phase 2a: Networking Setup (vSwitch0 port group configuration)
        effective_pg = ctx.port_group_name
        net_mgr = network_setup.NetworkManager(esxi=esxi_cli)
        if ctx.vlan_id is not None and ctx.port_group_name:
          effective_pg = retry_with_backoff(
              net_mgr.configure_networking,
              vlan_id=ctx.vlan_id,
              port_group_name=ctx.port_group_name,
          )
          logger.info("Effective port group for deployment: %s", effective_pg)

        # Phase 2b: vSAN ESA Cluster & Disk Setup
        vsan_mgr = vsan_setup.VSANManager(esxi=esxi_cli)
        retry_with_backoff(vsan_mgr.setup_vsan)

        # Phase 2c-e: VCF OVA Deployment & Bootstrapping via VMDeployer
        vm_mgr = vm_deployer.VMDeployer(esxi=esxi_cli)
        if ctx.vcf_installer_ova_url and effective_pg and ctx.vcf_vm_name:
          vm_ref = retry_with_backoff(
              vm_mgr.deploy_ova,
              vcf_installer_ova_url=ctx.vcf_installer_ova_url,
              ssl_thumbprint=ctx.ssl_thumbprint,
              port_group_name=effective_pg,
              vcf_vm_name=ctx.vcf_vm_name,
          )

          # Phase 2d: OVF Environment Config (vCenter-less extraConfig)
          if (
              ctx.sddc_manager_gateway
              and ctx.sddc_manager_netmask
              and ctx.vcf_appliance_root_password
              and ctx.vcf_appliance_local_password
              and ctx.vcf_domain
              and ctx.vcf_searchpath
          ):
            retry_with_backoff(
                vm_mgr.configure_ovf_environment,
                vm_reference=vm_ref,
                sddc_manager_ip=ctx.vcf_installer_ip,
                gateway=ctx.sddc_manager_gateway,
                netmask=ctx.sddc_manager_netmask,
                root_pwd=ctx.vcf_appliance_root_password,
                local_pwd=ctx.vcf_appliance_local_password,
                fqdn=config.vcf_deployment_config.vcf_installer_fqdn,
                domain=ctx.vcf_domain,
                searchpath=ctx.vcf_searchpath,
                dns_server=ctx.dns_server,
            )

          # Phase 2e: VM Power On & IP Acquisition monitoring
          retry_with_backoff(
              vm_mgr.power_on_and_wait_for_ip,
              vm_reference=vm_ref,
              target_ip=ctx.vcf_installer_ip,
              poll_interval_seconds=(
                  constants.DeployerDefaults.POWER_ON_POLL_INTERVAL_SECONDS
              ),
              timeout_seconds=(
                  constants.DeployerDefaults.POWER_ON_TIMEOUT_SECONDS
              ),
          )

          # Phase 2f: Bypass vSAN HCL & Disk Claiming Validation on Cloud Builder
          retry_with_backoff(
              vm_mgr.bypass_vcf_hcl_disk_validation,
              vcf_ip=ctx.vcf_installer_ip,
              root_pwd=ctx.vcf_appliance_root_password,
              local_pwd=ctx.vcf_appliance_local_password,
              appliance_user=ctx.vcf_appliance_local_user,
              timeout_seconds=180,
              poll_interval_seconds=5,
          )
      finally:
        esxi_cli.disconnect()
    else:
      logger.info(
          "vcf_deployment_config omitted; bypassing Phase 2 completely."
      )

    # ======================================================================
    # Phase 3: ESXi Inventory Root Password Reset
    # ======================================================================
    pwd_mgr = password_resetter.PasswordResetter()
    retry_with_backoff(pwd_mgr.reset_esxi_inventory_passwords, context=ctx)

    logger.info("=" * 70)
    logger.info("VCF Deployment Automation completed across all phases!")
    logger.info("=" * 70)
    return constants.ExitCode.SUCCESS

  except models.ValidationError as val_err:
    logger.critical(
        "Pipeline ABORTED during Phase 1 Validation: %s",
        val_err,
    )
    return constants.ExitCode.VALIDATION_ERROR
  except models.DeployerError as dep_err:
    logger.critical(
        "Pipeline FAILED during operational execution: %s",
        dep_err,
    )
    return constants.ExitCode.DEPLOYER_ERROR
  except Exception as unhandled_err:  # pylint: disable=broad-exception-caught
    logger.critical(
        "An unexpected critical exception occurred: %s",
        unhandled_err,
        exc_info=True,
    )
    return constants.ExitCode.UNHANDLED_ERROR


def main() -> None:
  """CLI entry point for command line invocations on customer Jumpboxes."""
  parser = argparse.ArgumentParser(
      description=(
          "Automated VCF Installer Deployment & Jumpbox Infrastructure"
          " Orchestrator"
      ),
      formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument(
      "--config",
      type=str,
      default=constants.DeployerDefaults.DEFAULT_CONFIG_FILE,
      help=(
          "Absolute or relative file system path to target JSON deployment"
          " profile."
      ),
  )
  args = parser.parse_args()

  exit_code = run_pipeline(config_file_path=args.config)
  sys.exit(exit_code)


if __name__ == "__main__":
  main()
