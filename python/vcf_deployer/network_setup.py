"""Phase 2a: ESXi Networking Setup module.

Configures standard virtual switch networking on target ESXi host,
establishing an idempotent port group bound directly to vSwitch0 with the target
VLAN ID.
"""

import logging
import re
from typing import Any, Dict, List

from clients import esxi_client as esxi_client_mod
import constants
import models

try:
  from pyVmomi import vim
except ImportError:
  vim = None


logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class NetworkManager:
  """Manages idempotent ESXi virtual networking configuration."""

  def __init__(self, esxi: esxi_client_mod.ESXiClient) -> None:
    """Initializes NetworkManager with an established ESXiClient wrapper.

    Args:
        esxi: Initialized ESXiClient connected to target hypervisor.
    """
    self.esxi = esxi

  def configure_networking(
      self,
      vlan_id: int,
      port_group_name: str,
      vswitch_name: str = constants.NetworkingDefaults.DEFAULT_VSWITCH,
  ) -> str:
    """Configures virtual network port group on target vSwitch with idempotency.

    Args:
        vlan_id: Numeric VLAN ID deduced during Phase 1.
        port_group_name: Unique port group name string (including random
          suffix).
        vswitch_name: Target virtual switch name (defaults to "vSwitch0").

    Returns:
        Effective port group name string to be used in subsequent steps.

    Raises:
        models.DeployerError: If network configuration fails.
    """
    logger.info(
        "Phase 2a: Setting up port group for VLAN %d on switch '%s'...",
        vlan_id,
        vswitch_name,
    )

    self.esxi.connect_pyvmomi()
    network_system = self.esxi.get_network_system()

    # Idempotency check: look for existing portgroup matching pattern or exact name
    existing_pgs = self._get_existing_port_groups(network_system)
    pattern = constants.NetworkingDefaults.PORT_GROUP_PATTERN.format(
        vlan_id=vlan_id
    )
    for pg in existing_pgs:
      pg_name = pg.get("name", "")
      pg_vlan = pg.get("vlan_id", -1)
      pg_vswitch = pg.get("vswitch", "")
      if pg_vswitch == vswitch_name and pg_vlan == vlan_id and (
          re.match(pattern, pg_name) or pg_name == port_group_name
      ):
        logger.info(
            "Found existing matching port group '%s' (VLAN %d) on switch"
            " '%s'; skipping creation.",
            pg_name,
            vlan_id,
            vswitch_name,
        )
        return pg_name

    logger.info(
        "Creating port group '%s' (VLAN %d) on switch '%s'...",
        port_group_name,
        vlan_id,
        vswitch_name,
    )
    self._add_port_group(network_system, port_group_name, vlan_id, vswitch_name)
    logger.info("Successfully configured port group '%s'.", port_group_name)
    return port_group_name

  def _get_existing_port_groups(
      self, network_system: Any
  ) -> List[Dict[str, Any]]:
    """Retrieves list of existing port group specs from HostNetworkSystem."""
    pgs: List[Dict[str, Any]] = []
    net_info = getattr(network_system, "networkInfo", None)
    if not net_info:
      return pgs
    raw_pgs = getattr(net_info, "portgroup", []) or []
    for pg in raw_pgs:
      spec = getattr(pg, "spec", None)
      if spec:
        pgs.append({
            "name": str(getattr(spec, "name", "")),
            "vlan_id": int(getattr(spec, "vlanId", 0) or 0),
            "vswitch": str(getattr(spec, "vswitchName", "")),
        })
    return pgs

  def _add_port_group(
      self, network_system: Any, name: str, vlan_id: int, vswitch_name: str
  ) -> None:
    """Creates a port group via HostNetworkSystem.AddPortGroup call."""
    if not vim:
      raise models.NonRetryableError("pyVmomi package is not installed.")
    try:
      spec = vim.host.PortGroup.Specification()
      spec.name = name
      spec.vlanId = vlan_id
      spec.vswitchName = vswitch_name
      spec.policy = vim.host.NetworkPolicy()
      network_system.AddPortGroup(portgrp=spec)
    except Exception as exc:  # pylint: disable=broad-exception-caught
      raise models.NonRetryableError(
          f"Failed to add port group '{name}': {exc}"
      ) from exc
