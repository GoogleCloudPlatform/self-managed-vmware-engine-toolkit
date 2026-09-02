"""Constants and enumerations used across the VCF deployment toolkit.

Defines configuration schema keys, process exit codes, retry mechanics defaults,
infrastructure networking parameters, validation thresholds, vSAN policies,
and VM deployment operational defaults used across Phase 1, Phase 2, and Phase 3.
"""

import enum
from typing import Dict, List, Tuple


class ExitCode(enum.IntEnum):
  """Process return codes for CLI executions and error taxonomy."""

  SUCCESS = 0
  UNHANDLED_ERROR = 1
  VALIDATION_ERROR = 2
  DEPLOYER_ERROR = 3


class ConfigKeys:
  """Keys for master configuration profile (config.json)."""

  PROJECT = "project"
  ZONE = "zone"
  GCE_NODES = "gce_nodes"
  ESXI_ROOT_PASSWORD_SECRET = "esxi_root_password_secret"
  PREFIX = "prefix"
  SUBNET = "subnet"
  VCF_DEPLOYMENT_CONFIG = "vcf_deployment_config"

  REQUIRED_KEYS: Tuple[str, ...] = (
      PROJECT,
      ZONE,
      GCE_NODES,
      ESXI_ROOT_PASSWORD_SECRET,
  )


class VCFConfigKeys:
  """Keys for optional Phase 2 VCF deployment configuration block."""

  TARGET_GCE_NODE = "target_gce_node"
  VCF_APPLIANCE_ROOT_PASSWORD_SECRET = "vcf_appliance_root_password_secret"
  VCF_APPLIANCE_LOCAL_USER_PASSWORD_SECRET = (
      "vcf_appliance_local_user_password_secret"
  )
  VCF_INSTALLER_FQDN = "vcf_installer_fqdn"
  VCF_INSTALLER_IP_SOURCE = "vcf_installer_ip_source"
  OFFLINE_DEPOT_SUBNET_NAME = "offline_depot_subnet_name"
  OFFLINE_DEPOT_SUBNET_CIDR = "offline_depot_subnet_cidr"
  FORWARDING_RULE = "forwarding_rule"
  RESERVED_ADDRESS = "reserved_address"
  DNS_SERVER = "dns_server"

  REQUIRED_KEYS: Tuple[str, ...] = (
      TARGET_GCE_NODE,
      VCF_APPLIANCE_ROOT_PASSWORD_SECRET,
      VCF_APPLIANCE_LOCAL_USER_PASSWORD_SECRET,
      VCF_INSTALLER_FQDN,
      VCF_INSTALLER_IP_SOURCE,
      OFFLINE_DEPOT_SUBNET_CIDR,
  )


class RetryDefaults:
  """Default exponential backoff parameters."""

  MAX_ATTEMPTS = 5
  BASE_DELAY = 2.0
  MAX_DELAY = 60.0
  JITTER_MIN = 0.1
  JITTER_MAX = 1.5


class DeployerDefaults:
  """Default operational parameters for orchestrator and pipeline execution."""

  LOGGER_NAME = "vcf_deployer"
  DEFAULT_CONFIG_FILE = "config.json"
  LOG_FORMAT = (
      "%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s"
  )
  LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
  VALIDATION_MAX_ATTEMPTS = 3
  POWER_ON_POLL_INTERVAL_SECONDS = 10
  POWER_ON_TIMEOUT_SECONDS = 600


class NetworkingDefaults:
  """Default network parameters, ports, and metadata endpoints."""

  DEFAULT_VSWITCH = "vSwitch0"
  DEFAULT_PRIMARY_NIC = "nic0"
  HTTPS_PORT = 443
  SSH_PORT = 22
  DEFAULT_METADATA_SERVER = "169.254.169.254"
  SSL_TIMEOUT_SECONDS = 10
  SSH_TIMEOUT_SECONDS = 300
  HTTP_TIMEOUT_SECONDS = 60
  MAX_FQDN_LENGTH = 255
  PORT_GROUP_PATTERN = r"^vlan-{vlan_id}-[0-9a-fA-F]+$"
  FORWARDING_RULE_PATTERN = (
      r"(?:^|/)projects/([^/]+)/regions/([^/]+)/forwardingRules/([^/]+)$"
  )
  ADDRESS_PATTERN = (
      r"(?:^|/)projects/([^/]+)/regions/([^/]+)/addresses/([^/]+)$"
  )


class GCPClientDefaults:
  """Defaults and environment variable names for GCP SDK client wrapper."""

  COMPUTE_API_VERSION_ENV = "COMPUTE_API_VERSION"
  DEFAULT_COMPUTE_API_VERSION = "v1"
  DEFAULT_DNS_HOST = "dns.googleapis.com"
  STAGING_DNS_HOST = "staging-dns.sandbox.googleapis.com"
  DEFAULT_DNS_API_VERSION = "v1"
  STAGING_COMPUTE_API_VERSION = "staging_v1"
  OPERATION_TIMEOUT_SECONDS = 60
  DEFAULT_SECRET_VERSION = "versions/latest"
  NON_RETRYABLE_HTTP_CODES: Tuple[int, ...] = (400, 401, 403, 404)
  RETRYABLE_HTTP_CODES: Tuple[int, ...] = (429, 500, 502, 503, 504)


class ValidationRules:
  """Validation rules, password complexity thresholds, tags, and depot constants."""

  REQUIRED_GCE_TAGS: Tuple[str, ...] = ("mm-gcve-node",)
  REQUIRED_GCE_LABELS: Dict[str, str] = {"gcve-node": "true"}

  OFFLINE_DEPOT_ENV_VAR = "OFFLINE_DEPOT_ENV"
  DEFAULT_OFFLINE_DEPOT_ENV = "prod"
  MAX_INSPECTION_WORKERS = 10
  MAX_TAG_GOVERNANCE_WORKERS = 10

  RFC1123_LABEL_PATTERN = r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
  VCF_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
  ESXI_IMAGE_PATTERN = r"^(?:vmware-)?esxi-(\d+-\d+-\d+)-(.+)$"
  BUILD_NUMBER_PATTERN = r"^[0-9]+$"
  VCF_OVA_PREFIX_TEMPLATE = "VCF-SDDC-Manager-Appliance-{vcf_version}"
  HTML_OVA_HREF_PATTERN = r'href="([^"]+\.ova)"'
  HTML_OVA_HREF_FALLBACK_PATTERN = r'href=["\']?([^">\s]+\.ova)["\']?'

  DEPOT_HOST_TEMPLATE = "offline-depot.{region}.selfmanagedvmwareengine.goog"
  DEPOT_HOST_TEMPLATES: Dict[str, str] = {
      "prod": "offline-depot.{region}.selfmanagedvmwareengine.goog",
      "staging": "offline-depot.{region}.staging.smve-vcf.internal",
      "autopush": "offline-depot.{region}.autopush.smve-vcf.internal",
  }
  DEPOT_INDEX_PATH = "/PROD/COMP/SDDC_MANAGER_VCF/"
  DEPOT_INDEX_TIMEOUT_SECONDS = 30

  # Password complexity parameters (min_length, max_length, min_classes)
  ESXI_ROOT_PASSWORD_MIN_LEN = 7
  ESXI_ROOT_PASSWORD_MAX_LEN = 39
  ESXI_ROOT_PASSWORD_MIN_CLASSES = 3

  VCF_ROOT_PASSWORD_MIN_LEN = 15
  VCF_ROOT_PASSWORD_MAX_LEN = 0
  VCF_ROOT_PASSWORD_MIN_CLASSES = 4

  VCF_LOCAL_PASSWORD_MIN_LEN = 12
  VCF_LOCAL_PASSWORD_MAX_LEN = 0
  VCF_LOCAL_PASSWORD_MIN_CLASSES = 4


class OfflineDepotDefaults:
  """Defaults and multi-environment templates for Offline Depot PSC automation."""

  MAX_SUBNET_PREFIX_LEN = 29
  PSC_IP_PURPOSE = "GCE_ENDPOINT"
  DNS_RECORD_TTL_SECONDS = 300

  # Standard resource name templates
  SUBNET_NAME_TEMPLATE = "offline-depot-subnet-{region}"
  PSC_IP_NAME_TEMPLATE = "offline-depot-psc-ip-{region}"
  PSC_FORWARDING_RULE_TEMPLATE = "offline-depot-psc-ep-{region}"
  DNS_ZONE_NAME_TEMPLATE = "offline-depot-{region}-{env}-zone"

  # Cloud DNS Private Base Domains (Trailing dot included)
  BASE_DOMAIN_TEMPLATES: Dict[str, str] = {
      "prod": "{region}.selfmanagedvmwareengine.goog.",
      "staging": "{region}.staging.smve-vcf.internal.",
      "autopush": "{region}.autopush.smve-vcf.internal.",
  }

  # Regional Service Attachment URI by environment
  SERVICE_ATTACHMENT_TEMPLATES: Dict[str, str] = {
      "prod": "projects/smve-prod-offline-depot/regions/{region}/serviceAttachments/offline-depot-service-attachment-{region}",
      "staging": "projects/smve-staging-offline-depot/regions/{region}/serviceAttachments/offline-depot-service-attachment-{region}",
      "autopush": "projects/smve-autopush-offline-depot/regions/{region}/serviceAttachments/offline-depot-service-attachment-{region}",
  }


class VSANConstants:
  """Constants and policy definitions for Phase 2b vSAN ESA initialization."""

  ELIGIBLE_FOR_STORAGE_POOL = "eligible for use by storage pool"
  IN_USE_FOR_STORAGE_POOL = "in-use for storage pool"
  VDQ_COMMAND = "/sbin/vdq -q"

  DEFAULT_VSAN_POLICIES: List[Dict[str, str]] = [
      {
          "type": "cluster",
          "policy": '(("hostFailuresToTolerate" i0))',
      },
      {
          "type": "vmem",
          "policy": '(("hostFailuresToTolerate" i0) ("forceProvisioning" i1))',
      },
      {
          "type": "vmswap",
          "policy": '(("hostFailuresToTolerate" i0) ("forceProvisioning" i1))',
      },
      {
          "type": "vmnamespace",
          "policy": '(("hostFailuresToTolerate" i0))',
      },
      {
          "type": "vdisk",
          "policy": '(("hostFailuresToTolerate" i0))',
      },
  ]


class VMDeployerDefaults:
  """Operational defaults and OVF property names for Phase 2c-e VM deployment."""

  DEFAULT_DATASTORE_NAME = "vsanDatastore"
  DISK_PROVISIONING_THIN = "thin"
  HTTP_USER_AGENT = "VCFDeployer/1.0"
  NFC_LEASE_TIMEOUT_SECONDS = 120
  NFC_LEASE_POLL_INTERVAL_SECONDS = 2
  TASK_TIMEOUT_SECONDS = 900
  TASK_POLL_INTERVAL_SECONDS = 3
  GUESTINFO_OVF_ENV = "guestinfo.ovfEnv"
  GUESTINFO_OVF_ENV_LEN = "guestinfo.ovfEnv/len"


class OVFPropertyKeys:
  """Property keys used in the OVF environment configuration."""

  ROOT_PASSWORD = "ROOT_PASSWORD"
  LOCAL_USER_PASSWORD = "LOCAL_USER_PASSWORD"
  VAMI_HOSTNAME = "vami.hostname"
  GUESTINFO_NTP = "guestinfo.ntp"
  VAMI_IP0_SDDC_MANAGER = "vami.ip0.SDDC-Manager"
  VAMI_NETMASK0_SDDC_MANAGER = "vami.netmask0.SDDC-Manager"
  VAMI_GATEWAY_SDDC_MANAGER = "vami.gateway.SDDC-Manager"
  VAMI_DOMAIN_SDDC_MANAGER = "vami.domain.SDDC-Manager"
  VAMI_SEARCHPATH_SDDC_MANAGER = "vami.searchpath.SDDC-Manager"
  VAMI_DNS_SDDC_MANAGER = "vami.DNS.SDDC-Manager"


class PasswordResetDefaults:
  """Defaults for Phase 3 ESXi inventory root password reset."""

  DEFAULT_INITIAL_SECRET = "Google1!Google1!"
  DEFAULT_BATCH_SIZE = 10
  DEFAULT_ROOT_USER = "root"
