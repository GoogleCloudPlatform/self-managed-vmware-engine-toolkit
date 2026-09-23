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

"""Unit tests for cloud_dns/vcf_cloud_dns_sync.py.

Validates:
- IPv4 reverse PTR and CIDR-to-in-addr.arpa. conversions.
- FQDN normalization (dot boundaries, raising ValueError on mismatched domain suffix) and '-fr' suffix removal.
- Cloud DNS API enablement, VPC DNS policy idempotency, and forward/reverse zone auto-discovery/creation.
- Dynamic /16 vs /8 reverse zone selection based on non-NSX VPC subnets, skipping reverse zone creation when no subnets exist, label-boundary matching, and longest-prefix specificity.
- Record upsert idempotency (create, update on stale/multi-IP, skip on exact match, collision detection).
- Bare-metal Z3 node discovery (including multi-NIC VPC IP selection), management frontend sync (skipping NSX subnet load balancers), and NTP configuration.
- CLI argument parsing (including independent `--no-create-zones` and `--no-create-dns-policy` flags) and main workflow execution.
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

# Ensure scripts and cloud_dns directories are in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
CLOUD_DNS_DIR = os.path.join(SCRIPTS_DIR, "cloud_dns")
for path in (CLOUD_DNS_DIR, SCRIPTS_DIR):
  if path not in sys.path:
    sys.path.insert(0, path)

import vcf_cloud_dns_sync


class TestHelperFunctions(unittest.TestCase):
  """Tests for pure DNS formatting and gcloud execution helper functions."""

  def test_ip_to_reverse_ptr_valid(self):
    self.assertEqual(
        vcf_cloud_dns_sync.ip_to_reverse_ptr("10.10.1.25"),
        "25.1.10.10.in-addr.arpa.",
    )
    self.assertEqual(
        vcf_cloud_dns_sync.ip_to_reverse_ptr(" 192.168.0.1 "),
        "1.0.168.192.in-addr.arpa.",
    )

  def test_ip_to_reverse_ptr_invalid(self):
    with self.assertRaises(ValueError):
      vcf_cloud_dns_sync.ip_to_reverse_ptr("invalid-ip")

  def test_cidr_to_reverse_dns_name(self):
    self.assertEqual(
        vcf_cloud_dns_sync.cidr_to_reverse_dns_name("10.0.0.0/8"),
        "10.in-addr.arpa.",
    )
    self.assertEqual(
        vcf_cloud_dns_sync.cidr_to_reverse_dns_name("10.10.0.0/16"),
        "10.10.in-addr.arpa.",
    )
    self.assertEqual(
        vcf_cloud_dns_sync.cidr_to_reverse_dns_name("192.168.1.0/24"),
        "1.168.192.in-addr.arpa.",
    )
    self.assertEqual(
        vcf_cloud_dns_sync.cidr_to_reverse_dns_name("50.10.in-addr.arpa"),
        "50.10.in-addr.arpa.",
    )
    self.assertEqual(
        vcf_cloud_dns_sync.cidr_to_reverse_dns_name("50.10.in-addr.arpa."),
        "50.10.in-addr.arpa.",
    )

  def test_cidr_to_reverse_dns_name_ipv6_rejected(self):
    with self.assertRaises(ValueError):
      vcf_cloud_dns_sync.cidr_to_reverse_dns_name("2001:db8::/32")

  def test_normalize_fqdn_standard_and_dot_boundaries(self):
    # Standard short name
    self.assertEqual(
        vcf_cloud_dns_sync.normalize_fqdn("esxi-h0", "smve.test"),
        "esxi-h0.smve.test.",
    )
    # Already qualified with target domain
    self.assertEqual(
        vcf_cloud_dns_sync.normalize_fqdn("esxi-h0.smve.test.", "smve.test"),
        "esxi-h0.smve.test.",
    )
    # Dot-boundary check: "my-test" does NOT end with ".test", so ".test." must be appended
    self.assertEqual(
        vcf_cloud_dns_sync.normalize_fqdn("my-test", "test"),
        "my-test.test.",
    )
    # Mismatched domain suffix must raise ValueError
    with self.assertRaises(ValueError):
      vcf_cloud_dns_sync.normalize_fqdn("node1.other.domain", "bm.gce")
    with self.assertRaises(ValueError):
      vcf_cloud_dns_sync.normalize_fqdn("node1.abm.gce", "bm.gce")

  def test_strip_frontend_suffix(self):
    self.assertEqual(vcf_cloud_dns_sync.strip_frontend_suffix("vcenter-fr"), "vcenter")
    self.assertEqual(vcf_cloud_dns_sync.strip_frontend_suffix("sddc-manager-fr-01"), "sddc-manager-fr-01")
    # Substrings like '-fra-' or '-frontend' must NOT be corrupted
    self.assertEqual(vcf_cloud_dns_sync.strip_frontend_suffix("vcf-fra-01"), "vcf-fra-01")
    self.assertEqual(vcf_cloud_dns_sync.strip_frontend_suffix("vcf-frontend"), "vcf-frontend")

  @mock.patch("subprocess.run")
  def test_run_gcloud_json_and_not_found_handling(self, mock_run):
    # JSON parsing
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='[{"name": "zone-1"}]', stderr=""
    )
    res = vcf_cloud_dns_sync.run_gcloud(["gcloud", "dns", "managed-zones", "list"])
    self.assertEqual(res, [{"name": "zone-1"}])

    # allow_not_found=True returns None on 404
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["gcloud"],
        stderr="ERROR: (gcloud.dns.managed-zones.describe) HTTPError 404: The 'parameters.managedZone' resource named 'missing' was not found.",
    )
    self.assertIsNone(
        vcf_cloud_dns_sync.run_gcloud(
            ["gcloud", "dns", "managed-zones", "describe", "missing"],
            allow_not_found=True,
        )
    )

    # Non-404 error raises GcloudError
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["gcloud"],
        stderr="ERROR: Permission denied",
    )
    with self.assertRaises(vcf_cloud_dns_sync.GcloudError):
      vcf_cloud_dns_sync.run_gcloud(["gcloud", "dns", "managed-zones", "list"])


class TestVcfDnsManagerBootstrapAndRouting(unittest.TestCase):
  """Tests for VcfDnsManager initialization, policy/zone creation, and reverse zone selection."""

  def _make_gcloud_router(
      self, existing_policies=None, existing_zones=None, existing_records=None, subnets=None
  ):
    """Creates a side_effect function for mocking run_gcloud calls."""
    existing_policies = existing_policies if existing_policies is not None else []
    existing_zones = existing_zones if existing_zones is not None else []
    existing_records = existing_records if existing_records is not None else {}
    if subnets is None:
      subnets = [
          {"name": "mgmt-subnet", "ipCidrRange": "10.40.0.0/24"},
          {"name": "vsan-subnet", "ipCidrRange": "10.40.1.0/24"},
      ]
    recorded_cmds = []

    def side_effect(cmd, parse_json=True, allow_not_found=False):
      recorded_cmds.append(cmd)
      cmd_str = " ".join(cmd)
      if "dns policies list" in cmd_str:
        return existing_policies
      if "dns managed-zones list" in cmd_str:
        return existing_zones
      if "compute networks subnets list" in cmd_str:
        return subnets
      if "dns record-sets list" in cmd_str:
        for arg in cmd:
          if arg.startswith("--zone="):
            z = arg.split("=", 1)[1]
            return existing_records.get(z, [])
        return []
      if "compute instances list" in cmd_str:
        return [
            {
                "name": "esxi-node-1",
                "hostname": "esxi-node-1.smve.test",
                "networkInterfaces": [
                    {"network": "projects/p/global/networks/other-vpc", "networkIP": "192.168.1.10"},
                    {"network": "projects/p/global/networks/vcf-vpc", "networkIP": "10.10.1.11"},
                ],
            }
        ]
      if "compute forwarding-rules list" in cmd_str:
        return [
            {"name": "vcenter-fr", "IPAddress": "10.10.1.20"},
            {"name": "nsx-fra-fr", "IPAddress": "10.50.2.30"},
        ]
      return "" if not parse_json else []

    return side_effect, recorded_cmds

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_bootstrap_single_slash16_selects_slash16_reverse_zone(self, mock_gcloud):
    # All subnets in 10.40.x.x -> should select 40.10.in-addr.arpa. (/16)
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=[],
        existing_zones=[],
        subnets=[
            {"name": "mgmt-subnet", "ipCidrRange": "10.40.0.0/24"},
            {"name": "vsan-subnet", "ipCidrRange": "10.40.1.0/24"},
        ],
    )
    mock_gcloud.side_effect = side_effect

    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="projects/test-proj/global/networks/vcf-vpc",
        domain_name="smve.test",
    )

    self.assertEqual(mgr.vpc_network, "vcf-vpc")
    self.assertEqual(mgr.forward_zone, "vcf-vpc-forward-zone")
    self.assertEqual(mgr.dns_policy, "vcf-vpc-dns-policy")

    flat_cmds = [" ".join(c) for c in cmds]
    self.assertTrue(any("services enable dns.googleapis.com" in c for c in flat_cmds))
    self.assertTrue(
        any("dns policies create vcf-vpc-dns-policy" in c and "--networks=vcf-vpc" in c for c in flat_cmds)
    )
    self.assertTrue(
        any("dns managed-zones create vcf-vpc-forward-zone" in c and "--dns-name=smve.test." in c for c in flat_cmds)
    )
    self.assertTrue(
        any("dns managed-zones create vcf-vpc-reverse-zone" in c and "--dns-name=40.10.in-addr.arpa." in c for c in flat_cmds)
    )

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_bootstrap_multi_slash16_selects_slash8_reverse_zone(self, mock_gcloud):
    # Non-NSX subnets span 10.40.x.x and 10.43.x.x -> should select 10.in-addr.arpa. (/8)
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=[],
        existing_zones=[],
        subnets=[
            {"name": "mgmt-subnet", "ipCidrRange": "10.40.0.0/24"},
            {"name": "wld-mgmt-subnet", "ipCidrRange": "10.43.0.0/24"},
        ],
    )
    mock_gcloud.side_effect = side_effect

    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="vcf-vpc",
        domain_name="smve.test",
    )

    self.assertEqual(mgr._zone_dns_names["vcf-vpc-reverse-zone"], "10.in-addr.arpa.")
    flat_cmds = [" ".join(c) for c in cmds]
    self.assertTrue(
        any("dns managed-zones create vcf-vpc-reverse-zone" in c and "--dns-name=10.in-addr.arpa." in c for c in flat_cmds)
    )

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_nsx_subnet_skipped_in_reverse_zone_and_frontends(self, mock_gcloud):
    # vcf-day0-mgmt (10.40.0.0/24) + vcf-day0-nsx (10.43.0.0/24):
    # - NSX subnet should be ignored for reverse zone (/16 40.10.in-addr.arpa. selected)
    # - NSX Edge mgmt LB in vcf-day0-mgmt gets DNS records
    # - NSX Edge TEP LB in vcf-day0-nsx is skipped
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=[],
        existing_zones=[],
        subnets=[
            {"name": "vcf-day0-mgmt", "ipCidrRange": "10.40.0.0/24"},
            {"name": "vcf-day0-nsx", "ipCidrRange": "10.43.0.0/24"},
        ],
    )

    def custom_side_effect(cmd, parse_json=True, allow_not_found=False):
      cmd_str = " ".join(cmd)
      if "compute forwarding-rules list" in cmd_str:
        cmds.append(cmd)
        return [
            {
                "name": "vcf-day0-nsx-edge01-fr",
                "IPAddress": "10.40.0.38",
                "subnetwork": "projects/p/regions/us-central1/subnetworks/vcf-day0-mgmt",
            },
            {
                "name": "vcf-day0-nsx-edge01-tep01-fr",
                "IPAddress": "10.43.0.10",
                "subnetwork": "projects/p/regions/us-central1/subnetworks/vcf-day0-nsx",
            },
        ]
      return side_effect(cmd, parse_json=parse_json, allow_not_found=allow_not_found)

    mock_gcloud.side_effect = custom_side_effect

    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="vcf-vpc",
        domain_name="bm.gce",
    )
    mgr.sync_frontends()

    self.assertEqual(mgr._zone_dns_names["vcf-vpc-reverse-zone"], "40.10.in-addr.arpa.")
    flat_cmds = [" ".join(c) for c in cmds]
    self.assertTrue(
        any("dns record-sets create vcf-day0-nsx-edge01.bm.gce." in c and "--rrdatas=10.40.0.38" in c for c in flat_cmds)
    )
    self.assertFalse(
        any("vcf-day0-nsx-edge01-tep01" in c for c in flat_cmds)
    )

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_bootstrap_no_subnets_skips_reverse_zone_creation(self, mock_gcloud):
    # No subnets in VPC -> should skip reverse zone creation instead of defaulting to 10.in-addr.arpa.
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=[],
        existing_zones=[],
        subnets=[],
    )
    mock_gcloud.side_effect = side_effect

    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="vcf-vpc",
        domain_name="smve.test",
    )

    self.assertEqual(mgr.reverse_zones, [])
    flat_cmds = [" ".join(c) for c in cmds]
    self.assertFalse(
        any("dns managed-zones create vcf-vpc-reverse-zone" in c for c in flat_cmds)
    )

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_create_missing_zones_false_uses_provided_reverse_zones(self, mock_gcloud):
    existing_policies = [
        {
            "name": "existing-vpc-policy",
            "networks": [{"networkUrl": "https://www.googleapis.com/compute/v1/projects/p/global/networks/vcf-vpc"}],
        }
    ]
    existing_zones = [
        {
            "name": "custom-fwd-zone",
            "dnsName": "smve.test.",
            "privateVisibilityConfig": {
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}]
            },
        },
        {
            "name": "rev-10-0",
            "dnsName": "0.10.in-addr.arpa.",
            "privateVisibilityConfig": {
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}]
            },
        },
        {
            "name": "rev-10-10",
            "dnsName": "10.10.in-addr.arpa.",
            "privateVisibilityConfig": {
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}]
            },
        },
        {
            "name": "rev-10-10-1",
            "dnsName": "1.10.10.in-addr.arpa.",
            "privateVisibilityConfig": {
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}]
            },
        },
    ]
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=existing_policies,
        existing_zones=existing_zones,
    )
    mock_gcloud.side_effect = side_effect

    # When create_missing_zones=False, omitting reverse_zones must raise ValueError
    with self.assertRaises(ValueError):
      vcf_cloud_dns_sync.VcfDnsManager(
          project_id="test-proj",
          vpc_network="vcf-vpc",
          domain_name="smve.test",
          create_missing_zones=False,
      )

    # When create_missing_zones=False, passing a non-existent reverse zone must raise GcloudError
    with self.assertRaises(vcf_cloud_dns_sync.GcloudError):
      vcf_cloud_dns_sync.VcfDnsManager(
          project_id="test-proj",
          vpc_network="vcf-vpc",
          domain_name="smve.test",
          reverse_zones=["non-existent-rev-zone"],
          create_missing_zones=False,
      )

    cmds.clear()
    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="vcf-vpc",
        domain_name="smve.test",
        reverse_zones=["rev-10-0", "rev-10-10", "rev-10-10-1"],
        create_missing_zones=False,
    )

    # Should reuse existing policy, forward zone, and provided reverse zones without creating new ones
    self.assertEqual(mgr.dns_policy, "existing-vpc-policy")
    self.assertEqual(mgr.forward_zone, "custom-fwd-zone")
    self.assertEqual(mgr.reverse_zones, ["rev-10-0", "rev-10-10", "rev-10-10-1"])
    flat_cmds = [" ".join(c) for c in cmds]
    self.assertFalse(any("dns policies create" in c for c in flat_cmds))
    self.assertFalse(any("dns managed-zones create" in c for c in flat_cmds))

    # Longest-prefix specificity: 10.10.1.5 -> matches /24 zone 'rev-10-10-1' over /16 'rev-10-10'
    self.assertEqual(
        mgr._find_reverse_zone("10.10.1.5", "5.1.10.10.in-addr.arpa."),
        "rev-10-10-1",
    )
    # 10.10.2.5 -> matches /16 zone 'rev-10-10'
    self.assertEqual(
        mgr._find_reverse_zone("10.10.2.5", "5.2.10.10.in-addr.arpa."),
        "rev-10-10",
    )
    # Dot-boundary check: 10.50.1.2 ('2.1.50.10.in-addr.arpa.') must NOT match '0.10.in-addr.arpa.' ('rev-10-0');
    # and when no configured reverse zone covers the IP, _find_reverse_zone must raise ValueError
    with self.assertRaises(ValueError):
      mgr._find_reverse_zone("10.50.1.2", "2.1.50.10.in-addr.arpa.")

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_create_missing_zones_true_creates_reverse_zones_without_checking_existing(self, mock_gcloud):
    # Even if an existing reverse zone is present in `dns managed-zones list`,
    # create_missing_zones=True creates reverse zones directly without checking if they exist.
    existing_zones = [
        {
            "name": "vcf-vpc-reverse-zone",
            "dnsName": "40.10.in-addr.arpa.",
            "privateVisibilityConfig": {
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}]
            },
        },
    ]
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=[],
        existing_zones=existing_zones,
        subnets=[{"name": "mgmt-subnet", "ipCidrRange": "10.40.0.0/24"}],
    )
    mock_gcloud.side_effect = side_effect

    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="vcf-vpc",
        domain_name="smve.test",
        create_missing_zones=True,
    )

    self.assertEqual(mgr.reverse_zones, ["vcf-vpc-reverse-zone"])
    flat_cmds = [" ".join(c) for c in cmds]
    self.assertTrue(
        any("dns managed-zones create vcf-vpc-reverse-zone" in c and "--dns-name=40.10.in-addr.arpa." in c for c in flat_cmds)
    )

    # When create_missing_zones=True and reverse_zones is passed without a CIDR/suffix hint, raise ValueError
    with self.assertRaises(ValueError):
      vcf_cloud_dns_sync.VcfDnsManager(
          project_id="test-proj",
          vpc_network="vcf-vpc",
          domain_name="smve.test",
          reverse_zones=["custom-rev-without-cidr"],
          create_missing_zones=True,
      )

  @mock.patch("vcf_cloud_dns_sync.run_gcloud")
  def test_full_sync_and_record_upsert_idempotency(self, mock_gcloud):
    existing_zones = [
        {
            "name": "vcf-vpc-forward-zone",
            "dnsName": "smve.test.",
            "privateVisibilityConfig": {
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}]
            },
        },
    ]
    existing_records = {
        "vcf-vpc-forward-zone": [
            # Already up-to-date record (should be skipped)
            {"name": "esxi-node-1.smve.test.", "type": "A", "rrdatas": ["10.10.1.11"]},
            # Record with stale secondary IP (should be updated)
            {"name": "vcenter.smve.test.", "type": "A", "rrdatas": ["10.10.1.20", "10.10.1.99"]},
        ],
        "vcf-vpc-reverse-zone": [
            {"name": "11.1.10.10.in-addr.arpa.", "type": "PTR", "rrdatas": ["esxi-node-1.smve.test."]},
        ],
    }
    side_effect, cmds = self._make_gcloud_router(
        existing_policies=[
            {
                "name": "vcf-vpc-dns-policy",
                "networks": [{"networkUrl": "projects/p/global/networks/vcf-vpc"}],
            }
        ],
        existing_zones=existing_zones,
        existing_records=existing_records,
        subnets=[
            {"name": "mgmt-subnet", "ipCidrRange": "10.10.1.0/24"},
            {"name": "wld-mgmt-subnet", "ipCidrRange": "10.50.2.0/24"},
        ],
    )
    mock_gcloud.side_effect = side_effect

    mgr = vcf_cloud_dns_sync.VcfDnsManager(
        project_id="test-proj",
        vpc_network="vcf-vpc",
        domain_name="smve.test",
    )
    mgr.sync_baremetal_nodes()
    mgr.sync_frontends()
    mgr.configure_ntp("169.254.169.254")

    flat_cmds = [" ".join(c) for c in cmds]

    # esxi-node-1 A & PTR were already up-to-date -> must NOT be created or updated
    self.assertFalse(any("esxi-node-1.smve.test." in c and "record-sets" in c for c in flat_cmds))

    # vcenter.smve.test. had a stale second IP -> must be UPDATED to 10.10.1.20
    self.assertTrue(
        any("dns record-sets update vcenter.smve.test." in c and "--rrdatas=10.10.1.20" in c for c in flat_cmds)
    )

    # nsx-fra-fr -> stripped to nsx-fra.smve.test. (preserving '-fra') and PTR created in upfront /8 'vcf-vpc-reverse-zone'
    self.assertTrue(
        any("dns record-sets create nsx-fra.smve.test." in c and "--rrdatas=10.50.2.30" in c for c in flat_cmds)
    )
    self.assertTrue(
        any("dns managed-zones create vcf-vpc-reverse-zone" in c and "--dns-name=10.in-addr.arpa." in c for c in flat_cmds)
    )
    self.assertTrue(
        any(
            "dns record-sets create 30.2.50.10.in-addr.arpa." in c
            and "--zone=vcf-vpc-reverse-zone" in c
            and "--rrdatas=nsx-fra.smve.test." in c
            for c in flat_cmds
        )
    )

    # NTP record created
    self.assertTrue(
        any("dns record-sets create ntp.smve.test." in c and "--rrdatas=169.254.169.254" in c for c in flat_cmds)
    )


class TestMainCli(unittest.TestCase):
  """Tests for CLI argument handling in main()."""

  @mock.patch("vcf_cloud_dns_sync.VcfDnsManager")
  def test_no_action_flags_exits_without_calling_gcloud(self, mock_mgr):
    with mock.patch.object(
        sys, "argv", ["vcf_cloud_dns_sync.py", "--vpc-network", "my-vpc", "--domain", "smve.test"]
    ):
      with self.assertRaises(SystemExit) as ctx:
        vcf_cloud_dns_sync.main()
      self.assertEqual(ctx.exception.code, 0)
      mock_mgr.assert_not_called()

  @mock.patch("vcf_cloud_dns_sync.VcfDnsManager")
  @mock.patch("vcf_cloud_dns_sync.get_default_project", return_value="default-gcloud-proj")
  def test_sync_all_and_set_ntp_ip_execution(self, mock_default_proj, mock_mgr):
    with mock.patch.object(
        sys,
        "argv",
        [
            "vcf_cloud_dns_sync.py",
            "--vpc-network",
            "my-vpc",
            "--domain",
            "smve.test",
            "--sync-all",
            "--set-ntp-ip",
            "10.254.254.250",
        ],
    ):
      vcf_cloud_dns_sync.main()
      mock_mgr.assert_called_once_with(
          project_id="default-gcloud-proj",
          vpc_network="my-vpc",
          domain_name="smve.test",
          forward_zone=None,
          reverse_zones=[],
          dns_policy=None,
          ttl=300,
          create_missing_zones=True,
          create_dns_policy=True,
          dry_run=False,
      )
      instance = mock_mgr.return_value
      instance.sync_baremetal_nodes.assert_called_once()
      instance.sync_frontends.assert_called_once()
      instance.configure_ntp.assert_called_once_with("10.254.254.250")

  @mock.patch("vcf_cloud_dns_sync.VcfDnsManager")
  def test_no_create_zones_and_no_create_dns_policy_flags(self, mock_mgr):
    with mock.patch.object(
        sys,
        "argv",
        [
            "vcf_cloud_dns_sync.py",
            "--project-id",
            "my-proj",
            "--vpc-network",
            "my-vpc",
            "--domain",
            "smve.test",
            "--no-create-dns-policy",
            "--sync-all",
        ],
    ):
      vcf_cloud_dns_sync.main()
      mock_mgr.assert_called_once_with(
          project_id="my-proj",
          vpc_network="my-vpc",
          domain_name="smve.test",
          forward_zone=None,
          reverse_zones=[],
          dns_policy=None,
          ttl=300,
          create_missing_zones=True,
          create_dns_policy=False,
          dry_run=False,
      )


if __name__ == "__main__":
  unittest.main()
