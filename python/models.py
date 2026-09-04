"""Data models, configuration schemas, and exception hierarchy.

Defines core structures used across Phase 1 (Validation), Phase 2
(Deployment), and Phase 3 (Password Reset), along with structured error
classification for retry mechanics.
"""

import dataclasses
from typing import Any, Dict, List, Optional

# ==============================================================================
# Custom Error Classification
# ==============================================================================


class DeployerError(Exception):
  """Base error class for operational errors during Phase 2 and Phase 3."""

  def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
    super().__init__(message)
    self.details = details or {}


class ValidationError(DeployerError):
  """Raised during Phase 1 pre-deployment validation on non-conformances.

  Halts runtime immediately without retrying when external system states or
  configuration inputs fail mandatory pre-flight checks.
  """


class RetryableError(DeployerError):
  """Raised for transient errors that should trigger exponential backoff.

  Examples: Transient network faults, HTTP 429 Too Many Requests (rate
  limits), HTTP 500/503 server errors, and socket connection timeouts.
  """


class NonRetryableError(DeployerError):
  """Raised for terminal errors where retrying will not resolve the issue.

  Examples: HTTP 400 Bad Request (invalid config parameters), HTTP 401/403
  Unauthorized/Forbidden (credential auth failures), and HTTP 404 Not Found.
  """


# ==============================================================================
# Input Configuration Schemas (from config.json)
# ==============================================================================


@dataclasses.dataclass
class VCFDeploymentConfig:
  """Optional configuration block for Phase 2 VCF Installer deployment.

  If omitted from DeployerConfig, the deployment pipeline skips Phase 2
  mutations and advances directly to Phase 3 password rotation.
  """

  target_gce_node: str
  vcf_appliance_root_password_secret: str
  vcf_appliance_local_user: str
  vcf_appliance_local_user_password_secret: str
  vcf_installer_fqdn: str
  vcf_installer_ip_source: Any
  offline_depot_subnet_cidr: str
  offline_depot_subnet_name: Optional[str] = None
  dns_server: Optional[str] = None


@dataclasses.dataclass
class DeployerConfig:
  """Master config document parsed from config.json at runtime by main.py."""

  project: str
  zone: str
  gce_nodes: Any
  esxi_root_password_secret: str
  vcf_deployment_config: Optional[VCFDeploymentConfig] = None

  @property
  def region(self) -> str:
    """Parses GCP region from zone string (e.g.

    'us-central1-a' -> 'us-central1').
    """
    if "-" in self.zone:
      return "-".join(self.zone.split("-")[:-1])
    return self.zone

  def get_full_node_path(self, node_input: str) -> str:
    """Constructs full GCE node resource string if short name provided."""
    if node_input.startswith("projects/"):
      return node_input
    return f"projects/{self.project}/zones/{self.zone}/instances/{node_input}"

  def get_full_secret_path(self, secret_input: str) -> str:
    """Constructs full Secret Manager resource path if short secret name provided."""
    if secret_input.startswith("projects/"):
      if "/versions/" not in secret_input:
        return f"{secret_input}/versions/latest"
      return secret_input
    return f"projects/{self.project}/secrets/{secret_input}/versions/latest"


# ==============================================================================
# Infrastructure Inspection Structures (Phase 1 Caching)
# ==============================================================================


@dataclasses.dataclass
class SubnetworkInfo:
  """Subnetwork metadata attached to a GCE primary or dynamic network interface."""

  subnetwork_uri: str
  vlan_id: int
  network_uri: str
  cidr: Optional[str] = None


@dataclasses.dataclass
class GCEInstanceDetails:
  """Complete compute instance attributes cached after initial GCE inspection."""

  instance_resource_string: str
  short_name: str
  project: str
  zone: str
  primary_ip: str
  boot_image_name: str
  subnetworks: List[SubnetworkInfo]
  tags: List[str]
  tags_fingerprint: str
  labels: Dict[str, str] = dataclasses.field(default_factory=dict)
  label_fingerprint: str = ""


# ==============================================================================
# Phase 1 -> Phase 2 & 3 Context structures
# ==============================================================================


@dataclasses.dataclass(frozen=True)
class ValidationContext:
  """Immutable data context holding deduced variables and secrets.

  Produced upon completion of Phase 1 pre-deployment validation and passed
  sequentially to Phase 2 and Phase 3 modules.
  """

  # Mapping of ESXi GCE node resource strings to cached GCEInstanceDetails
  esxi_nodes: Dict[str, GCEInstanceDetails]
  new_esxi_root_password: str

  # Optional fields populated only if vcf_deployment_config was provided
  target_esxi_ip: Optional[str] = None
  vcf_installer_ip: Optional[str] = None
  vcf_installer_ova_url: Optional[str] = None
  vlan_id: Optional[int] = None
  port_group_name: Optional[str] = None
  sddc_manager_netmask: Optional[str] = None
  sddc_manager_gateway: Optional[str] = None
  vcf_vm_name: Optional[str] = None
  vcf_domain: Optional[str] = None
  vcf_searchpath: Optional[str] = None
  ssl_thumbprint: Optional[str] = None
  vcf_appliance_root_password: Optional[str] = None
  vcf_appliance_local_password: Optional[str] = None
  vcf_appliance_local_user: Optional[str] = "admin"
  dns_server: Optional[str] = None


# ==============================================================================
# Hardware Discovery Structures
# ==============================================================================


@dataclasses.dataclass
class VDQDiskInfo:
  """Representation of storage disk discovered via /sbin/vdq -q over SSH."""

  name: str
  device_path: str
  state: str
  eligible_for_use: bool
  is_ssd: bool
  capacity_bytes: int
  details: Optional[Dict[str, Any]] = None
