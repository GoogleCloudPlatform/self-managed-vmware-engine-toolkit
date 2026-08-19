"""Client-independent network routing and SSL socket inspection utilities.

Provides stateless domain helper routines for unified VLAN/CIDR routing
deduction across primary and dynamic alias interfaces, GCP reserved address
validation, and remote SSL SHA-256 certificate fingerprint capture.
"""

import hashlib
import ipaddress
import logging
import socket
import ssl
from typing import Any, Tuple

import constants
import models

logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


def extract_vlan_cidr_and_routing(
    vcf_ip: str, target_details: models.GCEInstanceDetails, gcp_client: Any
) -> Tuple[int, str, str, str]:
  """Unified extraction of VLAN ID, CIDR range, Gateway, and Netmask in one call.

  Evaluates primary NIC (VLAN 0) and dynamic alias NICs attached to the
  primary interface. Identifies enclosing subnetwork CIDR, verifies IP is not
  a reserved GCP address, and derives gateway and subnet mask simultaneously.

  Args:
      vcf_ip: Configured VCF installer static IPv4 address.
      target_details: Cached GCEInstanceDetails for the target ESXi host.
      gcp_client: Initialized GCPClient to query subnet CIDRs if unpopulated.

  Returns:
      Tuple of (vlan_id, cidr_range, netmask, gateway_ip).

  Raises:
      models.ValidationError: If IP syntax is malformed or unreachable.
  """
  logger.info(
      "Performing unified VLAN/CIDR and routing extraction for IP %s against"
      " host '%s'...",
      vcf_ip,
      target_details.instance_resource_string,
  )
  try:
    target_addr = ipaddress.IPv4Address(vcf_ip)
  except ValueError as exc:
    raise models.ValidationError(
        f"Configured vcf_installer_ip '{vcf_ip}' is not valid IPv4: {exc}"
    ) from exc

  for subnet_info in target_details.subnetworks:
    if not subnet_info.cidr:
      subnet_info.cidr = gcp_client.fetch_subnetwork_cidr(
          subnet_info.subnetwork_uri
      )

    cidr = subnet_info.cidr
    try:
      net = ipaddress.IPv4Network(cidr, strict=False)
    except ValueError:
      continue

    if target_addr in net:
      # Check GCP reserved addresses (first two and last two IPs in block)
      network_ip = net.network_address
      gateway_ip = net.network_address + 1
      broadcast_ip = net.broadcast_address
      second_to_last = net.broadcast_address - 1

      if target_addr in (
          network_ip,
          gateway_ip,
          broadcast_ip,
          second_to_last,
      ):
        raise models.ValidationError(
            f"VCF installer IP '{vcf_ip}' falls on a reserved GCP subnetwork"
            f" address in CIDR '{cidr}'!"
        )

      vlan_id = subnet_info.vlan_id  # 0 for primary NIC, >0 for dynamic NICs
      netmask = str(net.netmask)
      gateway = str(gateway_ip)

      logger.info(
          "Subnet containment verified: IP %s matched CIDR %s -> VLAN ID: %d,"
          " Netmask: %s, Gateway: %s.",
          vcf_ip,
          cidr,
          vlan_id,
          netmask,
          gateway,
      )
      return vlan_id, cidr, netmask, gateway

  raise models.ValidationError(
      f"Configured VCF installer IP '{vcf_ip}' does not fall within any primary"
      " or dynamic NIC subnetwork ranges attached to target host"
      f" '{target_details.instance_resource_string}'!"
  )


def capture_ssl_thumbprint(target_url: str) -> str:
  """Opens HTTPS socket connection to target host port 443 to capture SHA-256 hash.

  Args:
      target_url: HTTPS web domain or URL string of OVA depot distribution host.

  Returns:
      Colon-separated SHA-256 hexadecimal certificate thumbprint.

  Raises:
      models.ValidationError: If no SSL certificate is returned by server.
      models.RetryableError: If network socket connection fails or times out.
  """
  hostname = (
      target_url.replace("https://", "")
      .replace("http://", "")
      .split("/")[0]
      .split(":")[0]
  )
  logger.info(
      "Connecting to %s:%d to capture SSL SHA-256 thumbprint...",
      hostname,
      constants.NetworkingDefaults.HTTPS_PORT,
  )
  try:
    if hasattr(ssl, "_create_unverified_context"):
      ctx = ssl._create_unverified_context()
    else:
      ctx = ssl.create_default_context()
      ctx.check_hostname = False
      ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection(
        (hostname, constants.NetworkingDefaults.HTTPS_PORT),
        timeout=constants.NetworkingDefaults.SSL_TIMEOUT_SECONDS,
    ) as sock:
      with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
        cert_der = ssock.getpeercert(binary_form=True)
        if not cert_der:
          raise models.ValidationError(
              f"No SSL certificate returned by server '{hostname}:443'."
          )
        sha256_hash = hashlib.sha256(cert_der).hexdigest().upper()
        thumbprint = ":".join(
            sha256_hash[i : i + 2] for i in range(0, len(sha256_hash), 2)
        )
        logger.info("Captured SSL thumbprint for %s: %s", hostname, thumbprint)
        return thumbprint
  except Exception as exc:  # pylint: disable=broad-exception-caught
    if isinstance(exc, models.ValidationError):
      raise exc
    raise models.RetryableError(
        f"Failed to connect to '{hostname}:443' to capture SSL SHA-256"
        f" thumbprint: {exc}"
    ) from exc
