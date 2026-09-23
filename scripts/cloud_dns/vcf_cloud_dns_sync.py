#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
VMware Cloud Foundation (VCF) on Google Cloud Engine - Cloud DNS Automator

Automates the non-Terraform Cloud DNS & NTP setup workflow:
  1. Enables Cloud DNS API (dns.googleapis.com)
  2. Ensures a Cloud DNS Policy (with default settings) is attached to the VPC
  3. Ensures Private Forward & Reverse Lookup Zones exist and are bound to the VPC
  4. Synchronizes Forward (A) and Reverse (PTR) DNS records for Z3 bare-metal nodes
     and management-subnet internal load balancer frontends (stripping '-fr' and
     skipping IP-only NSX TEP/uplink subnet load balancers)
  5. Manages NTP DNS record lifecycle (pre-validation IP vs. post-validation 169.254.169.254)

================================================================================
USAGE & INVOCATION SCENARIOS
================================================================================

Note: If you already ran `gcloud config set project PROJECT_ID`, `--project-id`
can be omitted from all commands below.

1. Dry-Run / Preview Mode (No Changes Applied)
   Preview which zones, DNS policies, and A/PTR records will be created or updated:
     python3 vcf_cloud_dns_sync.py \
       --project-id PROJECT_ID \
       --vpc-network VPC_NETWORK_NAME \
       --domain smve.test \
       --sync-all \
       --set-ntp-ip 10.254.254.250 \
       --dry-run

2. Full Day-0 Initial Setup (Before VCF Installer Validation)
   Run after provisioning VPC, subnets, Z3 bare-metal instances, NEGs, and
   internal load balancer forwarding rules in the UI, and BEFORE running VCF
   Installer validation. Automatically enables the DNS API, creates the VPC DNS
   policy, creates private forward & /16 or /8 reverse zones (from non-NSX
   subnets), registers all node and management frontend A/PTR records (skipping
   NSX subnet load balancers), and sets ntp.<domain> to a non-link-local IP:
     python3 vcf_cloud_dns_sync.py \
       --project-id PROJECT_ID \
       --vpc-network VPC_NETWORK_NAME \
       --domain smve.test \
       --sync-all \
       --set-ntp-ip 10.254.254.250

3. Post-Validation NTP Cutover (Once Management Domain Bringup Starts)
   Once VCF Installer validation passes and management domain installation begins,
   point ntp.<domain> back to the GCE metadata server (169.254.169.254):
     python3 vcf_cloud_dns_sync.py \
       --project-id PROJECT_ID \
       --vpc-network VPC_NETWORK_NAME \
       --domain smve.test \
       --set-ntp-ip 169.254.169.254

4. Day-2 Scale-Out (Adding New Z3 Hosts or Workload Domain Frontends)
   After adding new Z3 bare-metal hosts or internal forwarding rules in the UI,
   re-run `--sync-all` (unchanged records are skipped automatically):
     python3 vcf_cloud_dns_sync.py \
       --project-id PROJECT_ID \
       --vpc-network VPC_NETWORK_NAME \
       --domain smve.test \
       --sync-all

5. Bootstrap Zones & VPC Policy Only (Before Creating Nodes/Frontends)
   Enable Cloud DNS API, create the VPC DNS Policy, and create Forward/Reverse
   zones ahead of compute provisioning:
     python3 vcf_cloud_dns_sync.py \
       --project-id PROJECT_ID \
       --vpc-network VPC_NETWORK_NAME \
       --domain smve.test \
       --reverse-zone smve-rev-10-10=10.10.0.0/16 \
       --setup-zones

6. Custom Zone / Policy Names or Pre-Created Admin Resources
   Override default resource names or specify custom reverse zone CIDRs:
     python3 vcf_cloud_dns_sync.py \
       --project-id PROJECT_ID \
       --vpc-network VPC_NETWORK_NAME \
       --domain smve.test \
       --dns-policy my-custom-dns-policy \
       --forward-zone my-custom-fwd-zone \
       --reverse-zones my-rev-zone-1=10.10.1.0/24 my-rev-zone-2=10.10.2.0/24 \
       --sync-all \
       --set-ntp-ip 10.254.254.250
   - Pass `--no-create-dns-policy` to skip creating the VPC-level Cloud DNS policy
     (e.g. when the VPC policy is centrally managed or already configured).
   - Pass `--no-create-zones` (along with `--reverse-zones <zone1> <zone2>`) to skip
     creating forward/reverse Cloud DNS managed zones when zones are pre-provisioned
     by an administrator.
================================================================================
"""

import argparse
import ipaddress
import json
import logging
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VCF-DNS-Sync")


class GcloudError(RuntimeError):
    """Raised when a gcloud command fails."""


def run_gcloud(cmd: List[str], parse_json: bool = True, allow_not_found: bool = False) -> Any:
    """Executes a gcloud command and optionally parses JSON output."""
    full_cmd = list(cmd)
    if parse_json and not any(arg.startswith("--format") for arg in full_cmd):
        full_cmd.append("--format=json")

    try:
        result = subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
        if not parse_json:
            return result.stdout.strip()
        return json.loads(result.stdout) if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        if allow_not_found and ("was not found" in stderr or "HTTPError 404" in stderr or "NOT_FOUND" in stderr):
            return None
        logger.error(f"gcloud command failed: {' '.join(full_cmd)}")
        logger.error(f"Error output: {stderr}")
        raise GcloudError(stderr) from e
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from gcloud command: {' '.join(full_cmd)}")
        raise GcloudError("Invalid JSON output from gcloud") from e


def get_default_project() -> Optional[str]:
    """Reads the active project from `gcloud config get-value project`."""
    try:
        proj = run_gcloud(["gcloud", "config", "get-value", "project"], parse_json=False)
        if proj and proj != "(unset)":
            return proj
    except GcloudError:
        pass
    return None


def ip_to_reverse_ptr(ip: str) -> str:
    """Converts an IPv4 address to in-addr.arpa. PTR notation."""
    octets = ip.strip().split(".")
    if len(octets) == 4:
        return f"{octets[3]}.{octets[2]}.{octets[1]}.{octets[0]}.in-addr.arpa."
    raise ValueError(f"Invalid IPv4 address: {ip}")


def cidr_to_reverse_dns_name(cidr_or_suffix: str) -> str:
    """
    Converts an IPv4 CIDR (e.g. '10.10.0.0/16') or reverse zone suffix
    (e.g. '10.10.in-addr.arpa') into a trailing-dot reverse zone dnsName.
    """
    val = cidr_or_suffix.strip()
    if val.endswith(".in-addr.arpa") or val.endswith(".in-addr.arpa."):
        return val.rstrip(".") + "."

    net = ipaddress.ip_network(val, strict=False)
    if net.version != 4:
        raise ValueError(f"Only IPv4 CIDRs are supported for reverse zones: {val}")

    octets = str(net.network_address).split(".")
    if net.prefixlen >= 24:
        rev_octets = [octets[2], octets[1], octets[0]]
    elif net.prefixlen >= 16:
        rev_octets = [octets[1], octets[0]]
    else:
        rev_octets = [octets[0]]
    return ".".join(rev_octets) + ".in-addr.arpa."


def normalize_fqdn(name: str, domain: str) -> str:
    """
    Ensures FQDN has the target domain suffix and a trailing dot.
    Raises ValueError if `name` contains a node domain that does not match `domain`.
    """
    clean_domain = domain.strip(".").lower()
    clean_name = name.strip(".").lower()

    # If hostname includes a domain, verify the node domain matches the input domain
    if "." in clean_name:
        _, node_domain = clean_name.split(".", 1)
        if node_domain != clean_domain:
            raise ValueError(
                f"Node domain '{node_domain}' in hostname '{clean_name}' does not match input domain '{clean_domain}'."
            )
        return f"{clean_name}."

    return f"{clean_name}.{clean_domain}."


def strip_frontend_suffix(name: str) -> str:
    """
    Removes the '-fr' suffix from forwarding rule names
    without corrupting substrings like 'vcf-fra-01' or 'vcf-frontend'.
    """
    if name.endswith("-fr"):
        return name[:-3]
    return name


class VcfDnsManager:
    def __init__(
        self,
        project_id: str,
        vpc_network: str,
        domain_name: str,
        forward_zone: Optional[str] = None,
        reverse_zones: Optional[List[str]] = None,
        dns_policy: Optional[str] = None,
        ttl: int = 300,
        create_missing_zones: bool = True,
        create_dns_policy: bool = True,
        dry_run: bool = False,
    ):
        self.project_id = project_id
        # Normalize VPC network in case a full resource URL was provided
        self.vpc_network = vpc_network.rstrip("/").split("/")[-1]
        self.domain_name = domain_name.strip(".")
        # Default forward zone and DNS policy names if not explicitly provided
        self.forward_zone = forward_zone or f"{self.vpc_network}-forward-zone"
        self._forward_zone_explicit = bool(forward_zone)
        self.dns_policy = dns_policy or f"{self.vpc_network}-dns-policy"
        self.reverse_zones_input = reverse_zones or []
        self.reverse_zones: List[str] = []
        self.ttl = ttl
        self.create_missing_zones = create_missing_zones
        self.create_dns_policy = create_dns_policy
        self.dry_run = dry_run

        self._zone_dns_names: Dict[str, str] = {}
        self._cached_records: Dict[Tuple[str, str, str], List[str]] = {}
        self._seen_in_run: Dict[Tuple[str, str, str], str] = {}
        self._mgmt_subnets: Set[str] = set()

        if self.create_missing_zones or self.create_dns_policy:
            self._enable_dns_api()
        if self.create_dns_policy:
            self._ensure_dns_policy()

        self._ensure_and_load_zones()
        self._preload_existing_records()

    def _enable_dns_api(self):
        """Step 1: Enable the Cloud DNS API (dns.googleapis.com)."""
        logger.info("Ensuring Cloud DNS API (dns.googleapis.com) is enabled...")
        cmd = [
            "gcloud", "services", "enable", "dns.googleapis.com",
            f"--project={self.project_id}",
            "--quiet",
        ]
        if self.dry_run:
            logger.info(f"  [DRY-RUN] Would run: {' '.join(cmd)}")
        else:
            run_gcloud(cmd, parse_json=False)

    def _ensure_dns_policy(self):
        """Ensures a Cloud DNS policy with default settings is attached to self.vpc_network."""
        logger.info(f"Checking Cloud DNS policy for VPC '{self.vpc_network}'...")
        policies = run_gcloud([
            "gcloud", "dns", "policies", "list",
            f"--project={self.project_id}",
        ])

        for pol in policies:
            pol_name = pol.get("name", "")
            for net in pol.get("networks", []):
                net_url = net.get("networkUrl", "")
                if net_url.rstrip("/").split("/")[-1] == self.vpc_network:
                    logger.info(
                        f"  ⏭️  SKIPPED (Already exists): DNS Policy '{pol_name}' is already bound to VPC '{self.vpc_network}'"
                    )
                    self.dns_policy = pol_name
                    return

        cmd = [
            "gcloud", "dns", "policies", "create", self.dns_policy,
            f"--description=Default Cloud DNS policy for VPC {self.vpc_network}",
            f"--networks={self.vpc_network}",
            f"--project={self.project_id}",
            "--quiet",
        ]
        if self.dry_run:
            logger.info(
                f"  [DRY-RUN] ➕ CREATING DNS Policy '{self.dns_policy}' bound to VPC '{self.vpc_network}' (default settings)"
            )
        else:
            logger.info(
                f"  ➕ CREATING DNS Policy '{self.dns_policy}' bound to VPC '{self.vpc_network}' (default settings)"
            )
            run_gcloud(cmd, parse_json=False)

    def _create_private_zone(self, zone_name: str, dns_name: str, description: str):
        """Creates a private Cloud DNS managed zone bound to self.vpc_network."""
        dns_name_dot = dns_name.rstrip(".") + "."
        cmd = [
            "gcloud", "dns", "managed-zones", "create", zone_name,
            f"--dns-name={dns_name_dot}",
            f"--description={description}",
            "--visibility=private",
            f"--networks={self.vpc_network}",
            f"--project={self.project_id}",
            "--quiet",
        ]
        if self.dry_run:
            logger.info(
                f"  [DRY-RUN] ➕ CREATING Zone '{zone_name}' (dnsName: {dns_name_dot}, VPC: {self.vpc_network})"
            )
            self._zone_dns_names[zone_name] = dns_name_dot
        else:
            logger.info(
                f"  ➕ CREATING Zone '{zone_name}' (dnsName: {dns_name_dot}, VPC: {self.vpc_network})"
            )
            run_gcloud(cmd, parse_json=False)
            self._zone_dns_names[zone_name] = dns_name_dot

    def _zone_bound_to_vpc(self, zone_obj: Dict[str, Any]) -> bool:
        """Returns True if a managed-zone JSON object is bound to self.vpc_network."""
        priv_cfg = zone_obj.get("privateVisibilityConfig", {})
        for net in priv_cfg.get("networks", []):
            net_url = net.get("networkUrl", "")
            if net_url.rstrip("/").split("/")[-1] == self.vpc_network:
                return True
        return False

    def _ensure_and_load_zones(self):
        """
        Steps 2 & 3: Ensures forward and reverse Cloud DNS zones are ready.
        - For reverse zones:
          * When create_missing_zones is True: directly creates reverse zones
            (dynamically from VPC non-NSX subnets if --reverse-zones is omitted,
            or from the provided --reverse-zones) without checking if they already exist.
          * When create_missing_zones is False (--no-create-zones): requires the user
            to provide existing reverse zone names via --reverse-zones and loads them
            for creating PTR records later.
        """
        logger.info("Checking Cloud DNS managed zones...")
        all_project_zones = run_gcloud([
            "gcloud", "dns", "managed-zones", "list",
            f"--project={self.project_id}",
        ])
        zones_by_name: Dict[str, Dict[str, Any]] = {
            z["name"]: z for z in all_project_zones if "name" in z
        }

        expected_fwd_dns = f"{self.domain_name}.".lower()

        # If --forward-zone was not explicitly given, check if a VPC-bound zone for this domain already exists
        if not self._forward_zone_explicit and self.forward_zone not in zones_by_name:
            for z_name, z_obj in zones_by_name.items():
                if (
                    z_obj.get("dnsName", "").lower() == expected_fwd_dns
                    and self._zone_bound_to_vpc(z_obj)
                ):
                    self.forward_zone = z_name
                    break

        # 1. Forward Zone
        fwd_data = zones_by_name.get(self.forward_zone)
        if fwd_data and "dnsName" in fwd_data:
            actual_dns = fwd_data["dnsName"]
            self._zone_dns_names[self.forward_zone] = actual_dns
            logger.info(f"  Forward Zone '{self.forward_zone}' -> DNS Domain: {actual_dns}")
            if actual_dns.rstrip(".").lower() != self.domain_name.lower():
                logger.warning(
                    f"  ⚠️ Forward zone '{self.forward_zone}' has dnsName '{actual_dns}', "
                    f"which differs from --domain '{self.domain_name}'. Using '{actual_dns.rstrip('.')}'."
                )
                self.domain_name = actual_dns.rstrip(".")
        elif self.create_missing_zones:
            self._create_private_zone(
                self.forward_zone,
                expected_fwd_dns,
                "Private forward lookup zone",
            )
        else:
            raise GcloudError(
                f"Forward zone '{self.forward_zone}' does not exist in project '{self.project_id}'."
            )

        # 2. Reverse Zones
        # When create_missing_zones is True, create reverse zones directly without checking if they exist.
        # When create_missing_zones is False, require user-supplied --reverse-zones and load them for PTR sync.
        if self.create_missing_zones:
            if not self.reverse_zones_input:
                # Inspect the VPC's non-NSX subnets to dynamically decide between a /16 reverse zone
                # (when all non-NSX subnets in a /8 share a single /16, e.g. 10.40.x.x -> 40.10.in-addr.arpa.)
                # and a /8 reverse zone (when non-NSX subnets span multiple /16s -> 10.in-addr.arpa.).
                # If no subnets are discovered in the VPC, reverse zone creation is skipped.
                subnets = run_gcloud([
                    "gcloud", "compute", "networks", "subnets", "list",
                    f"--project={self.project_id}",
                    f"--filter=network.basename() = '{self.vpc_network}'",
                ])
                # Exclude NSX datapath/TEP subnets (whose appliances do not require FQDNs/DNS records)
                # unless all subnets in the VPC have 'nsx' in their name.
                non_nsx_subnets = [
                    sn for sn in subnets if "nsx" not in sn.get("name", "").lower()
                ]
                candidate_subnets = non_nsx_subnets if non_nsx_subnets else subnets

                # Map each first octet -> ordered list of distinct second octets seen in candidate subnets
                octets_by_first: Dict[str, List[str]] = {}
                for sn in candidate_subnets:
                    cidr = sn.get("ipCidrRange", "")
                    if not cidr:
                        continue
                    octets = cidr.split("/")[0].split(".")
                    if len(octets) == 4:
                        first_oct, second_oct = octets[0], octets[1]
                        sec_list = octets_by_first.setdefault(first_oct, [])
                        if second_oct not in sec_list:
                            sec_list.append(second_oct)

                if not octets_by_first:
                    logger.warning(
                        f"  ⚠️ No subnets found in VPC '{self.vpc_network}'. Skipping reverse zone creation."
                    )

                for idx, (first_oct, sec_list) in enumerate(octets_by_first.items()):
                    if len(sec_list) == 1:
                        second_oct = sec_list[0]
                        rev_dns = f"{second_oct}.{first_oct}.in-addr.arpa."
                        desc = f"Private reverse lookup zone for {first_oct}.{second_oct}.0.0/16"
                        logger.info(
                            f"  ℹ️ All VPC subnets under {first_oct}.0.0.0/8 share {first_oct}.{second_oct}.0.0/16 -> selecting /16 reverse zone ({rev_dns})"
                        )
                    else:
                        rev_dns = f"{first_oct}.in-addr.arpa."
                        desc = f"Private reverse lookup zone for {first_oct}.0.0.0/8"
                        logger.info(
                            f"  ℹ️ VPC subnets span multiple /16s ({', '.join(f'{first_oct}.{s}.x.x' for s in sec_list)}) -> selecting /8 reverse zone ({rev_dns})"
                        )

                    z_name = (
                        f"{self.vpc_network}-reverse-zone"
                        if idx == 0
                        else f"{self.vpc_network}-reverse-zone-{first_oct}"
                    )
                    self.reverse_zones.append(z_name)
                    self._create_private_zone(z_name, rev_dns, desc)
            else:
                for item in self.reverse_zones_input:
                    if not item:
                        continue
                    if "=" in item:
                        zone_name, cidr_hint = item.split("=", 1)
                    elif ":" in item:
                        zone_name, cidr_hint = item.split(":", 1)
                    else:
                        zone_name, cidr_hint = item, None

                    zone_name = zone_name.strip()
                    cidr_hint = cidr_hint.strip() if cidr_hint else None
                    if not zone_name:
                        continue

                    if not cidr_hint:
                        raise ValueError(
                            f"Reverse zone '{zone_name}' must include a CIDR or reverse DNS suffix hint "
                            f"(e.g. '{zone_name}=10.10.0.0/16') when creating zones."
                        )

                    if zone_name not in self.reverse_zones:
                        self.reverse_zones.append(zone_name)

                    rev_dns_name = cidr_to_reverse_dns_name(cidr_hint)
                    self._create_private_zone(
                        zone_name,
                        rev_dns_name,
                        "Private reverse lookup zone",
                    )
        else:
            if not self.reverse_zones_input:
                raise ValueError(
                    "Reverse zones must be provided via --reverse-zones when --no-create-zones is set."
                )

            for item in self.reverse_zones_input:
                if not item:
                    continue
                if "=" in item:
                    zone_name, _ = item.split("=", 1)
                elif ":" in item:
                    zone_name, _ = item.split(":", 1)
                else:
                    zone_name = item

                zone_name = zone_name.strip()
                if not zone_name:
                    continue

                rev_data = zones_by_name.get(zone_name)
                if rev_data and "dnsName" in rev_data:
                    if zone_name not in self.reverse_zones:
                        self.reverse_zones.append(zone_name)
                    self._zone_dns_names[zone_name] = rev_data["dnsName"]
                    logger.info(f"  Reverse Zone '{zone_name}' -> DNS Domain: {rev_data['dnsName']}")
                else:
                    raise GcloudError(
                        f"Reverse zone '{zone_name}' does not exist in project '{self.project_id}'."
                    )

    def _preload_existing_records(self):
        """Pre-loads existing DNS records into memory to prevent 409 conflicts."""
        all_zones = [self.forward_zone] + [
            z for z in self.reverse_zones if z in self._zone_dns_names
        ]
        for zone in set(all_zones):
            if not zone:
                continue
            # Skip listing if zone is only planned to be created in dry-run
            if self.dry_run and not run_gcloud(
                [
                    "gcloud", "dns", "managed-zones", "describe", zone,
                    f"--project={self.project_id}",
                ],
                allow_not_found=True,
            ):
                continue

            records = run_gcloud([
                "gcloud", "dns", "record-sets", "list",
                f"--zone={zone}",
                f"--project={self.project_id}",
            ])
            for r in records:
                key = (zone, r.get("name", "").lower(), r.get("type", "").upper())
                self._cached_records[key] = r.get("rrdatas", [])

    def _find_reverse_zone(self, ip: str, ptr_name: str) -> str:
        """
        Finds the managed zone whose dnsName is the longest valid domain suffix of ptr_name.
        Respects DNS label boundaries ('.') so '0.10.in-addr.arpa.' never matches '50.10.in-addr.arpa.'.
        Raises ValueError if no configured reverse zone covers ptr_name.
        """
        ptr_lower = ptr_name.lower()
        candidates: List[Tuple[int, str]] = []

        for zone in self.reverse_zones:
            dns_suffix = self._zone_dns_names.get(zone, "").lower()
            if not dns_suffix:
                continue
            # Must match either exact zone name or preceded by a dot boundary
            if ptr_lower == dns_suffix or ptr_lower.endswith("." + dns_suffix):
                candidates.append((len(dns_suffix), zone))

        if candidates:
            # Sort by longest suffix (most specific zone wins, e.g. /24 over /16 over /8)
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        raise ValueError(
            f"No configured reverse zone covers IP {ip} ({ptr_name})."
        )

    def _upsert_record(self, zone: str, name: str, record_type: str, rrdata: str):
        """Creates or updates a DNS record idempotently."""
        norm_name = (name.rstrip(".") + ".").lower()
        norm_type = record_type.upper()
        key = (zone, norm_name, norm_type)

        # Warn if two different items in the same run collide on the same record
        prev_rrdata = self._seen_in_run.get(key)
        if prev_rrdata is not None and prev_rrdata != rrdata:
            logger.warning(
                f"  ⚠️ COLLISION in current run for {norm_name} ({norm_type}) in zone '{zone}': "
                f"overwriting '{prev_rrdata}' with '{rrdata}'"
            )
        self._seen_in_run[key] = rrdata

        existing_rrdatas = self._cached_records.get(key)

        if existing_rrdatas is not None:
            # Check exact single-value equality so stale secondary IPs are cleaned up
            if existing_rrdatas == [rrdata]:
                logger.info(f"  ⏭️  SKIPPED (Already Up-to-date): {norm_name} ({norm_type}) -> {rrdata}")
                return
            action = "update"
            verb = "🔄 UPDATING"
        else:
            action = "create"
            verb = "➕ CREATING"

        cmd = [
            "gcloud", "dns", "record-sets", action, norm_name,
            f"--zone={zone}",
            f"--type={norm_type}",
            f"--ttl={self.ttl}",
            f"--rrdatas={rrdata}",
            f"--project={self.project_id}",
            "--quiet",
        ]

        if self.dry_run:
            logger.info(f"  [DRY-RUN] {verb}: {norm_name} ({norm_type}) -> {rrdata} in zone '{zone}'")
            self._cached_records[key] = [rrdata]
        else:
            logger.info(f"  {verb}: {norm_name} ({norm_type}) -> {rrdata} in zone '{zone}'")
            run_gcloud(cmd, parse_json=False)
            self._cached_records[key] = [rrdata]

    def _extract_vpc_ip(self, inst: Dict[str, Any]) -> Optional[str]:
        """Finds the primary IPv4 address on the NIC connected to self.vpc_network."""
        nics = inst.get("networkInterfaces", [])
        # Prefer the primary untagged NIC (no 'vlan' field) on self.vpc_network
        for prefer_untagged in (True, False):
            for nic in nics:
                if prefer_untagged and nic.get("vlan") is not None:
                    continue
                net_url = nic.get("network", "")
                net_name = net_url.rstrip("/").split("/")[-1]
                if net_name == self.vpc_network and nic.get("networkIP"):
                    subnet_url = nic.get("subnetwork", "")
                    if subnet_url:
                        subnet_name = subnet_url.rstrip("/").split("/")[-1]
                        if subnet_name and "nsx" not in subnet_name.lower():
                            self._mgmt_subnets.add(subnet_name)
                    return nic["networkIP"]
        # Fallback to nic0 if filter already matched
        if nics and nics[0].get("networkIP"):
            subnet_url = nics[0].get("subnetwork", "")
            if subnet_url:
                subnet_name = subnet_url.rstrip("/").split("/")[-1]
                if subnet_name and "nsx" not in subnet_name.lower():
                    self._mgmt_subnets.add(subnet_name)
            return nics[0]["networkIP"]
        return None

    def sync_baremetal_nodes(self):
        """Discovers Z3 bare-metal instances and registers A/PTR records."""
        logger.info("\n=== [1/3] Discovering Bare-Metal Nodes (machineType: ^z3) ===")
        instances = run_gcloud([
            "gcloud", "compute", "instances", "list",
            f"--project={self.project_id}",
            f"--filter=machineType.basename() ~ ^z3 AND networkInterfaces[].network.basename() = '{self.vpc_network}'",
        ])

        if not instances:
            logger.warning(f"No Z3 bare-metal nodes found in VPC '{self.vpc_network}'.")
            return

        for inst in instances:
            name = inst.get("name", "")
            hostname = inst.get("hostname")
            ip = self._extract_vpc_ip(inst)

            if not ip:
                logger.warning(f"  ⚠️ Skipping instance '{name}': no networkIP found on VPC '{self.vpc_network}'.")
                continue

            fqdn = normalize_fqdn(hostname if hostname else name, self.domain_name)
            ptr = ip_to_reverse_ptr(ip)

            logger.info(f"Node: {name} | IP: {ip} | FQDN: {fqdn}")
            self._upsert_record(self.forward_zone, fqdn, "A", ip)

            rev_zone = self._find_reverse_zone(ip, ptr)
            self._upsert_record(rev_zone, ptr, "PTR", fqdn)

    def sync_frontends(self):
        """Discovers Forwarding Rules, strips '-fr', and registers A/PTR records (skipping NSX subnet LBs)."""
        logger.info("\n=== [2/3] Discovering Internal Forwarding Rules (Frontends) ===")
        fr_list = run_gcloud([
            "gcloud", "compute", "forwarding-rules", "list",
            f"--project={self.project_id}",
            f"--filter=loadBalancingScheme:(INTERNAL,INTERNAL_MANAGED,INTERNAL_SELF_MANAGED) AND network.basename() = '{self.vpc_network}'",
        ])

        if not fr_list:
            logger.warning(f"No internal forwarding rules found in VPC '{self.vpc_network}'.")
            return

        for fr in fr_list:
            name = fr.get("name", "")
            ip = fr.get("IPAddress", "")
            subnet_url = fr.get("subnetwork", "")
            subnet_name = subnet_url.rstrip("/").split("/")[-1] if subnet_url else ""

            if not ip:
                continue

            # Skip load balancers in the NSX (TEP/Uplink) subnet as they are IP-only
            # and do not require FQDNs per Broadcom VCF guidelines.
            if "nsx" in subnet_name.lower() or (
                subnet_name and self._mgmt_subnets and subnet_name not in self._mgmt_subnets
            ):
                logger.info(
                    f"  ⏭️  SKIPPED (NSX/non-management subnet '{subnet_name}'): {name} ({ip})"
                )
                continue

            custom_name = strip_frontend_suffix(name)
            fqdn = normalize_fqdn(custom_name, self.domain_name)
            ptr = ip_to_reverse_ptr(ip)

            logger.info(f"Frontend: {name} -> Clean: {custom_name} | FQDN: {fqdn} | IP: {ip}")
            self._upsert_record(self.forward_zone, fqdn, "A", ip)

            rev_zone = self._find_reverse_zone(ip, ptr)
            self._upsert_record(rev_zone, ptr, "PTR", fqdn)

    def configure_ntp(self, ntp_ip: str):
        """Configures the NTP DNS record for pre-validation or post-bringup cutover."""
        logger.info(f"\n=== [3/3] Configuring NTP Record (ntp.{self.domain_name}.) -> {ntp_ip} ===")
        # Validate IPv4 address format
        ipaddress.IPv4Address(ntp_ip.strip())
        ntp_fqdn = normalize_fqdn("ntp", self.domain_name)
        self._upsert_record(self.forward_zone, ntp_fqdn, "A", ntp_ip.strip())


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize Cloud DNS & NTP for Self-Managed VMware Engine (VCF on GCP)."
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="GCP Project ID (defaults to active `gcloud config get-value project`)",
    )
    parser.add_argument(
        "--vpc-network",
        required=True,
        help="VPC Network name or full URL (e.g. vcf-day0-testing-vpc)",
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Forward DNS domain name (e.g. smve.test or bm.gce)",
    )
    parser.add_argument(
        "--forward-zone",
        default=None,
        help=(
            "Forward Cloud DNS managed-zone resource name "
            "(optional: auto-discovers existing VPC-bound zone or creates '<vpc-network>-forward-zone')"
        ),
    )
    parser.add_argument(
        "--reverse-zones",
        nargs="*",
        default=[],
        help=(
            "Reverse DNS zone names. When creating zones (default), specify with CIDR/suffix hints "
            "(e.g. rev-zone-1=10.10.0.0/16) or omit to create dynamically from VPC subnets. "
            "Required when --no-create-zones is set (pass existing reverse zone names to use for PTR records)."
        ),
    )
    parser.add_argument(
        "--dns-policy",
        default=None,
        help=(
            "Cloud DNS Policy resource name "
            "(optional: auto-discovers existing VPC-bound policy or creates '<vpc-network>-dns-policy' with default settings)"
        ),
    )
    parser.add_argument("--ttl", type=int, default=300, help="DNS Record TTL (default: 300)")
    parser.add_argument(
        "--no-create-zones",
        action="store_true",
        help="Do not create forward or reverse Cloud DNS managed zones (requires --reverse-zones)",
    )
    parser.add_argument(
        "--no-create-dns-policy",
        action="store_true",
        help="Do not automatically create a Cloud DNS policy for the VPC",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview DNS zone and record modifications without applying them",
    )

    # Action Flags
    parser.add_argument(
        "--setup-zones",
        action="store_true",
        help="Enable Cloud DNS API, create VPC DNS policy, and ensure forward/reverse zones exist",
    )
    parser.add_argument(
        "--sync-all",
        action="store_true",
        help="Sync all Z3 bare-metal nodes and management-subnet internal load balancer frontend A/PTR records (skipping NSX subnet LBs)",
    )
    parser.add_argument(
        "--set-ntp-ip",
        help="Set ntp.<domain> A record to a specific IP (e.g. valid NTP IP before VCF validation, or 169.254.169.254 after validation)",
    )

    args = parser.parse_args()

    # Check action flags BEFORE running any gcloud commands
    if not (args.setup_zones or args.sync_all or args.set_ntp_ip):
        parser.print_help()
        sys.exit(0)

    project_id = args.project_id or get_default_project()
    if not project_id:
        parser.error(
            "--project-id was not provided and no active project is set in `gcloud config`."
        )

    try:
        manager = VcfDnsManager(
            project_id=project_id,
            vpc_network=args.vpc_network,
            domain_name=args.domain,
            forward_zone=args.forward_zone,
            reverse_zones=args.reverse_zones,
            dns_policy=args.dns_policy,
            ttl=args.ttl,
            create_missing_zones=not args.no_create_zones,
            create_dns_policy=not args.no_create_dns_policy,
            dry_run=args.dry_run,
        )

        if args.sync_all:
            manager.sync_baremetal_nodes()
            manager.sync_frontends()

        if args.set_ntp_ip:
            manager.configure_ntp(args.set_ntp_ip)

    except (GcloudError, ValueError) as exc:
        logger.error(f"Execution aborted: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
