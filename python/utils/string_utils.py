"""Client-independent string parsing and validation utilities.

Provides stateless domain helper routines for password complexity auditing,
ESXi boot disk image version parsing, RFC 1123 FQDN deconstruction, and
numerical build sorting of OVA distribution filenames.
"""

import logging
import os
import re
import sys
from typing import List, Tuple

# Ensure top-level 'python/' application root is in sys.path for cross-importing
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
  sys.path.insert(0, root_dir)

import constants
import models  # pylint: disable=g-import-not-at-top

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)

LABEL_REGEX = re.compile(constants.ValidationRules.RFC1123_LABEL_PATTERN)
VCF_VERSION_REGEX = re.compile(constants.ValidationRules.VCF_VERSION_PATTERN)
ESXI_IMAGE_REGEX = re.compile(constants.ValidationRules.ESXI_IMAGE_PATTERN)
BUILD_NUMBER_REGEX = re.compile(constants.ValidationRules.BUILD_NUMBER_PATTERN)
FORWARDING_RULE_REGEX = re.compile(
    constants.NetworkingDefaults.FORWARDING_RULE_PATTERN
)
ADDRESS_REGEX = re.compile(constants.NetworkingDefaults.ADDRESS_PATTERN)


def clean_gcp_uri(uri: str) -> str:
  """Strips Google API domain prefix from resource URIs, leaving 'projects/...'.

  Args:
      uri: Raw GCP resource URI string (e.g.
        'https://www.googleapis.com/compute/v1/projects/my-proj/...').

  Returns:
      Clean relative path starting with 'projects/...'.
  """
  if not uri:
    return ""
  s = str(uri).strip()
  idx = s.find("projects/")
  if idx != -1:
    return s[idx:]
  return s


def parse_forwarding_rule_path(path_or_uri: str) -> Tuple[str, str, str]:
  """Extracts project, region, and forwarding rule name from resource path.

  Args:
      path_or_uri: Resource URI string (e.g.,
        'projects/my-proj/regions/us-east4/forwardingRules/my-fr').

  Returns:
      Tuple of (project, region, forwarding_rule_name).

  Raises:
      models.ValidationError: If resource string formatting is invalid.
  """
  clean = clean_gcp_uri(path_or_uri)
  matches = FORWARDING_RULE_REGEX.search(clean)
  if not matches:
    raise models.ValidationError(
        f"Invalid forwarding rule resource path '{path_or_uri}'. Expected"
        " format: 'projects/<project>/regions/<region>/forwardingRules/<name>'"
    )
  return matches.group(1), matches.group(2), matches.group(3)


def parse_address_path(path_or_uri: str) -> Tuple[str, str, str]:
  """Extracts project, region, and address name from resource path.

  Args:
      path_or_uri: Resource URI string (e.g.,
        'projects/my-proj/regions/us-east4/addresses/my-addr').

  Returns:
      Tuple of (project, region, address_name).

  Raises:
      models.ValidationError: If resource string formatting is invalid.
  """
  clean = clean_gcp_uri(path_or_uri)
  matches = ADDRESS_REGEX.search(clean)
  if not matches:
    raise models.ValidationError(
        f"Invalid reserved address resource path '{path_or_uri}'. Expected"
        " format: 'projects/<project>/regions/<region>/addresses/<name>'"
    )
  return matches.group(1), matches.group(2), matches.group(3)


def audit_password(
    name: str, pwd: str, min_len: int, max_len: int, min_classes: int
) -> None:
  """Verifies password length bounds and category character class counts.

  Matches standard Carrot validation rules (ValidatePassword in validation.go).

  Args:
      name: Secret name string used in diagnostic exception logs.
      pwd: Plaintext password payload retrieved from Secret Manager.
      min_len: Minimum acceptable length threshold for the password string.
      max_len: Maximum acceptable length threshold (0 if unbounded).
      min_classes: Minimum required distinct character category classes.

  Raises:
      models.ValidationError: If string lengths or character categories fail.
  """
  length = len(pwd)
  if length < min_len or (max_len > 0 and length > max_len):
    raise models.ValidationError(
        f"Secret '{name}' fails length verification: length {length} not in"
        f" bounds [{min_len}, {max_len or 'unbounded'}]."
    )

  has_lower = any(c.islower() for c in pwd)
  has_upper = any(c.isupper() for c in pwd)
  has_digit = any(c.isdigit() for c in pwd)
  has_special = any(not c.isalnum() for c in pwd)
  class_count = sum([has_lower, has_upper, has_digit, has_special])

  if class_count < min_classes:
    raise models.ValidationError(
        f"Secret '{name}' fails complexity verification: required {min_classes}"
        f" character classes, found {class_count} classes."
    )
  if constants.PasswordResetDefaults.DEFAULT_ROOT_USER.lower() in pwd.lower():
    raise models.ValidationError(
        f"Secret '{name}' fails validation: ESXi password must not contain"
        " ESXi username."
    )


def parse_vcf_version_from_image(image_name: str) -> str:
  """Parses semantic VCF version from an ESXi boot disk image name string.

  Expected format: esxi-x-x-x-x-xxxxxxx or esxi-x-x-x-xxxxxxx (e.g.
  esxi-5-1-1-1-23395914 or esxi-5-1-1-23395914). Only the first three
  version components are used for the VCF version and installer OVA.

  Args:
      image_name: Raw boot disk image or OS template string name.

  Returns:
      Formatted semantic VCF version string using first 3 digits (e.g., '5.1.1').

  Raises:
      models.ValidationError: If image syntax is invalid or non-numeric.
  """
  clean_name = image_name.rstrip("/").split("/")[-1]
  match = ESXI_IMAGE_REGEX.match(clean_name)
  if not match:
    raise models.ValidationError(
        f"Invalid GCE image name '{image_name}': must match format"
        " 'esxi-x-x-x-<anything>', 'esxi-x-x-x-x-<anything>',"
        " 'vmware-esxi-x-x-x-<anything>', or"
        " 'vmware-esxi-x-x-x-x-<anything>'."
    )
  raw_version = match.group(1)
  parts = raw_version.split("-")
  version = ".".join(parts[:3])
  if not VCF_VERSION_REGEX.match(version):
    raise models.ValidationError(
        f"Invalid VCF version '{version}' parsed from image '{image_name}'"
    )
  logger.info("Parsed VCF version '%s' from boot image %s", version, clean_name)
  return version


def deconstruct_fqdn(fqdn: str) -> Tuple[str, str, str]:
  """Parses FQDN to isolate VM Name, Domain, and Searchpath via RFC 1123.

  Args:
      fqdn: Fully qualified domain name string (e.g. sddc-manager.vcf.internal).

  Returns:
      Tuple of (vm_name, domain, searchpath).

  Raises:
      models.ValidationError: If FQDN length or domain label syntax is invalid.
  """
  if not fqdn:
    raise models.ValidationError("Invalid FQDN: FQDN must not be empty.")
  clean_fqdn = str(fqdn).strip().rstrip(".")
  if not clean_fqdn or len(clean_fqdn) > constants.NetworkingDefaults.MAX_FQDN_LENGTH:
    raise models.ValidationError(f"Invalid FQDN length: '{fqdn}'")
  parts = clean_fqdn.split(".", 1)
  if len(parts) < 2:
    raise models.ValidationError(f"Invalid FQDN structure provided: '{fqdn}'")
  for label in clean_fqdn.split("."):
    if not label or not LABEL_REGEX.match(label):
      raise models.ValidationError(
          f"FQDN label '{label}' fails RFC 1123 conformance in '{fqdn}'"
      )
  vm_name, domain_and_search = parts[0], parts[1]
  logger.debug("Deconstructed FQDN '%s' -> VM: '%s'", clean_fqdn, vm_name)
  return vm_name, domain_and_search, domain_and_search


def extract_region_from_zone(zone_str: str) -> str:
  """Extracts GCP region from zone resource string or short name.

  Args:
      zone_str: Zone string or URI (e.g. 'us-central1-a' or
        'projects/p/zones/us-east4-b').

  Returns:
      GCP region string (e.g. 'us-central1' or 'us-east4').
  """
  clean = str(zone_str).rstrip("/").split("/")[-1]
  parts = clean.split("-")
  if len(parts) >= 3:
    return "-".join(parts[:-1])
  return clean


def select_optimal_ova_object(
    object_names: List[str], bucket: str, prefix: str
) -> str:
  """Parses object string listings to pick the .ova with highest build number.

  Args:
      object_names: Raw object filename strings fetched from storage repository.
      bucket: Origin bucket name for error attribution.
      prefix: Origin filtering prefix string for error attribution.

  Returns:
      Exact filename string of the optimal VCF installer OVA object.

  Raises:
      models.ValidationError: If no valid numeric build OVA exists in list.
  """
  best_name = ""
  max_build = -1
  found = False

  for name in object_names:
    if not name.endswith(".ova"):
      continue
    name_without_ext = name[:-4]
    idx = name_without_ext.rfind(".")
    if idx == -1:
      continue
    build_str = name_without_ext[idx + 1 :]
    try:
      build_num = int(build_str)
    except ValueError:
      continue

    if not found or build_num > max_build:
      max_build = build_num
      best_name = name
      found = True

  if found:
    logger.info("Selected optimal VCF installer OVA artifact: %s", best_name)
    return best_name

  raise models.ValidationError(
      f"No VCF installer OVA files found in bucket '{bucket}' matching prefix"
      f" '{prefix}'"
  )


def get_active_env() -> str:
  """Returns normalized active environment (prod, staging, autopush)."""
  return os.environ.get(
      constants.ValidationRules.OFFLINE_DEPOT_ENV_VAR,
      constants.ValidationRules.DEFAULT_OFFLINE_DEPOT_ENV,
  ).strip().lower()


def get_depot_host_template() -> str:
  """Returns the regional depot host template for the active environment."""
  env = get_active_env()
  return constants.ValidationRules.DEPOT_HOST_TEMPLATES.get(
      env, constants.ValidationRules.DEPOT_HOST_TEMPLATE
  )


def get_base_domain(region: str) -> str:
  """Returns the regional private DNS base domain for the active environment."""
  env = get_active_env()
  template = constants.OfflineDepotDefaults.BASE_DOMAIN_TEMPLATES.get(
      env, constants.OfflineDepotDefaults.BASE_DOMAIN_TEMPLATES["prod"]
  )
  return template.format(region=region)


def get_host_fqdn(region: str) -> str:
  """Returns the fully qualified domain name with trailing dot for the A-record."""
  env = get_active_env()
  template = constants.ValidationRules.DEPOT_HOST_TEMPLATES.get(
      env, constants.ValidationRules.DEPOT_HOST_TEMPLATE
  )
  host = template.format(region=region)
  return host if host.endswith(".") else f"{host}."


def get_service_attachment_uri(region: str) -> str:
  """Returns the regional Service Attachment URI for the active environment."""
  env = get_active_env()
  template = constants.OfflineDepotDefaults.SERVICE_ATTACHMENT_TEMPLATES.get(
      env, constants.OfflineDepotDefaults.SERVICE_ATTACHMENT_TEMPLATES["prod"]
  )
  return template.format(region=region)


def get_dns_zone_name(region: str) -> str:
  """Returns the managed DNS zone resource name for the active environment."""
  env = get_active_env()
  return constants.OfflineDepotDefaults.DNS_ZONE_NAME_TEMPLATE.format(
      region=region, env=env
  )
