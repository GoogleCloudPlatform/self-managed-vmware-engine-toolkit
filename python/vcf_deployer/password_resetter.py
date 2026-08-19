"""Phase 3: ESXi Inventory Root Password Reset module.

Orchestrates root password reset on ESXi hosts.
"""

import concurrent.futures
import logging

from clients import esxi_client as esxi_client_mod
import constants
import models

try:
  from pyVmomi import vim
except ImportError:
  vim = None


logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class PasswordResetter:
  """Orchestrates automated ESXi hypervisor root password reset."""

  def reset_password(
      self, host_ip: str, old_password: str, new_password: str
  ) -> None:
    """Connects to ESXi via pyVmomi and updates the root password idempotently.

    First attempts authentication using new_password. If successful, returns
    immediately as the host is already configured. Otherwise, connects using
    old_password and updates root credentials to new_password.

    Args:
        host_ip: Target ESXi host IP address.
        old_password: Active root password.
        new_password: New root password to set.

    Raises:
        models.DeployerError: If connection or password update fails.
    """
    logger.info(
        "Verifying if host '%s' is already configured with new root password...",
        host_ip,
    )
    new_client = esxi_client_mod.ESXiClient(
        host_ip=host_ip,
        user=constants.PasswordResetDefaults.DEFAULT_ROOT_USER,
        password=new_password,
    )
    try:
      si = new_client.connect_pyvmomi()
      if si:
        logger.info(
            "Host '%s' is already authenticated with new root password; skipping"
            " reset.",
            host_ip,
        )
        return
    except Exception:  # pylint: disable=broad-exception-caught
      logger.debug(
          "Authentication with new password failed on '%s'. Proceeding"
          " to reset using old password...",
          host_ip,
      )
    finally:
      new_client.disconnect()

    logger.info("Resetting root password on host '%s'...", host_ip)
    client = esxi_client_mod.ESXiClient(
        host_ip=host_ip,
        user=constants.PasswordResetDefaults.DEFAULT_ROOT_USER,
        password=old_password,
    )
    try:
      si = client.connect_pyvmomi()
      account_mgr = getattr(si.content, "accountManager", None)
      if not account_mgr:
        raise models.NonRetryableError(
            f"Account manager not found on host {host_ip}"
        )

      user_spec = getattr(
          vim.host, "HostAccountSpec", getattr(vim, "HostAccountSpec", None)
      )()
      if user_spec is None:
        raise models.NonRetryableError(
            "vim.host.HostAccountSpec type not found in pyVmomi"
        )
      user_spec.id = constants.PasswordResetDefaults.DEFAULT_ROOT_USER
      user_spec.password = new_password

      account_mgr.UpdateUser(user_spec)
      logger.info(
          "Successfully updated password for root on host '%s'.", host_ip
      )
    except Exception as exc:
      if isinstance(exc, (models.ValidationError, models.NonRetryableError)):
        raise exc
      raise models.DeployerError(
          f"Failed to reset root password on host '{host_ip}': {exc}"
      ) from exc
    finally:
      client.disconnect()

  def reset_esxi_inventory_passwords(
      self,
      context: models.ValidationContext,
      batch_size: int = constants.PasswordResetDefaults.DEFAULT_BATCH_SIZE,
  ) -> None:
    """Executes Phase 3 password rotation across inventory in parallel batches.

    Args:
        context: ValidationContext holding host mappings and target password.
        batch_size: Max number of concurrent host resets per batch (default 10).
    """
    logger.info(
        "Phase 3: Initiating inventory root password reset across hosts..."
    )
    if not context.esxi_instances:
      logger.warning(
          "No ESXi host mappings found in ValidationContext; skipping."
      )
      return

    hosts = list(context.esxi_instances.values())
    new_password = context.new_esxi_root_password
    total_hosts = len(hosts)
    total_batches = (total_hosts + batch_size - 1) // batch_size

    logger.info(
        "Parallelizing password reset for %d host(s) across %d batch(es)"
        " (batch size: %d)...",
        total_hosts,
        total_batches,
        batch_size,
    )

    for batch_num in range(total_batches):
      batch_start = batch_num * batch_size
      batch_end = min(batch_start + batch_size, total_hosts)
      current_batch = hosts[batch_start:batch_end]

      logger.info(
          "Processing batch %d/%d (%d host(s))...",
          batch_num + 1,
          total_batches,
          len(current_batch),
      )

      with concurrent.futures.ThreadPoolExecutor(
          max_workers=len(current_batch)
      ) as executor:
        future_to_host = {
            executor.submit(
                self.reset_password,
                details.primary_ip,
                constants.PasswordResetDefaults.DEFAULT_INITIAL_SECRET,
                new_password,
            ): details
            for details in current_batch
        }

        for future in concurrent.futures.as_completed(future_to_host):
          details = future_to_host[future]
          try:
            future.result()
          except Exception as exc:
            logger.error(
                "Password reset failed for host %s (%s): %s",
                getattr(details, "instance_id", details.primary_ip),
                details.primary_ip,
                exc,
            )
            raise

    logger.info("Phase 3 inventory root password rotation concluded cleanly.")
