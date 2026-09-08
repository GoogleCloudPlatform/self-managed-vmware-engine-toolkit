"""Phase 1: Pre-Deployment Validation & Extraction module.

Performs operational inspections, external system state validation, secret
verification, image-based OVA discovery, and unified VLAN/CIDR routing
deduction utilizing stateless utility helpers and generic infrastructure
clients. Produces an immutable ValidationContext.
"""

import concurrent.futures
import ipaddress
import logging
import re
import secrets
import ssl
from typing import Dict, Optional, Tuple
import urllib.request

from clients import gcp_client as gcp_client_mod
import constants
import models
from utils import network_utils
from utils import string_utils
from vcf_deployer import offline_depot_infra

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class PreDeploymentValidator:
  """Executes Phase 1 pre-deployment verification gates and deduction."""

  def __init__(
      self,
      config: models.DeployerConfig,
      gcp: gcp_client_mod.GCPClient,
  ) -> None:
    """Initializes validator with target config document and GCP SDK client.

    Args:
        config: Parsed master configuration document from config.json.
        gcp: Initialized GCPClient wrapper.
    """
    self.config = config
    self.gcp = gcp

  def validate_and_extract(self) -> models.ValidationContext:
    """Master execution routine for Phase 1 pre-deployment validation.

    Performs a single inspection call per GCE node during initial checks,
    extracts and audits Secret Manager passwords via string utilities,
    governs node tags, infers VCF OVA download paths from boot disk images,
    and performs unified VLAN/CIDR routing deduction via network utilities.

    Returns:
        A frozen models.ValidationContext populated with verified variables.

    Raises:
        models.ValidationError: On non-conformance or config validation failure.
    """
    logger.info("Initiating Phase 1: Pre-Deployment Validation & Extraction...")

    # 1. Single-pass inspection of GCE nodes during initial check
    esxi_details_map = self._validate_gce_nodes()

    # 2. Extract and audit required secret payloads from Secret Manager
    root_pass, vcf_root, vcf_local = self._extract_and_audit_secrets()

    # 3. Govern mandatory compute node tags utilizing cached properties
    self._govern_gce_node_tags(esxi_details_map)

    # If optional VCF deployment profile is missing, skip VCF-specific checks
    vcf_cfg = self.config.vcf_deployment_config
    if not vcf_cfg:
      logger.info("No vcf_deployment_config provided; skipping VCF checks.")
      return models.ValidationContext(
          esxi_nodes=esxi_details_map,
          new_esxi_root_password=root_pass,
      )
    vcf_appliance_local_user = vcf_cfg.vcf_appliance_local_user

    # 4. Target ESXi host lookup from cache
    target_full_path = self.config.get_full_node_path(
        vcf_cfg.target_gce_node
    )
    clean_target_path = string_utils.clean_gcp_uri(target_full_path)
    target_details = esxi_details_map.get(clean_target_path)
    if not target_details:
      raise models.ValidationError(
          f"Designated target_gce_node '{vcf_cfg.target_gce_node}' not"
          " found in gce_nodes or missing valid internal IP."
      )

    # 4b. Provision / Verify Offline Depot Subnet, PSC Endpoint & Private DNS
    if not target_details.subnetworks:
      raise models.ValidationError(
          f"Target node '{target_details.instance_resource_string}' has no attached subnetworks to determine VPC network."
      )
    discovered_vpc = target_details.subnetworks[0].network_uri
    infra_mgr = offline_depot_infra.OfflineDepotInfraManager(
        config=self.config,
        gcp=self.gcp,
        vpc_network=discovered_vpc,
        cidr=vcf_cfg.offline_depot_subnet_cidr,
        subnet_name=vcf_cfg.offline_depot_subnet_name,
    )
    depot_infra = infra_mgr.setup_offline_depot_infrastructure()
    depot_ip = depot_infra.get("psc_ip") if depot_infra else None

    # 5. VCF OVA URL inference and SSL thumbprint extraction
    ova_url = self._derive_vcf_ova_url(target_details, depot_host_or_ip=depot_ip)

    # 5. Dynamic IP source resolution (forwarding rule or reserved address)
    if not vcf_cfg.vcf_installer_ip_source:
      raise models.ValidationError(
          "VCF deployment configuration missing required"
          " 'vcf_installer_ip_source'!"
      )
    vcf_ip = self.gcp.resolve_ip_source(
        vcf_cfg.vcf_installer_ip_source,
        default_project=self.config.project,
        default_region=self.config.region,
    )
    logger.info("Resolved VCF installer IP address: %s", vcf_ip)

    # 6. Unified extraction of VLAN ID, CIDR range, Gateway, and Netmask
    vlan_id, cidr, netmask, gateway = (
        network_utils.extract_vlan_cidr_and_routing(
            vcf_ip, target_details, self.gcp
        )
    )

    # 6. FQDN deconstruction into VM Name, Domain, and Searchpath
    vm_name, domain, searchpath = string_utils.deconstruct_fqdn(
        vcf_cfg.vcf_installer_fqdn
    )

    # 7. Port Group standardization with unique random suffix
    rand_suffix = secrets.token_hex(2)
    port_group = f"vlan-{vlan_id}-{rand_suffix}"

    # 8. Offline Depot SSL Thumbprint capture via HTTPS testing connection
    thumbprint = network_utils.capture_ssl_thumbprint(ova_url)

    # 9. Validate optional custom DNS server format if provided
    if vcf_cfg.dns_server:
      try:
        ipaddress.IPv4Address(vcf_cfg.dns_server.strip())
      except ValueError as exc:
        raise models.ValidationError(
            f"Invalid dns_server '{vcf_cfg.dns_server}': must be a valid IPv4"
            " address."
        ) from exc

    logger.info(
        "Phase 1 validation completed successfully (VLAN: %d, CIDR: %s).",
        vlan_id,
        cidr,
    )
    return models.ValidationContext(
        esxi_nodes=esxi_details_map,
        new_esxi_root_password=root_pass,
        target_esxi_ip=target_details.primary_ip,
        vcf_installer_ip=vcf_ip,
        vcf_installer_ova_url=ova_url,
        vlan_id=vlan_id,
        port_group_name=port_group,
        sddc_manager_netmask=netmask,
        sddc_manager_gateway=gateway,
        vcf_vm_name=vm_name,
        vcf_domain=domain,
        vcf_searchpath=searchpath,
        ssl_thumbprint=thumbprint,
        vcf_appliance_root_password=vcf_root,
        vcf_appliance_local_password=vcf_local,
        vcf_appliance_local_user=vcf_appliance_local_user,
        dns_server=vcf_cfg.dns_server,
    )

  def _inspect_single_node(
      self, node_input: str
  ) -> Tuple[str, models.GCEInstanceDetails]:
    """Inspects and validates a single GCE node."""
    full_node_path = self.config.get_full_node_path(node_input)
    details = self.gcp.get_instance_details(full_node_path)
    try:
      ipaddress.IPv4Address(details.primary_ip)
    except ValueError as exc:
      raise models.ValidationError(
          f"Node '{node_input}' returned malformed IPv4 address"
          f" '{details.primary_ip}': {exc}"
      ) from exc

    string_utils.parse_vcf_version_from_image(details.boot_image_name)

    clean_key = string_utils.clean_gcp_uri(full_node_path)
    logger.info(
        "Validated GCE node '%s' (IP: %s, Subnets: %d, Image: %s)",
        full_node_path,
        details.primary_ip,
        len(details.subnetworks),
        details.boot_image_name,
    )
    return clean_key, details

  def _validate_gce_nodes(self) -> Dict[str, models.GCEInstanceDetails]:
    """Executes single-pass inspection of all configured GCE nodes in parallel.

    Returns:
        Dictionary mapping node resource strings to cached
        GCEInstanceDetails.
    """
    logger.info("Performing single-pass initial inspection of GCE nodes...")
    nodes_list = self.gcp.resolve_gce_nodes(
        self.config.gce_nodes,
        project=self.config.project,
        zone=self.config.zone,
    )

    if not nodes_list:
      raise models.ValidationError(
          "gce_nodes in configuration profile is empty!"
      )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(
            constants.ValidationRules.MAX_INSPECTION_WORKERS,
            len(nodes_list),
        )
    ) as executor:
      return dict(executor.map(self._inspect_single_node, nodes_list))

  def _extract_and_audit_secrets(
      self,
  ) -> Tuple[str, Optional[str], Optional[str]]:
    """Reads secrets from Secret Manager and enforces password complexity rules.

    Returns:
        Tuple of (new_esxi_root, vcf_appliance_root, vcf_appliance_local).
    """
    logger.info("Extracting and auditing Secret Manager payloads...")
    esxi_root_secret_path = self.config.get_full_secret_path(
        self.config.esxi_root_password_secret
    )
    esxi_root = self.gcp.get_secret_payload(esxi_root_secret_path)
    string_utils.audit_password(
        "esxi_root_password",
        esxi_root,
        min_len=constants.ValidationRules.ESXI_ROOT_PASSWORD_MIN_LEN,
        max_len=constants.ValidationRules.ESXI_ROOT_PASSWORD_MAX_LEN,
        min_classes=constants.ValidationRules.ESXI_ROOT_PASSWORD_MIN_CLASSES,
    )

    vcf_root: Optional[str] = None
    vcf_local: Optional[str] = None

    if self.config.vcf_deployment_config:
      vcf_cfg = self.config.vcf_deployment_config
      vcf_root_path = self.config.get_full_secret_path(
          vcf_cfg.vcf_appliance_root_password_secret
      )
      vcf_root = self.gcp.get_secret_payload(vcf_root_path)
      string_utils.audit_password(
          "vcf_appliance_root_password",
          vcf_root,
          min_len=constants.ValidationRules.VCF_ROOT_PASSWORD_MIN_LEN,
          max_len=constants.ValidationRules.VCF_ROOT_PASSWORD_MAX_LEN,
          min_classes=constants.ValidationRules.VCF_ROOT_PASSWORD_MIN_CLASSES,
      )

      vcf_local_path = self.config.get_full_secret_path(
          vcf_cfg.vcf_appliance_local_user_password_secret
      )
      vcf_local = self.gcp.get_secret_payload(vcf_local_path)
      string_utils.audit_password(
          "vcf_local_user_password",
          vcf_local,
          min_len=constants.ValidationRules.VCF_LOCAL_PASSWORD_MIN_LEN,
          max_len=constants.ValidationRules.VCF_LOCAL_PASSWORD_MAX_LEN,
          min_classes=constants.ValidationRules.VCF_LOCAL_PASSWORD_MIN_CLASSES,
      )

    logger.info("Secret Manager payloads successfully validated and audited.")
    return esxi_root, vcf_root, vcf_local

  def _govern_single_node_tags(
      self, details: models.GCEInstanceDetails
  ) -> None:
    """Inspects and applies required tags and labels to a single node."""
    required_tags = set(constants.ValidationRules.REQUIRED_GCE_TAGS)
    required_labels = dict(constants.ValidationRules.REQUIRED_GCE_LABELS)

    # 1. Govern network tags
    missing_tags = required_tags - set(details.tags)
    if missing_tags:
      new_tags = sorted(list(set(details.tags) | required_tags))
      self.gcp.set_instance_tags(
          project=details.project,
          zone=details.zone,
          instance_name=details.short_name,
          new_tags=new_tags,
          fingerprint=details.tags_fingerprint,
      )
      details.tags = new_tags
    else:
      logger.info(
          "Node '%s' already contains required tags; skipping tag patch.",
          details.instance_resource_string,
      )

    # 2. Govern node labels
    missing_labels = {
        k: v for k, v in required_labels.items() if details.labels.get(k) != v
    }
    if missing_labels:
      new_labels = dict(details.labels)
      new_labels.update(required_labels)
      self.gcp.set_instance_labels(
          project=details.project,
          zone=details.zone,
          instance_name=details.short_name,
          new_labels=new_labels,
          label_fingerprint=details.label_fingerprint,
      )
      details.labels = new_labels
    else:
      logger.info(
          "Node '%s' already contains required labels; skipping label"
          " patch.",
          details.instance_resource_string,
      )

  def _govern_gce_node_tags(
      self, details_map: Dict[str, models.GCEInstanceDetails]
  ) -> None:
    """Inspects cached GCE node tags and labels, applying mandatory entries if missing in parallel.

    Args:
        details_map: Cached map of GCEInstanceDetails from initial inspection.
    """
    logger.info(
        "Governing GCE node networking tags and labels across inventory..."
    )
    if not details_map:
      return

    nodes = list(details_map.values())
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(
            constants.ValidationRules.MAX_TAG_GOVERNANCE_WORKERS,
            len(nodes),
        )
    ) as executor:
      list(executor.map(self._govern_single_node_tags, nodes))

  def _derive_vcf_ova_url(
      self,
      target_details: models.GCEInstanceDetails,
      depot_host_or_ip: Optional[str] = None,
  ) -> str:
    """Infers VCF installer OVA URL from regional offline depot server index.

    Args:
        target_details: Cached GCEInstanceDetails object for the target host.
        depot_host_or_ip: Optional specific IP or hostname for depot connections.

    Returns:
        Fully constructed HTTPS URL pointing to optimal OVA artifact.

    Raises:
        models.ValidationError: If index cannot be fetched or parsed.
    """
    vcf_version = string_utils.parse_vcf_version_from_image(
        target_details.boot_image_name
    )
    prefix = constants.ValidationRules.VCF_OVA_PREFIX_TEMPLATE.format(
        vcf_version=vcf_version
    )

    region = string_utils.extract_region_from_zone(target_details.zone)
    fqdn_host = string_utils.get_depot_host_template().format(
        region=region
    )
    depot_host = depot_host_or_ip or fqdn_host

    logger.info(
        "Deriving OVA URL for VCF version '%s' (prefix '%s') from offline depot"
        " server '%s' on target host '%s'...",
        vcf_version,
        prefix,
        depot_host,
        target_details.instance_resource_string,
    )

    index_url = (
        f"https://{depot_host}{constants.ValidationRules.DEPOT_INDEX_PATH}"
    )
    headers = {
        "Host": fqdn_host,
        "User-Agent": constants.VMDeployerDefaults.HTTP_USER_AGENT,
    }
    req = urllib.request.Request(index_url, headers=headers)

    try:
      ssl_ctx = ssl._create_unverified_context()
      with urllib.request.urlopen(
          req,
          context=ssl_ctx,
          timeout=constants.ValidationRules.DEPOT_INDEX_TIMEOUT_SECONDS,
      ) as resp:
        html_content = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
      raise models.ValidationError(
          "Failed to fetch OVA index from offline depot server at"
          f" '{index_url}': {exc}"
      ) from exc

    raw_ova_files = re.findall(
        constants.ValidationRules.HTML_OVA_HREF_PATTERN, html_content
    )
    if not raw_ova_files:
      raw_ova_files = re.findall(
          constants.ValidationRules.HTML_OVA_HREF_FALLBACK_PATTERN, html_content
      )

    matching_ova_files = [f for f in raw_ova_files if f.startswith(prefix)]

    if not matching_ova_files:
      raise models.ValidationError(
          f"No OVA files found matching prefix '{prefix}' in index from"
          f" offline depot server at '{index_url}'"
      )

    optimal_object = string_utils.select_optimal_ova_object(
        matching_ova_files, depot_host, prefix
    )

    ova_url = (
        f"https://{depot_host}{constants.ValidationRules.DEPOT_INDEX_PATH}{optimal_object}"
    )
    logger.info("Inferred VCF installer OVA URL: %s", ova_url)
    return ova_url
