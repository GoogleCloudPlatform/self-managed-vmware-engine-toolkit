"""Automated provisioner for Offline Depot PSC Endpoint and Private DNS.

Manages dedicated Subnetwork creation, Static Internal IP reservation with
PRIVATE_SERVICE_CONNECT purpose, Private Service Connect Forwarding Rule
creation, and environment-aware Cloud DNS Private Zone and A-record management.
"""

import logging
from typing import Dict, Optional

from clients import gcp_client
import constants
import models
from utils import network_utils
from utils import string_utils

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class OfflineDepotInfraManager:
  """Provisions all required GCP resources dynamically using CIDR and discovered VPC."""

  def __init__(
      self,
      config: models.DeployerConfig,
      gcp: gcp_client.GCPClient,
      vpc_network: str,
      cidr: str,
  ) -> None:
    """Initializes manager with master config, GCP client, VPC URI, and CIDR.

    Args:
        config: Loaded DeployerConfig dataclass.
        gcp: Initialized GCPClient instance.
        vpc_network: Resource URI of the customer VPC network.
        cidr: Subnet IPv4 CIDR range (e.g. '10.0.100.0/29').
    """
    self.config = config
    self.gcp = gcp
    self.vpc_network = vpc_network
    self.cidr = cidr

  def setup_offline_depot_infrastructure(self) -> Dict[str, str]:
    """Executes Steps 1-4 for offline depot PSC and private DNS connectivity.

    Returns:
        Dictionary containing provisioned/verified 'psc_ip', 'fqdn', and 'subnet_uri'.

    Raises:
        models.ValidationError: On invalid CIDR or configuration issues.
        models.DeployerError: On GCP provisioning failures.
    """
    if not self.cidr:
      logger.info("No offline depot CIDR specified; skipping PSC infrastructure setup.")
      return {}

    project = self.config.project
    region = self.config.region
    env = string_utils.get_active_env()

    logger.info("=" * 70)
    logger.info(
        "Automating Offline Depot PSC & DNS Setup [%s] in Region '%s'",
        env.upper(),
        region,
    )
    logger.info("=" * 70)

    # Step 1: Subnet Verification / Creation
    network_utils.validate_subnet_cidr_size(self.cidr)
    effective_subnet_name = (
        constants.OfflineDepotDefaults.SUBNET_NAME_TEMPLATE.format(
            region=region
        )
    )
    subnet_uri = self.gcp.create_offline_depot_subnetwork(
        project=project,
        region=region,
        name=effective_subnet_name,
        network=self.vpc_network,
        ip_cidr_range=self.cidr,
    )

    # Step 2a: Static Internal IP with purpose GCE_ENDPOINT
    ip_name = constants.OfflineDepotDefaults.PSC_IP_NAME_TEMPLATE.format(
        region=region
    )
    ip_link, psc_ip = self.gcp.reserve_psc_internal_ip(
        project=project, region=region, name=ip_name, subnet_uri=subnet_uri
    )

    # Step 2b: Forwarding Rule pointing to environment-specific Service Attachment
    svc_attachment = string_utils.get_service_attachment_uri(region)
    ep_name = (
        constants.OfflineDepotDefaults.PSC_FORWARDING_RULE_TEMPLATE.format(
            region=region
        )
    )
    self.gcp.create_offline_depot_forwarding_rule(
        project=project,
        region=region,
        name=ep_name,
        network=self.vpc_network,
        subnet_uri=subnet_uri,
        ip_address_link=ip_link,
        target_service_attachment=svc_attachment,
    )

    # Steps 3 & 4: Private DNS Zone (env-aware), VPC Network Binding & A-Record
    zone_name = string_utils.get_dns_zone_name(region)
    dns_base_domain = string_utils.get_base_domain(region)
    a_record_fqdn = string_utils.get_host_fqdn(region)

    self.gcp.create_offline_depot_private_dns_zone_and_record(
        project=project,
        zone_name=zone_name,
        dns_name=dns_base_domain,
        network_uri=self.vpc_network,
        a_record_fqdn=a_record_fqdn,
        target_ip=psc_ip,
        ttl=constants.OfflineDepotDefaults.DNS_RECORD_TTL_SECONDS,
    )

    logger.info(
        "Offline Depot PSC Endpoint [%s] ready: IP=%s, FQDN=%s (Cloud DNS private zone configured for VPC).",
        env.upper(),
        psc_ip,
        a_record_fqdn,
    )
    return {
        "psc_ip": psc_ip,
        "fqdn": a_record_fqdn,
        "subnet_uri": subnet_uri,
    }
