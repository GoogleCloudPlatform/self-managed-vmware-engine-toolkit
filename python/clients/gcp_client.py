"""Google Cloud Platform (GCP) integration client.

Wraps Google Cloud APIs (Secret Manager, Compute Engine etc.)
utilizing ADC or custom service accounts to fetch and consolidate resource
telemetry cleanly without embedding service-specific domain processing.
"""

import ipaddress
import logging
import os
from typing import Any, List, Optional, Tuple

try:
  from google.api_core import exceptions as gcp_exceptions
  import google.auth
  from google.cloud import compute_v1
  from google.cloud import secretmanager
  from google.oauth2 import credentials as google_user_credentials
except ImportError:
  gcp_exceptions = None
  google = None
  google_user_credentials = None
  compute_v1 = None
  secretmanager = None

import constants
import models
from utils import string_utils

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class GCPClient:
  """Wrapper around GCP SDK clients for Secret Manager, Compute etc."""

  def __init__(self, require_explicit_auth: bool = False) -> None:
    """Initializes Google Cloud API clients using Application Default Credentials (ADC).

    Args:
        require_explicit_auth: If True, raises ValidationError if credentials
          are not strictly user credentials from 'gcloud auth
          application-default login'.
    """
    self._sm_client: Optional[Any] = None
    self._compute_client: Optional[Any] = None
    self._disks_client: Optional[Any] = None
    self._subnets_client: Optional[Any] = None
    self._fw_rules_client: Optional[Any] = None
    self._addresses_client: Optional[Any] = None

    c_version = os.environ.get(
        constants.GCPClientDefaults.COMPUTE_API_VERSION_ENV, ""
    ).strip().rstrip("/")
    if (
        c_version
        and c_version != constants.GCPClientDefaults.DEFAULT_COMPUTE_API_VERSION
    ):
      self._compute_api_version: Optional[str] = c_version
      self._install_api_version_rewriter()
    else:
      self._compute_api_version = None

    if require_explicit_auth:
      self.verify_explicit_credentials()
    logger.info(
        "Initialized GCPClient using Application Default Credentials (ADC)"
    )

  def _install_api_version_rewriter(self) -> None:
    """Hooks AuthorizedSession and requests.Session globally to redirect compute API version."""
    if not self._compute_api_version:
      return

    # Hook google.auth.transport.requests.AuthorizedSession
    if google is not None:
      try:
        from google.auth.transport import requests as auth_requests
        if getattr(auth_requests.AuthorizedSession, "_api_version_rewriter_installed", None) is not True:
          orig_auth_request = auth_requests.AuthorizedSession.request

          def versioned_auth_request(sess, method, url, *args, **kwargs):
            if isinstance(url, str) and "/compute/v1/" in url:
              url = url.replace("/compute/v1/", f"/compute/{self._compute_api_version}/")
            return orig_auth_request(sess, method, url, *args, **kwargs)

          auth_requests.AuthorizedSession.request = versioned_auth_request
          auth_requests.AuthorizedSession._api_version_rewriter_installed = True
      except Exception as exc:
        raise models.NonRetryableError(
            f"Failed to hook AuthorizedSession for Compute API version redirection: {exc}"
        ) from exc

    # Hook requests.Session
    try:
      import requests
      if getattr(requests.Session, "_api_version_rewriter_installed", None) is not True:
        orig_session_request = requests.Session.request

        def versioned_session_request(sess, method, url, *args, **kwargs):
          if isinstance(url, str) and "/compute/v1/" in url:
            url = url.replace("/compute/v1/", f"/compute/{self._compute_api_version}/")
          return orig_session_request(sess, method, url, *args, **kwargs)

        requests.Session.request = versioned_session_request
        requests.Session._api_version_rewriter_installed = True
    except Exception as exc:
      raise models.NonRetryableError(
          f"Failed to hook requests.Session for Compute API version redirection: {exc}"
      ) from exc

  def verify_explicit_credentials(self) -> None:
    """Verifies that user authentication is strictly from 'gcloud auth application-default login'."""
    if not google or not hasattr(google, "auth"):
      return
    try:
      credentials, _ = google.auth.default()
      if google_user_credentials and hasattr(
          google_user_credentials, "Credentials"
      ):
        if not isinstance(credentials, google_user_credentials.Credentials):
          raise models.ValidationError(
              "Execution using Service Account keys or GCE VM attached"
              " identity is disabled for auditing compliance. Each user must"
              " authenticate explicitly using 'gcloud auth"
              " application-default login'."
          )
      else:
        logger.warning("Credential type couldn't be determined.")
    except models.ValidationError:
      raise
    except Exception as exc:
      logger.warning("Could not verify credential origin: %s", exc)

  def _init_sm_client(self) -> None:
    """Instantiates SecretManagerServiceClient lazily."""
    if not secretmanager:
      raise models.NonRetryableError(
          "google-cloud-secret-manager package is not installed in interpreter."
      )
    self._sm_client = secretmanager.SecretManagerServiceClient()

  def _init_compute_client(self) -> None:
    """Instantiates Compute Engine InstancesClient lazily."""
    if not compute_v1:
      raise models.NonRetryableError(
          "google-cloud-compute package is not installed in interpreter."
      )
    self._compute_client = compute_v1.InstancesClient()

  def _init_disks_client(self) -> None:
    """Instantiates Compute Engine DisksClient lazily."""
    if not compute_v1:
      raise models.NonRetryableError(
          "google-cloud-compute package is not installed in interpreter."
      )
    self._disks_client = compute_v1.DisksClient()

  def _init_subnets_client(self) -> None:
    """Instantiates Compute Engine SubnetworksClient lazily."""
    if not compute_v1:
      raise models.NonRetryableError(
          "google-cloud-compute package is not installed in interpreter."
      )
    self._subnets_client = compute_v1.SubnetworksClient()

  def _init_fw_rules_client(self) -> None:
    """Instantiates Compute Engine ForwardingRulesClient lazily."""
    if not compute_v1:
      raise models.NonRetryableError(
          "google-cloud-compute package is not installed in interpreter."
      )
    self._fw_rules_client = compute_v1.ForwardingRulesClient()

  def _init_addresses_client(self) -> None:
    """Instantiates Compute Engine AddressesClient lazily."""
    if not compute_v1:
      raise models.NonRetryableError(
          "google-cloud-compute package is not installed in interpreter."
      )
    self._addresses_client = compute_v1.AddressesClient()

  def _handle_gcp_exception(
      self, operation: str, target: str, exc: Exception
  ) -> None:
    """Translates Google API status exceptions to structured DeployerErrors."""
    if isinstance(exc, (models.ValidationError, models.NonRetryableError)):
      raise exc
    if gcp_exceptions and isinstance(exc, gcp_exceptions.GoogleAPICallError):
      code = getattr(exc, "code", None)
      if code in constants.GCPClientDefaults.NON_RETRYABLE_HTTP_CODES:
        raise models.NonRetryableError(
            f"GCP Terminal Error [{code}] during {operation} on '{target}':"
            f" {exc.message}"
        ) from exc
      if code in constants.GCPClientDefaults.RETRYABLE_HTTP_CODES:
        raise models.RetryableError(
            f"GCP Transient Error [{code}] during {operation} on '{target}':"
            f" {exc.message}"
        ) from exc
    raise models.RetryableError(
        f"Unexpected operational fault during {operation} on '{target}': {exc}"
    ) from exc

  def _parse_instance_resource(self, resource_str: str) -> Tuple[str, str, str]:
    """Extracts project, zone, and instance name from resource URI string."""
    clean = string_utils.clean_gcp_uri(resource_str)
    parts = [p for p in clean.split("/") if p]
    if len(parts) >= 6 and parts[0] == "projects" and parts[2] == "zones":
      return parts[1], parts[3], parts[5]
    if len(parts) == 1:
      raise models.ValidationError(
          f"Instance identifier '{resource_str}' must include GCP project and"
          " zone (e.g., projects/<project>/zones/<zone>/instances/<name>)."
      )
    raise models.ValidationError(
        f"Malformed GCE instance resource string: '{resource_str}'"
    )

  def list_instances(
      self,
      project: str,
      zone: str,
      prefix: Optional[str] = None,
      subnet: Optional[str] = None,
  ) -> List[str]:
    """Lists and filters GCE instances in a project and zone by prefix and/or subnet.

    Args:
        project: GCP Project ID.
        zone: Compute Engine availability zone.
        prefix: Optional name prefix to filter instances.
        subnet: Optional subnetwork name or URI to filter instances.

    Returns:
        List of instance short names matching the filter criteria.
    """
    logger.debug(
        "Listing instances in %s/%s (prefix: %s, subnet: %s)...",
        project,
        zone,
        prefix,
        subnet,
    )
    if not self._compute_client:
      self._init_compute_client()
    try:
      instances = self._compute_client.list(project=project, zone=zone)
      matched_instances: List[str] = []
      for inst in instances:
        name = getattr(inst, "name", "")
        if prefix and not name.startswith(prefix):
          continue
        if subnet:
          clean_target_subnet = string_utils.clean_gcp_uri(subnet)
          target_sub_name = clean_target_subnet.rstrip("/").split("/")[-1]
          in_subnet = False
          for nic in getattr(inst, "network_interfaces", []) or []:
            raw_sub = getattr(nic, "subnetwork", "") or ""
            clean_sub = string_utils.clean_gcp_uri(raw_sub)
            sub_name = clean_sub.rstrip("/").split("/")[-1]
            if (
                clean_sub == clean_target_subnet
                or sub_name == target_sub_name
                or clean_sub.endswith(f"/subnetworks/{target_sub_name}")
            ):
              in_subnet = True
              break
          if not in_subnet:
            continue
        matched_instances.append(name)

      logger.info(
          "Discovered %d matching instance(s) in %s/%s for prefix='%s',"
          " subnet='%s': %s",
          len(matched_instances),
          project,
          zone,
          prefix,
          subnet,
          matched_instances,
      )
      return matched_instances
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception(
          "Compute List Instances", f"{project}/{zone}", exc
      )
      raise

  def resolve_gce_instances(
      self,
      instances_input: Any,
      project: str,
      zone: str,
  ) -> List[str]:
    """Resolves list of GCE instances from dynamic instances input.

    Supports:
    - List of instance names/URIs: ['esxi-1', 'esxi-2']
    - Dict with 'prefix' and/or 'subnet': {'prefix': 'esxi-', 'subnet': 'my-subnet'}
    - Single instance name string: 'esxi-1'

    Args:
        instances_input: List of instance names or dict containing 'prefix'
          and/or 'subnet'.
        project: GCP Project ID.
        zone: Compute Engine availability zone.

    Returns:
        List of resolved instance short names.

    Raises:
        models.ValidationError: If input format is invalid or returns no
          matching instances.
    """
    if not instances_input:
      raise models.ValidationError(
          "gce_instances in configuration profile is empty!"
      )

    if isinstance(instances_input, list):
      return list(instances_input)

    if isinstance(instances_input, dict):
      prefix = (
          str(instances_input["prefix"]).strip()
          if "prefix" in instances_input and instances_input["prefix"]
          else None
      )
      subnet = (
          str(instances_input["subnet"]).strip()
          if "subnet" in instances_input and instances_input["subnet"]
          else None
      )
      if not (prefix or subnet):
        raise models.ValidationError(
            "gce_instances dictionary must contain 'prefix' and/or 'subnet' key"
            " with non-empty values."
        )

      instances = self.list_instances(
          project=project, zone=zone, prefix=prefix, subnet=subnet
      )

      if not instances:
        raise models.ValidationError(
            f"No GCE instances found matching filter '{instances_input}' in"
            f" {project}/{zone}."
        )
      return instances

    if isinstance(instances_input, str):
      return [instances_input.strip()]

    raise models.ValidationError(
        f"Invalid gce_instances '{instances_input}': must be a list of instance"
        " names or a dictionary containing 'prefix' or 'subnet'."
    )

  def _parse_subnetwork_uri(self, subnetwork_uri: str) -> Tuple[str, str, str]:
    """Extracts project, region, and subnetwork resource name from URI."""
    clean = string_utils.clean_gcp_uri(subnetwork_uri)
    parts = [p for p in clean.split("/") if p]
    if (
        len(parts) >= 6
        and parts[0] == "projects"
        and parts[2] == "regions"
        and parts[4] == "subnetworks"
    ):
      return parts[1], parts[3], parts[5]
    raise models.ValidationError(
        f"Malformed subnetwork resource URI: '{subnetwork_uri}'"
    )

  def get_secret_payload(self, secret_version_path: str) -> str:
    """Retrieves a plaintext secret payload from GCP Secret Manager (read-only).

    Args:
        secret_version_path: Secret Manager resource path string. If no explicit
          version suffix is supplied, automatically defaults to
          '/versions/latest'.

    Returns:
        The decoded UTF-8 string payload of the requested secret.
    """
    path = str(secret_version_path).strip().rstrip("/")
    if "/versions/" not in path:
      path = f"{path}/{constants.GCPClientDefaults.DEFAULT_SECRET_VERSION}"

    logger.debug("Extracting secret payload from path: %s", path)
    if not self._sm_client:
      self._init_sm_client()
    try:
      response = self._sm_client.access_secret_version(  # type: ignore
          request={"name": path}
      )
      payload = response.payload.data.decode("utf-8").strip()
      if not payload:
        raise models.ValidationError(
            f"Secret Manager payload at '{path}' is empty!"
        )
      logger.debug("Successfully extracted secret from %s", path)
      return payload
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception("Secret Access", path, exc)
      raise

  def get_instance_details(
      self, instance_resource_string: str
  ) -> models.GCEInstanceDetails:
    """Performs single comprehensive GCE inspection during initial validation.

    Resolves primary internal IP, enumerates dynamic NICs with associated
    VLAN IDs, extracts tags, and resolves boot disk image name in one pass.

    Args:
        instance_resource_string: GCE instance name or full IAM URI.

    Returns:
        Cached GCEInstanceDetails object populated with all required metadata.
    """
    logger.debug(
        "Inspecting GCE instance details: %s", instance_resource_string
    )
    project, zone, instance_name = self._parse_instance_resource(
        instance_resource_string
    )
    if not self._compute_client:
      self._init_compute_client()
    try:
      inst = self._compute_client.get(  # type: ignore
          project=project, zone=zone, instance=instance_name
      )
      if not inst.network_interfaces:
        raise models.ValidationError(
            f"GCE instance '{instance_name}' has no network interfaces."
        )

      primary_nic = inst.network_interfaces[0]
      primary_ip = str(primary_nic.network_i_p)
      if not primary_ip or primary_ip == "None":
        raise models.ValidationError(
            f"GCE instance '{instance_name}' nic0 has no internal IPv4"
            " assigned."
        )

      clean_inst_str = string_utils.clean_gcp_uri(instance_resource_string)
      primary_nic_name = getattr(
          primary_nic, "name", constants.NetworkingDefaults.DEFAULT_PRIMARY_NIC
      )
      subnets: List[models.SubnetworkInfo] = [
          models.SubnetworkInfo(
              subnetwork_uri=string_utils.clean_gcp_uri(primary_nic.subnetwork),
              vlan_id=0,
              network_uri=string_utils.clean_gcp_uri(primary_nic.network),
          )
      ]

      for nic in inst.network_interfaces[1:]:
        parent = getattr(nic, "parent_nic_name", "")
        vlan = int(getattr(nic, "vlan", 0) or 0)
        if (parent == primary_nic_name or vlan > 0) and getattr(
            nic, "subnetwork", ""
        ):
          subnets.append(
              models.SubnetworkInfo(
                  subnetwork_uri=string_utils.clean_gcp_uri(nic.subnetwork),
                  vlan_id=vlan,
                  network_uri=string_utils.clean_gcp_uri(nic.network),
              )
          )

      tags = (
          list(inst.tags.items)
          if hasattr(inst, "tags")
          and inst.tags
          and hasattr(inst.tags, "items")
          and inst.tags.items
          else []
      )
      fingerprint = str(inst.tags.fingerprint) if inst.tags else ""
      labels = (
          dict(inst.labels) if hasattr(inst, "labels") and inst.labels else {}
      )
      label_fingerprint = str(getattr(inst, "label_fingerprint", ""))
      boot_image = self._resolve_boot_image_name(project, zone, inst)

      logger.info(
          "Resolved details for GCE instance '%s' (Primary IP: %s, Subnets: %d,"
          " Boot Image: %s).",
          clean_inst_str,
          primary_ip,
          len(subnets),
          boot_image,
      )
      return models.GCEInstanceDetails(
          instance_resource_string=clean_inst_str,
          short_name=instance_name,
          project=project,
          zone=zone,
          primary_ip=primary_ip,
          boot_image_name=boot_image,
          subnetworks=subnets,
          tags=tags,
          tags_fingerprint=fingerprint,
          labels=labels,
          label_fingerprint=label_fingerprint,
      )
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception("Compute Get", instance_resource_string, exc)
      raise

  def _resolve_boot_image_name(self, project: str, zone: str, inst: Any) -> str:
    """Helper method to resolve ESXi boot disk image name from instance object."""
    boot_disk_name = ""
    if inst.disks:
      for disk in inst.disks:
        if getattr(disk, "boot", False) or len(inst.disks) == 1:
          init_params = getattr(disk, "initialize_params", None)
          if init_params and getattr(init_params, "source_image", ""):
            return str(init_params.source_image).rstrip("/").split("/")[-1]
          src = getattr(disk, "source", "")
          if src:
            boot_disk_name = str(src).rstrip("/").split("/")[-1]
            break

    if not boot_disk_name:
      raise models.ValidationError(
          f"Instance '{inst.name}' missing boot disk definition in properties."
      )

    if not self._disks_client:
      self._init_disks_client()
    try:
      disk_obj = self._disks_client.get(  # type: ignore
          project=project, zone=zone, disk=boot_disk_name
      )
      src_img = getattr(disk_obj, "source_image", "")
      if not src_img:
        raise models.ValidationError(
            f"Boot disk '{boot_disk_name}' on '{inst.name}' lacks source_image."
        )
      return str(src_img).rstrip("/").split("/")[-1]
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception("Disk Get", boot_disk_name, exc)
      raise

  def fetch_subnetwork_cidr(self, subnetwork_uri: str) -> str:
    """Retrieves IP CIDR range associated with target GCE subnetwork URI.

    Args:
        subnetwork_uri: Full GCP subnetwork resource URI string.

    Returns:
        IPv4 CIDR range string (e.g., '10.140.20.0/24').
    """
    logger.debug("Fetching CIDR range for subnetwork: %s", subnetwork_uri)
    proj, reg, sub_name = self._parse_subnetwork_uri(subnetwork_uri)
    if not self._subnets_client:
      self._init_subnets_client()
    try:
      sub_resp = self._subnets_client.get(  # type: ignore
          project=proj, region=reg, subnetwork=sub_name
      )
      cidr = str(getattr(sub_resp, "ip_cidr_range", ""))
      if not cidr or cidr == "None":
        raise models.ValidationError(
            f"Subnetwork '{subnetwork_uri}' returned empty ip_cidr_range."
        )
      logger.debug("Resolved CIDR %s for subnetwork %s", cidr, sub_name)
      return cidr
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception("Subnetwork Get", subnetwork_uri, exc)
      raise

  def set_instance_tags(
      self,
      project: str,
      zone: str,
      instance_name: str,
      new_tags: List[str],
      fingerprint: str,
  ) -> None:
    """Applies updated tag set to compute instance via set_tags operation.

    Args:
        project: GCP Project ID.
        zone: Compute engine availability zone.
        instance_name: Short GCE resource instance name.
        new_tags: Consolidated list of tags to apply to the instance.
        fingerprint: Optimistic locking fingerprint from initial GET inspection.
    """
    if not self._compute_client:
      self._init_compute_client()
    try:
      logger.info(
          "Applying updated tags %s to instance '%s'...",
          new_tags,
          instance_name,
      )
      tags_res = compute_v1.Tags(items=new_tags, fingerprint=fingerprint)
      op = self._compute_client.set_tags(  # type: ignore
          project=project,
          zone=zone,
          instance=instance_name,
          tags_resource=tags_res,
      )
      op.result(
          timeout=constants.GCPClientDefaults.OPERATION_TIMEOUT_SECONDS
      )
      logger.info("Successfully updated tags for instance '%s'.", instance_name)
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception("Compute Set Tags", instance_name, exc)
      raise

  def set_instance_labels(
      self,
      project: str,
      zone: str,
      instance_name: str,
      new_labels: Any,
      label_fingerprint: str,
  ) -> None:
    """Applies updated labels dictionary to compute instance via set_labels operation.

    Args:
        project: GCP Project ID.
        zone: Compute engine availability zone.
        instance_name: Short GCE resource instance name.
        new_labels: Dict of key-value string label pairs to apply to instance.
        label_fingerprint: Optimistic locking label fingerprint from initial
          GET.
    """
    if not self._compute_client:
      self._init_compute_client()
    try:
      logger.info(
          "Applying updated labels %s to instance '%s'...",
          new_labels,
          instance_name,
      )
      labels_req = compute_v1.InstancesSetLabelsRequest(
          label_fingerprint=label_fingerprint, labels=new_labels
      )
      op = self._compute_client.set_labels(  # type: ignore
          project=project,
          zone=zone,
          instance=instance_name,
          instances_set_labels_request_resource=labels_req,
      )
      op.result(
          timeout=constants.GCPClientDefaults.OPERATION_TIMEOUT_SECONDS
      )
      logger.info(
          "Successfully updated labels for instance '%s'.", instance_name
      )
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception("Compute Set Labels", instance_name, exc)
      raise

  def get_forwarding_rule_ip(self, project: str, region: str, name: str) -> str:
    """Resolves IP address from a GCP Compute Engine Forwarding Rule.

    If the forwarding rule references a reserved Address resource URI, performs
    a secondary lookup to resolve the underlying IP address.

    Args:
        project: GCP Project ID.
        region: GCP Region name.
        name: Resource name of the forwarding rule.

    Returns:
        Resolved IPv4 address string.

    Raises:
        models.ValidationError: If IP address is empty or resource invalid.
    """
    logger.debug(
        "Resolving IP address for forwarding rule '%s' in %s/%s...",
        name,
        project,
        region,
    )
    if not self._fw_rules_client:
      self._init_fw_rules_client()
    try:
      fw_rule = self._fw_rules_client.get(  # type: ignore
          project=project, region=region, forwarding_rule=name
      )
      ip = ""
      if hasattr(fw_rule, "I_p_address") and fw_rule.I_p_address:
        ip = str(fw_rule.I_p_address)
      elif hasattr(fw_rule, "ip_address") and fw_rule.ip_address:
        ip = str(fw_rule.ip_address)

      if "/addresses/" in ip:
        proj, loc, addr_name = string_utils.parse_address_path(ip)
        return self.get_reserved_address_ip(proj, loc, addr_name)

      if not ip or ip == "None":
        raise models.ValidationError(
            f"Forwarding rule '{name}' in project '{project}' region '{region}'"
            " has no IP address assigned!"
        )
      return ip
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception(
          "Forwarding Rule Get", f"{project}/{region}/{name}", exc
      )
      raise

  def get_reserved_address_ip(
      self, project: str, region: str, name: str
  ) -> str:
    """Resolves IP address from a GCP Compute Engine Reserved Address resource.

    Args:
        project: GCP Project ID.
        region: GCP Region name.
        name: Resource name of the reserved address.

    Returns:
        Resolved IPv4 address string.

    Raises:
        models.ValidationError: If IP address is empty or resource invalid.
    """
    logger.debug(
        "Resolving IP address for reserved address '%s' in %s/%s...",
        name,
        project,
        region,
    )
    if not self._addresses_client:
      self._init_addresses_client()
    try:
      addr_obj = self._addresses_client.get(  # type: ignore
          project=project, region=region, address=name
      )
      ip = str(getattr(addr_obj, "address", ""))
      if not ip or ip == "None":
        raise models.ValidationError(
            f"Reserved address '{name}' in project '{project}' region"
            f" '{region}' is empty!"
        )
      return ip
    except Exception as exc:  # pylint: disable=broad-exception-caught
      self._handle_gcp_exception(
          "Reserved Address Get", f"{project}/{region}/{name}", exc
      )
      raise

  def resolve_ip_source(
      self,
      ip_source_input: Any,
      default_project: Optional[str] = None,
      default_region: Optional[str] = None,
  ) -> str:
    """Resolves VCF installer IPv4 address from dynamic GCP IP source.

    Supports:
    - Forwarding rule resource path
      ('projects/<p>/regions/<r>/forwardingRules/<name>')
    - Reserved address resource path
      ('projects/<p>/regions/<r>/addresses/<name>')
    - Short resource names with default_project & default_region
    - Structured dict ({'forwarding_rule': '...'} or {'reserved_address':
      '...'})

    Args:
        ip_source_input: Raw configuration input value for IP source.
        default_project: Optional GCP project ID to validate matching boundaries
          and construct full paths from short names.
        default_region: Optional GCP region name to construct full paths from
          short names.

    Returns:
        Verified IPv4 address string.

    Raises:
        models.ValidationError: If IP source is not a valid forwarding rule or
          reserved address.
    """
    if not ip_source_input:
      raise models.ValidationError("VCF installer IP source is required!")

    target_path = ""
    source_type = ""

    if isinstance(ip_source_input, dict):
      if (
          constants.VCFConfigKeys.FORWARDING_RULE in ip_source_input
          and ip_source_input[constants.VCFConfigKeys.FORWARDING_RULE]
      ):
        target_path = str(
            ip_source_input[constants.VCFConfigKeys.FORWARDING_RULE]
        ).strip()
        source_type = constants.VCFConfigKeys.FORWARDING_RULE
      elif (
          constants.VCFConfigKeys.RESERVED_ADDRESS in ip_source_input
          and ip_source_input[constants.VCFConfigKeys.RESERVED_ADDRESS]
      ):
        target_path = str(
            ip_source_input[constants.VCFConfigKeys.RESERVED_ADDRESS]
        ).strip()
        source_type = constants.VCFConfigKeys.RESERVED_ADDRESS
      else:
        raise models.ValidationError(
            f"vcf_installer_ip_source dictionary must contain"
            f" '{constants.VCFConfigKeys.FORWARDING_RULE}' or"
            f" '{constants.VCFConfigKeys.RESERVED_ADDRESS}' key."
        )
    elif isinstance(ip_source_input, str):
      target_path = ip_source_input.strip()
      if string_utils.FORWARDING_RULE_REGEX.search(target_path):
        source_type = "forwarding_rule"
      elif string_utils.ADDRESS_REGEX.search(target_path):
        source_type = "reserved_address"
      else:
        raise models.ValidationError(
            f"Invalid vcf_installer_ip_source '{ip_source_input}': string input"
            " must be a full forwarding rule URI"
            " ('projects/.../regions/.../forwardingRules/<name>') or full"
            " reserved address URI"
            " ('projects/.../regions/.../addresses/<name>'). For short names,"
            " provide a dictionary with 'forwarding_rule' or 'reserved_address'."
        )
    else:
      raise models.ValidationError(
          f"Invalid vcf_installer_ip_source format '{type(ip_source_input)}':"
          " expected dict or str."
      )

    if (
        not target_path.startswith("projects/")
        and default_project
        and default_region
    ):
      if source_type == "forwarding_rule":
        target_path = f"projects/{default_project}/regions/{default_region}/forwardingRules/{target_path}"
      elif source_type == "reserved_address":
        target_path = f"projects/{default_project}/regions/{default_region}/addresses/{target_path}"

    if source_type == "forwarding_rule":
      proj, reg, name = string_utils.parse_forwarding_rule_path(target_path)
      if default_project and proj != default_project:
        raise models.ValidationError(
            f"Forwarding rule project '{proj}' does not match target instance"
            f" project '{default_project}'!"
        )
      ip_str = self.get_forwarding_rule_ip(proj, reg, name)
    else:
      proj, reg, name = string_utils.parse_address_path(target_path)
      if default_project and proj != default_project:
        raise models.ValidationError(
            f"Reserved address project '{proj}' does not match target instance"
            f" project '{default_project}'!"
        )
      ip_str = self.get_reserved_address_ip(proj, reg, name)

    try:
      ipaddress.IPv4Address(ip_str)
    except ValueError as exc:
      raise models.ValidationError(
          f"Resolved IP '{ip_str}' from IP source '{ip_source_input}' is not a"
          f" valid IPv4 address: {exc}"
      ) from exc

    return ip_str
