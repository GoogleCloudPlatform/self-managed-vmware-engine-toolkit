"""Phase 2b: vSAN Setup module.

Handles automated vSAN Express Storage Architecture (ESA) cluster init,
interactive SSH disk hardware discovery (queryVDQViaSSH pattern), bulk storage
disk claiming (claimDisksInBulk pattern), and default storage policy binding.
"""

import json
import logging
from typing import Dict, List, Tuple

from clients import esxi_client as esxi_client_mod
import constants
import models

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class VSANManager:
  """Orchestrates idempotent vSAN ESA initialization and storage pool control."""

  def __init__(self, esxi: esxi_client_mod.ESXiClient) -> None:
    """Initializes VSANManager with target ESXiClient wrapper.

    Args:
        esxi: Initialized ESXiClient connected to target hypervisor.
    """
    self.esxi = esxi

  def setup_vsan(self) -> None:
    """Executes Phase 2b vSAN ESA cluster initialization and storage disk claim.

    Step A: Checks cluster active state via CLI (vsan cluster get). If active,
            skips init; otherwise executes vsan cluster new -x true.
    Step B: Runs SSH disk discovery (/sbin/vdq -q), partitioning devices into
            In-Use Disks and Eligible Disks.
    Step C: If eligible drives exist, compiles a single batch command to claim
            all disks concurrently (vsan storagepool add -d naa...). Skips
            cleanly if all disks are in use.
    Step D: Assigns hardcoded default VM storage policies via vsan policy
            setdefault matching preparednode.go specification.

    Raises:
        models.DeployerError: If cluster creation or storage claiming fails.
    """
    logger.info("Phase 2b: Starting vSAN ESA initialization and disk checks...")

    # Step 0 & A: Idempotency check and cluster instantiation
    self._check_and_init_cluster()

    # Step B: SSH Disk Discovery (queryVDQViaSSH pattern)
    eligible_disks, in_use_disks = self._query_vdq_via_ssh()

    logger.info(
        "Disk discovery complete: Found %d already in-use and %d eligible for"
        " storage pool addition.",
        len(in_use_disks),
        len(eligible_disks),
    )

    # Step C: Bulk Disk Claiming (claimDisksInBulk pattern)
    if not eligible_disks:
      if in_use_disks:
        logger.info(
            "Step C: No eligible disks found to add to Storage Pool, but found"
            " disks already in-use. Skipping claim."
        )
      else:
        logger.info(
            "Step C: No eligible or in-use disks found to add to Storage Pool."
        )
        raise models.NonRetryableError(
            "No eligible or in-use disks found to add to Storage Pool."
        )
    else:
      logger.info(
          "Step C: Found %d eligible disk(s). Claiming via esxcli...",
          len(eligible_disks),
      )
      self._claim_disks_in_bulk(eligible_disks)

    # Step D: Hardcoded Policy Binding (matching preparednode.go specification)
    logger.info(
        "Step D: Configuring %d hardcoded vSAN policies via esxcli...",
        len(constants.VSANConstants.DEFAULT_VSAN_POLICIES),
    )
    for p in constants.VSANConstants.DEFAULT_VSAN_POLICIES:
      self._bind_default_policies(p["type"], p["policy"])

    logger.info("vSAN ESA cluster configuration completed successfully.")

  def _check_and_init_cluster(self) -> None:
    """Checks cluster status via esxcli; instantiates ESA cluster if needed."""
    logger.info("Checking vSAN cluster status...")
    out = self.esxi.execute_esxcli(["vsan", "cluster", "get"])
    is_enabled = "enabled: true" in out.lower() or "enabled:true" in out.lower()
    if is_enabled:
      logger.info("vSAN cluster is already enabled. Skipping initialization.")
    else:
      logger.info("Step A: Initializing vSAN ESA...")
      self.esxi.execute_esxcli(["vsan", "cluster", "new", "-x"])

  def _query_vdq_via_ssh(self) -> Tuple[List[str], List[str]]:
    """Runs /sbin/vdq -q over SSH and parses output into eligible/in-use lists.

    Returns:
        Tuple of (eligible_disks, in_use_disks) device name lists.
    """
    logger.info(
        "Step B: Fetching eligible disks via SSH using %s...",
        constants.VSANConstants.VDQ_COMMAND,
    )
    out = self.esxi.execute_ssh_command(constants.VSANConstants.VDQ_COMMAND)
    try:
      raw_disks = json.loads(out)
    except Exception as exc:
      raise models.NonRetryableError(
          f"Failed to decode /sbin/vdq -q output: {exc}"
      ) from exc

    eligible_disks: List[str] = []
    in_use_disks: List[str] = []

    for disk in raw_disks:
      state = (
          str(disk.get("StoragePoolState") or disk.get("State") or "")
          .strip()
          .lower()
      )
      name = str(disk.get("Name") or "").strip()
      if not name:
        continue
      if state == constants.VSANConstants.ELIGIBLE_FOR_STORAGE_POOL:
        eligible_disks.append(name)
      elif state == constants.VSANConstants.IN_USE_FOR_STORAGE_POOL:
        in_use_disks.append(name)

    return eligible_disks, in_use_disks

  def _claim_disks_in_bulk(self, eligible_disks: List[str]) -> None:
    """Compiles a single consolidated batch command to claim disks concurrently.

    Args:
        eligible_disks: List of disk device names (e.g. naa.6000c29...).
    """
    args = ["vsan", "storagepool", "add"]
    for disk in eligible_disks:
      args.extend(["-d", disk])
    logger.info(
        "Claiming %d disks in a single bulk operation...", len(eligible_disks)
    )
    self.esxi.execute_esxcli(args)
    logger.info("All disks successfully added to the Storage Pool.")

  def _bind_default_policies(self, policy_class: str, policy_name: str) -> None:
    """Assigns requested storage policies using esxcli vsan policy setdefault."""
    logger.info("Setting policy for %s...", policy_class)
    self.esxi.execute_esxcli(
        ["vsan", "policy", "setdefault", "-c", policy_class, "-p", policy_name]
    )
