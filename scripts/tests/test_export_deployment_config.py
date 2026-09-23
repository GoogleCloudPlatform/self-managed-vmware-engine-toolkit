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

"""Unit tests for export_deployment_config.py script.

Validates:
- Canonical schema key reordering for all supported VCF and Python config blocks.
- Terraform output loading from files, standard input, and live CLI execution.
- Config extraction from wrapped/unwrapped Terraform JSON output structures.
- JSON output serialization to stdout and nested file paths.
- Command-line argument parsing and main workflow execution scenarios.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# Ensure scripts root directory is in sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
  sys.path.insert(0, SCRIPTS_DIR)

import export_deployment_config


class TestReorderObject(unittest.TestCase):
  """Tests for recursive schema key ordering according to canonical field specifications."""

  def test_reorder_root_mgmt_keys(self):
    """Verifies canonical field order for root management domain deployment config."""
    unordered = {
        "workflowType": "VCF",
        "dnsSpec": {"subdomain": "example.com", "nameservers": ["10.0.0.1"]},
        "version": "5.2.0",
        "sddcId": "sddc-1",
        "vcfInstanceName": "vcf-inst",
        "ceipEnabled": True,
        "custom_unlisted_key": "custom_val",
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")
    keys = list(ordered.keys())

    # Canonical order: version, vcfInstanceName, sddcId, ceipEnabled, workflowType, dnsSpec...
    self.assertEqual(
        keys[:6],
        ["version", "vcfInstanceName", "sddcId", "ceipEnabled", "workflowType", "dnsSpec"],
    )
    # Unlisted keys should appear at the end
    self.assertEqual(keys[-1], "custom_unlisted_key")

  def test_reorder_root_python_keys(self):
    """Verifies canonical field order for root python scripts input config."""
    unordered = {
        "vcf_deployment_config": {"target_gce_node": "node-1"},
        "esxi_root_password_secret": "secret-path",
        "zone": "us-central1-a",
        "project": "my-project",
        "gce_nodes": ["node-1", "node-2"],
        "extra_python_param": 123,
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_python__")
    keys = list(ordered.keys())

    self.assertEqual(
        keys[:5],
        [
            "project",
            "zone",
            "gce_nodes",
            "esxi_root_password_secret",
            "vcf_deployment_config",
        ],
    )
    self.assertEqual(keys[-1], "extra_python_param")

  def test_reorder_nested_structures(self):
    """Verifies recursive ordering on nested dictionary structures."""
    unordered = {
        "sddcManagerSpec": {
            "version": "5.2.0",
            "rootPassword": "pwd",
            "hostname": "sddc.test.local",
            "sslThumbprint": "AA:BB:CC",
            "localUserPassword": "pwd2",
            "sshPassword": "pwd3",
            "useExistingDeployment": False,
        },
        "vcenterSpec": {
            "version": "8.0.0",
            "ssoDomain": "vsphere.local",
            "vcenterHostname": "vc.test.local",
            "storageSize": "default",
            "vmSize": "medium",
            "rootVcenterPassword": "root_pwd",
            "adminUserSsoPassword": "admin_pwd",
            "useExistingDeployment": False,
        },
        "clusterSpec": {
            "clusterName": "mgmt-cluster",
            "datacenterName": "dc1",
        },
        "dnsSpec": {
            "nameservers": ["10.0.0.1", "10.0.0.2"],
            "subdomain": "example.com",
        },
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")

    sddc_keys = list(ordered["sddcManagerSpec"].keys())
    self.assertEqual(
        sddc_keys,
        [
            "hostname",
            "rootPassword",
            "sshPassword",
            "localUserPassword",
            "version",
            "useExistingDeployment",
            "sslThumbprint",
        ],
    )

    vc_keys = list(ordered["vcenterSpec"].keys())
    self.assertEqual(
        vc_keys,
        [
            "vcenterHostname",
            "vmSize",
            "storageSize",
            "rootVcenterPassword",
            "adminUserSsoPassword",
            "ssoDomain",
            "version",
            "useExistingDeployment",
        ],
    )

    cluster_keys = list(ordered["clusterSpec"].keys())
    self.assertEqual(cluster_keys, ["datacenterName", "clusterName"])

    dns_keys = list(ordered["dnsSpec"].keys())
    self.assertEqual(dns_keys, ["subdomain", "nameservers"])
    self.assertEqual(ordered["dnsSpec"]["nameservers"], ["10.0.0.1", "10.0.0.2"])

  def test_reorder_network_and_nsxt_specs(self):
    """Verifies ordering for network, NSX-T, DVS, and IP pool specifications."""
    unordered = {
        "dvsSpecs": [
            {
                "networks": ["mgmt-pg"],
                "vmnicsToUplinks": [{"uplink": "uplink1", "id": "vmnic0"}],
                "dvsName": "vcf-dvs",
                "nsxtSwitchConfig": {
                    "hostSwitchOperationalMode": "STANDARD",
                    "transportZones": [
                        {"transportType": "OVERLAY", "name": "overlay-tz"}
                    ],
                },
                "mtu": 9000,
                "lagSpecs": None,
                "nsxTeamings": [
                    {"activeUplinks": ["uplink1"], "policy": "FAILOVER_ORDER"}
                ],
            }
        ],
        "nsxtSpec": {
            "version": "4.1.0",
            "vipFqdn": "nsx-vip.test.local",
            "nsxtManagerSize": "MEDIUM",
            "nsxtManagers": [{"hostname": "nsx1.test.local"}],
            "rootNsxtManagerPassword": "pwd",
            "nsxtAdminPassword": "pwd",
            "nsxtAuditPassword": "pwd",
            "transportVlanId": 0,
            "ipAddressPoolSpec": {
                "description": "TEP pool",
                "name": "tep-ip-pool",
                "subnets": [
                    {
                        "ipAddressPoolRanges": [{"end": "10.0.1.20", "start": "10.0.1.10"}],
                        "gateway": "10.0.1.1",
                        "cidr": "10.0.1.0/24",
                    }
                ],
            },
            "vpcSpec": {
                "dtgwSpec": {
                    "vlan": 100,
                    "externalIpBlockCidr": "10.10.0.0/16",
                    "gatewayCidr": "10.100.0.1/24",
                    "privateTgwIpBlockCidr": "10.20.0.0/16",
                }
            },
            "useExistingDeployment": False,
        },
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")

    dvs = ordered["dvsSpecs"][0]
    self.assertEqual(
        list(dvs.keys()),
        ["dvsName", "vmnicsToUplinks", "networks", "mtu", "nsxTeamings", "nsxtSwitchConfig", "lagSpecs"],
    )
    self.assertEqual(list(dvs["vmnicsToUplinks"][0].keys()), ["id", "uplink"])
    self.assertEqual(list(dvs["nsxTeamings"][0].keys()), ["policy", "activeUplinks"])
    self.assertEqual(
        list(dvs["nsxtSwitchConfig"].keys()),
        ["transportZones", "hostSwitchOperationalMode"],
    )
    self.assertEqual(
        list(dvs["nsxtSwitchConfig"]["transportZones"][0].keys()),
        ["name", "transportType"],
    )

    nsxt = ordered["nsxtSpec"]
    self.assertEqual(
        list(nsxt.keys()),
        [
            "vipFqdn",
            "nsxtManagers",
            "rootNsxtManagerPassword",
            "nsxtAdminPassword",
            "nsxtAuditPassword",
            "transportVlanId",
            "nsxtManagerSize",
            "ipAddressPoolSpec",
            "vpcSpec",
            "version",
            "useExistingDeployment",
        ],
    )
    pool = nsxt["ipAddressPoolSpec"]
    self.assertEqual(list(pool.keys()), ["name", "description", "subnets"])
    subnet = pool["subnets"][0]
    self.assertEqual(list(subnet.keys()), ["cidr", "gateway", "ipAddressPoolRanges"])
    self.assertEqual(
        list(subnet["ipAddressPoolRanges"][0].keys()), ["start", "end"]
    )
    dtgw = nsxt["vpcSpec"]["dtgwSpec"]
    self.assertEqual(
        list(dtgw.keys()),
        ["vlan", "gatewayCidr", "externalIpBlockCidr", "privateTgwIpBlockCidr"],
    )

  def test_reorder_datastore_and_appliances_specs(self):
    """Verifies ordering for datastore, vSAN, VSP cluster, and appliance specs."""
    unordered = {
        "datastoreSpec": {
            "vsanSpec": {
                "failuresToTolerate": "1",
                "datastoreName": "vsanDatastore",
                "encryptionConfig": {"dataInTransitConfig": {"enable": False}},
                "vsanDedup": False,
                "esaConfig": {"enabled": True},
            }
        },
        "vspClusterSpec": {
            "size": "medium",
            "name": "vsp-cluster",
            "ipv4Pool": {
                "ipRange": {
                    "endIpAddress": "10.0.0.20",
                    "startIpAddress": "10.0.0.10",
                }
            },
            "platformFqdn": "vsp.test.local",
            "instanceFqdn": "shared.test.local",
            "fleetFqdn": "fleet.test.local",
            "internalClusterCidrIpv4": "198.18.0.0/15",
            "systemUserPassword": "pwd",
        },
        "vcfOperationsSpec": {
            "useExistingDeployment": False,
            "loadBalancerFqdn": "lb.test.local",
            "adminUserPassword": "pwd",
            "applianceSize": "medium",
            "nodes": [
                {
                    "type": "master",
                    "hostname": "ops-node.test.local",
                    "rootUserPassword": "pwd",
                }
            ],
        },
        "vcfOperationsCollectorSpec": {
            "useExistingDeployment": False,
            "rootUserPassword": "pwd",
            "hostname": "collector.test.local",
            "applianceSize": "standard",
        },
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")

    vsan = ordered["datastoreSpec"]["vsanSpec"]
    self.assertEqual(
        list(vsan.keys()),
        ["datastoreName", "vsanDedup", "failuresToTolerate", "esaConfig", "encryptionConfig"],
    )
    self.assertEqual(list(vsan["esaConfig"].keys()), ["enabled"])
    self.assertEqual(
        list(vsan["encryptionConfig"]["dataInTransitConfig"].keys()), ["enable"]
    )

    vsp = ordered["vspClusterSpec"]
    self.assertEqual(
        list(vsp.keys()),
        [
            "ipv4Pool",
            "platformFqdn",
            "instanceFqdn",
            "fleetFqdn",
            "size",
            "name",
            "internalClusterCidrIpv4",
            "systemUserPassword",
        ],
    )
    self.assertEqual(
        list(vsp["ipv4Pool"]["ipRange"].keys()), ["startIpAddress", "endIpAddress"]
    )

    ops = ordered["vcfOperationsSpec"]
    self.assertEqual(
        list(ops.keys()),
        ["nodes", "applianceSize", "loadBalancerFqdn", "adminUserPassword", "useExistingDeployment"],
    )
    self.assertEqual(
        list(ops["nodes"][0].keys()), ["hostname", "rootUserPassword", "type"]
    )

    coll = ordered["vcfOperationsCollectorSpec"]
    self.assertEqual(
        list(coll.keys()),
        ["applianceSize", "hostname", "useExistingDeployment", "rootUserPassword"],
    )

  def test_reorder_list_of_objects(self):
    """Verifies ordering within lists of dictionaries (e.g. hostSpecs, networkSpecs)."""
    unordered = {
        "hostSpecs": [
            {
                "credentials": {
                    "password": "pwd",
                    "username": "root",
                },
                "sslThumbprint": "11:22",
                "hostname": "esxi-1.test.local",
            },
            {
                "credentials": {
                    "password": "pwd",
                    "username": "root",
                },
                "sslThumbprint": "33:44",
                "hostname": "esxi-2.test.local",
            },
        ],
        "networkSpecs": [
            {
                "standbyUplinks": [],
                "ipAddressVersion": "IPv4",
                "gateway": "10.0.0.1",
                "subnet": "10.0.0.0/24",
                "networkType": "MANAGEMENT",
                "vlanId": 0,
                "includeIpAddressRanges": [
                    {
                        "endIpAddress": "10.0.0.100",
                        "startIpAddress": "10.0.0.10",
                    }
                ],
            }
        ],
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")

    for host in ordered["hostSpecs"]:
      self.assertEqual(list(host.keys()), ["hostname", "sslThumbprint", "credentials"])
      self.assertEqual(list(host["credentials"].keys()), ["username", "password"])

    net = ordered["networkSpecs"][0]
    self.assertEqual(
        list(net.keys())[:7],
        [
            "networkType",
            "subnet",
            "gateway",
            "includeIpAddressRanges",
            "vlanId",
            "ipAddressVersion",
            "standbyUplinks",
        ],
    )
    ip_range = net["includeIpAddressRanges"][0]
    self.assertEqual(list(ip_range.keys()), ["startIpAddress", "endIpAddress"])

  def test_reorder_updated_management_domain_deployment_config(self):
    """Verifies canonical field ordering for updated outputs.tf schema without passwords."""
    unordered = {
        "sddcId": "mgmt-domain",
        "version": "9.1.0",
        "workflowType": "VCF",
        "vcfInstanceName": "vcf1",
        "ceipEnabled": False,
        "vcenterSpec": {
            "ssoDomain": "gve.local",
            "useExistingDeployment": False,
            "vcenterHostname": "vc01.test.gve",
            "storageSize": "lstorage",
            "vmSize": "medium",
        },
        "nsxtSpec": {
            "nsxtManagerSize": "medium",
            "useExistingDeployment": False,
            "vipFqdn": "nsx01.test.gve",
            "transportVlanId": 250,
            "nsxtManagers": [{"hostname": "nsx02.test.gve"}],
        },
        "networkSpecs": [
            {
                "standbyUplinks": [],
                "networkType": "MANAGEMENT",
                "ipAddressVersion": "IPv4",
                "teamingPolicy": "loadbalance_loadbased",
                "subnet": "10.200.0.0/24",
                "gateway": "10.200.0.1",
                "vlanId": 0,
                "portGroupKey": "mgmt-domain-cl01-vds01-pg-esx-mgmt",
                "activeUplinks": ["uplink0"],
            }
        ],
        "sddcManagerSpec": {
            "useExistingDeployment": True,
            "hostname": "sddcm.test.gve",
            "localUserPassword": "<user_should_input_secret_manager_vcf-localuser-password>",
        },
        "vcfOperationsSpec": {
            "useExistingDeployment": False,
            "loadBalancerFqdn": "",
            "applianceSize": "medium",
            "nodes": [{"type": "master", "hostname": "ops01.test.gve"}],
        },
        "vcfOperationsCollectorSpec": {
            "useExistingDeployment": False,
            "hostname": "collector.test.gve",
            "applianceSize": "standard",
        },
        "dnsSpec": {
            "nameservers": ["10.200.0.4"],
            "subdomain": "gcve-vcf.test.gve",
        },
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")

    self.assertEqual(
        list(ordered["dnsSpec"].keys()),
        ["subdomain", "nameservers"],
    )
    self.assertEqual(ordered["dnsSpec"]["nameservers"], ["10.200.0.4"])
    self.assertEqual(
        list(ordered["vcenterSpec"].keys()),
        ["vcenterHostname", "vmSize", "storageSize", "ssoDomain", "useExistingDeployment"],
    )
    self.assertEqual(
        list(ordered["nsxtSpec"].keys()),
        ["vipFqdn", "nsxtManagers", "transportVlanId", "nsxtManagerSize", "useExistingDeployment"],
    )
    self.assertEqual(
        list(ordered["networkSpecs"][0].keys()),
        [
            "networkType",
            "subnet",
            "gateway",
            "vlanId",
            "portGroupKey",
            "activeUplinks",
            "teamingPolicy",
            "ipAddressVersion",
            "standbyUplinks",
        ],
    )
    self.assertEqual(
        list(ordered["sddcManagerSpec"].keys()),
        ["hostname", "localUserPassword", "useExistingDeployment"],
    )
    self.assertEqual(
        list(ordered["vcfOperationsSpec"].keys()),
        ["nodes", "applianceSize", "loadBalancerFqdn", "useExistingDeployment"],
    )
    self.assertEqual(
        list(ordered["vcfOperationsCollectorSpec"].keys()),
        ["applianceSize", "hostname", "useExistingDeployment"],
    )

  def test_reorder_dns_spec(self):
    """Verifies canonical field order for dnsSpec and preservation of nameservers list."""
    unordered = {
        "dnsSpec": {
            "nameservers": ["10.200.0.4", "10.200.0.5"],
            "subdomain": "gcve-vcf.test.gve",
        }
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")
    self.assertEqual(list(ordered["dnsSpec"].keys()), ["subdomain", "nameservers"])
    self.assertEqual(
        ordered["dnsSpec"]["nameservers"], ["10.200.0.4", "10.200.0.5"]
    )

  def test_reorder_vcf_deployment_config(self):
    """Verifies canonical field order for vcf_deployment_config in Python config."""
    unordered = {
        "vcf_installer_fqdn": "sddc.test.gve",
        "target_gce_node": "node-1",
        "dns_server": "10.200.0.4",
        "vcf_installer_ip_source": "fr-name",
        "vcf_appliance_root_password_secret": "sec-root",
        "offline_depot_subnet_cidr": "10.200.100.0/29",
        "vcf_appliance_local_user_password_secret": "sec-local",
    }
    ordered = export_deployment_config.reorder_object(
        unordered, "vcf_deployment_config"
    )
    self.assertEqual(
        list(ordered.keys()),
        [
            "target_gce_node",
            "offline_depot_subnet_cidr",
            "vcf_appliance_root_password_secret",
            "vcf_appliance_local_user_password_secret",
            "vcf_installer_ip_source",
            "vcf_installer_fqdn",
            "dns_server",
        ],
    )

  def test_reorder_primitives_and_empty(self):
    """Verifies that primitives, None, booleans, and empty collections pass through unchanged."""
    self.assertEqual(export_deployment_config.reorder_object("test_str"), "test_str")
    self.assertEqual(export_deployment_config.reorder_object(12345), 12345)
    self.assertEqual(export_deployment_config.reorder_object(True), True)
    self.assertIsNone(export_deployment_config.reorder_object(None))
    self.assertEqual(export_deployment_config.reorder_object({}), {})
    self.assertEqual(export_deployment_config.reorder_object([]), [])
    self.assertEqual(
        export_deployment_config.reorder_object(["b", "a"]), ["b", "a"]
    )


class TestExtractConfigValue(unittest.TestCase):
  """Tests for extract_config_value function."""

  def test_extract_wrapped_terraform_output(self):
    """Verifies extracting configuration from standard 'terraform output -json' wrapped structure."""
    outputs = {
        "management_domain_deployment_input_config": {
            "sensitive": False,
            "type": ["object", {}],
            "value": {
                "version": "5.2.0",
                "vcfInstanceName": "vcf-primary",
            },
        },
        "python_scripts_input_config": {
            "sensitive": False,
            "type": ["object", {}],
            "value": {
                "project": "test-proj",
                "vcf_deployment_config": {"target_gce_node": "node-1"},
            },
        },
    }

    mgmt_val = export_deployment_config.extract_config_value(
        outputs, export_deployment_config.MGMT_CONFIG_KEY
    )
    self.assertEqual(mgmt_val, {"version": "5.2.0", "vcfInstanceName": "vcf-primary"})

    py_val = export_deployment_config.extract_config_value(
        outputs, export_deployment_config.PYTHON_CONFIG_KEY
    )
    self.assertEqual(
        py_val,
        {
            "project": "test-proj",
            "vcf_deployment_config": {"target_gce_node": "node-1"},
        },
    )

  def test_extract_unwrapped_direct_output(self):
    """Verifies extracting configuration when output dictionary is already direct value."""
    outputs = {
        "management_domain_deployment_input_config": {
            "vcfInstanceName": "vcf-direct",
        },
        "python_scripts_input_config": {
            "project": "test-proj-direct",
        },
    }

    mgmt_val = export_deployment_config.extract_config_value(
        outputs, export_deployment_config.MGMT_CONFIG_KEY
    )
    self.assertEqual(mgmt_val, {"vcfInstanceName": "vcf-direct"})

    py_val = export_deployment_config.extract_config_value(
        outputs, export_deployment_config.PYTHON_CONFIG_KEY
    )
    self.assertEqual(py_val, {"project": "test-proj-direct"})

  def test_extract_from_root_config_directly(self):
    """Verifies detection when the input file is already the standalone extracted config."""
    mgmt_root = {
        "vcfInstanceName": "standalone-vcf",
        "version": "5.2.0",
    }
    self.assertEqual(
        export_deployment_config.extract_config_value(
            mgmt_root, export_deployment_config.MGMT_CONFIG_KEY
        ),
        mgmt_root,
    )

    py_root = {
        "project": "standalone-proj",
        "vcf_deployment_config": {"target_gce_node": "node-1"},
    }
    self.assertEqual(
        export_deployment_config.extract_config_value(
            py_root, export_deployment_config.PYTHON_CONFIG_KEY
        ),
        py_root,
    )

  def test_extract_missing_key_returns_none(self):
    """Verifies that missing keys return None."""
    outputs = {"unrelated_output": {"value": 123}}
    self.assertIsNone(
        export_deployment_config.extract_config_value(
            outputs, export_deployment_config.MGMT_CONFIG_KEY
        )
    )
    self.assertIsNone(
        export_deployment_config.extract_config_value(
            outputs, export_deployment_config.PYTHON_CONFIG_KEY
        )
    )


class TestLoadOutputsFromFileOrStdin(unittest.TestCase):
  """Tests for load_outputs_from_file_or_stdin function."""

  def test_load_from_valid_json_file(self):
    """Verifies loading JSON data from an existing file path."""
    data = {"sample_key": "sample_val", "nested": {"a": 1}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(data, f)
      temp_path = f.name

    try:
      loaded = export_deployment_config.load_outputs_from_file_or_stdin(temp_path)
      self.assertEqual(loaded, data)
    finally:
      if os.path.exists(temp_path):
        os.remove(temp_path)

  def test_load_from_stdin(self):
    """Verifies loading JSON data from standard input ('-')."""
    data = {"from_stdin": True, "count": 42}
    stdin_content = json.dumps(data)

    with mock.patch("sys.stdin", io.StringIO(stdin_content)):
      loaded = export_deployment_config.load_outputs_from_file_or_stdin("-")
      self.assertEqual(loaded, data)

  def test_load_non_existent_file_raises_runtime_error(self):
    """Verifies RuntimeError when specified input file does not exist."""
    with self.assertRaises(RuntimeError) as ctx:
      export_deployment_config.load_outputs_from_file_or_stdin("/non/existent/path.json")
    self.assertIn("Error reading JSON from", str(ctx.exception))

  def test_load_invalid_json_raises_runtime_error(self):
    """Verifies RuntimeError when input content is malformed JSON."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      f.write("INVALID JSON {")
      temp_path = f.name

    try:
      with self.assertRaises(RuntimeError) as ctx:
        export_deployment_config.load_outputs_from_file_or_stdin(temp_path)
      self.assertIn("Error reading JSON from", str(ctx.exception))
    finally:
      if os.path.exists(temp_path):
        os.remove(temp_path)


class TestGetTerraformOutputs(unittest.TestCase):
  """Tests for get_terraform_outputs execution wrapper."""

  @mock.patch("subprocess.run")
  def test_get_terraform_outputs_success(self, mock_run):
    """Verifies successful invocation and parsing of 'terraform output -json'."""
    expected_output = {
        "mgmt_out": {"value": {"vcfInstanceName": "vcf1"}},
    }
    mock_run.return_value = mock.Mock(
        returncode=0,
        stdout=json.dumps(expected_output),
        stderr="",
    )

    outputs = export_deployment_config.get_terraform_outputs("/fake/tf/dir")
    self.assertEqual(outputs, expected_output)
    mock_run.assert_called_once_with(
        ["terraform", "output", "-json"],
        cwd="/fake/tf/dir",
        capture_output=True,
        text=True,
        check=True,
    )

  @mock.patch("subprocess.run", side_effect=FileNotFoundError("No such file"))
  def test_get_terraform_outputs_missing_binary(self, mock_run):
    """Verifies informative RuntimeError when terraform executable is not in PATH."""
    with self.assertRaises(RuntimeError) as ctx:
      export_deployment_config.get_terraform_outputs()
    self.assertIn("'terraform' executable not found in PATH", str(ctx.exception))

  @mock.patch(
      "subprocess.run",
      side_effect=subprocess.CalledProcessError(
          returncode=1,
          cmd=["terraform", "output", "-json"],
          stderr="No state file found",
      ),
  )
  def test_get_terraform_outputs_called_process_error_with_stderr(self, mock_run):
    """Verifies RuntimeError when terraform command returns non-zero status with stderr."""
    with self.assertRaises(RuntimeError) as ctx:
      export_deployment_config.get_terraform_outputs()
    self.assertIn("Failed to execute 'terraform output -json'", str(ctx.exception))
    self.assertIn("No state file found", str(ctx.exception))

  @mock.patch(
      "subprocess.run",
      side_effect=subprocess.CalledProcessError(
          returncode=1,
          cmd=["terraform", "output", "-json"],
          stderr=None,
      ),
  )
  def test_get_terraform_outputs_called_process_error_without_stderr(self, mock_run):
    """Verifies RuntimeError when terraform command fails without stderr output."""
    with self.assertRaises(RuntimeError) as ctx:
      export_deployment_config.get_terraform_outputs()
    self.assertIn("Failed to execute 'terraform output -json'", str(ctx.exception))

  @mock.patch("subprocess.run")
  def test_get_terraform_outputs_invalid_json(self, mock_run):
    """Verifies RuntimeError when terraform output is not valid JSON."""
    mock_run.return_value = mock.Mock(
        returncode=0,
        stdout="Non-json warning message from CLI",
        stderr="",
    )
    with self.assertRaises(RuntimeError) as ctx:
      export_deployment_config.get_terraform_outputs()
    self.assertIn("Failed to parse Terraform output as JSON", str(ctx.exception))


class TestWriteJsonOutput(unittest.TestCase):
  """Tests for write_json_output serialization and file writing."""

  def test_write_to_stdout(self):
    """Verifies formatting and writing to stdout when output_path is None or '-'."""
    data = {"key": "value", "list": [1, 2]}
    expected_str = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    for target in [None, "-"]:
      with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        export_deployment_config.write_json_output(data, target)
        self.assertEqual(mock_stdout.getvalue(), expected_str)

  def test_write_to_file_in_new_directory(self):
    """Verifies writing JSON file and creating parent directories if necessary."""
    data = {"field_a": "alpha", "field_b": "beta"}
    with tempfile.TemporaryDirectory() as temp_dir:
      target_file = os.path.join(temp_dir, "nested", "sub_dir", "output.json")
      with mock.patch("sys.stderr", new_callable=io.StringIO):
        export_deployment_config.write_json_output(data, target_file)

      self.assertTrue(os.path.exists(target_file))
      with open(target_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
      self.assertEqual(loaded, data)


class TestParseArgs(unittest.TestCase):
  """Tests for CLI argument parsing."""

  def test_default_args(self):
    """Verifies default argument values."""
    with mock.patch("sys.argv", ["export_deployment_config.py"]):
      args = export_deployment_config.parse_args()
      self.assertEqual(args.config, "mgmt")
      self.assertEqual(args.terraform_dir, ".")
      self.assertIsNone(args.input_file)
      self.assertIsNone(args.output)
      self.assertIsNone(args.output_dir)
      self.assertIsNone(args.output_mgmt)
      self.assertIsNone(args.output_python)

  def test_explicit_args(self):
    """Verifies parsing of explicit CLI options."""
    test_argv = [
        "export_deployment_config.py",
        "-i", "input.json",
        "-d", "/path/to/tf",
        "-c", "all",
        "-o", "custom_out.json",
        "--output-dir", "/out/dir",
        "--output-mgmt", "/out/mgmt.json",
        "--output-python", "/out/py.json",
    ]
    with mock.patch("sys.argv", test_argv):
      args = export_deployment_config.parse_args()
      self.assertEqual(args.input_file, "input.json")
      self.assertEqual(args.terraform_dir, "/path/to/tf")
      self.assertEqual(args.config, "all")
      self.assertEqual(args.output, "custom_out.json")
      self.assertEqual(args.output_dir, "/out/dir")
      self.assertEqual(args.output_mgmt, "/out/mgmt.json")
      self.assertEqual(args.output_python, "/out/py.json")

  def test_invalid_config_choice_exits(self):
    """Verifies SystemExit on invalid --config option."""
    with mock.patch("sys.argv", ["export_deployment_config.py", "-c", "invalid_choice"]):
      with mock.patch("sys.stderr", new_callable=io.StringIO):
        with self.assertRaises(SystemExit):
          export_deployment_config.parse_args()


class TestMainWorkflow(unittest.TestCase):
  """Integration and scenario tests for the main() function."""

  def setUp(self):
    super().setUp()
    self.sample_tf_outputs = {
        "management_domain_deployment_input_config": {
            "value": {
                "workflowType": "VCF",
                "version": "5.2.0",
                "vcfInstanceName": "vcf-main",
            }
        },
        "python_scripts_input_config": {
            "value": {
                "zone": "us-east4-b",
                "project": "test-project-10",
                "vcf_deployment_config": {
                    "vcf_installer_fqdn": "sddc.test.local",
                    "target_gce_node": "node-1",
                },
            }
        },
    }

  def test_main_export_mgmt_to_stdout(self):
    """Verifies main() exports management config to stdout when --config mgmt."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    try:
      with mock.patch(
          "sys.argv",
          ["export_deployment_config.py", "-i", input_file, "-c", "mgmt"],
      ):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
          ret = export_deployment_config.main()
          self.assertEqual(ret, 0)
          exported = json.loads(mock_stdout.getvalue())
          self.assertEqual(exported["vcfInstanceName"], "vcf-main")
          self.assertEqual(list(exported.keys())[:3], ["version", "vcfInstanceName", "workflowType"])
    finally:
      if os.path.exists(input_file):
        os.remove(input_file)

  def test_main_export_mgmt_to_output_dir(self):
    """Verifies main() exports management config to default filename in --output-dir."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "mgmt",
                "--output-dir", temp_dir,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO):
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)
            target = os.path.join(temp_dir, export_deployment_config.DEFAULT_MGMT_OUTPUT_FILENAME)
            self.assertTrue(os.path.exists(target))
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_export_mgmt_with_output_mgmt_override(self):
    """Verifies main() prioritizes --output-mgmt flag."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      custom_mgmt = os.path.join(temp_dir, "custom_mgmt.json")
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "mgmt",
                "--output-mgmt", custom_mgmt,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO):
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.exists(custom_mgmt))
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_export_python_to_file(self):
    """Verifies main() exports python config to a designated output file."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      out_path = os.path.join(temp_dir, "python_cfg.json")
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "python",
                "-o", out_path,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO):
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, "r", encoding="utf-8") as out_f:
              exported = json.load(out_f)
            self.assertEqual(exported["project"], "test-project-10")
            self.assertEqual(list(exported.keys())[:2], ["project", "zone"])
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_export_python_to_output_dir(self):
    """Verifies main() exports python config to default filename in --output-dir."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "python",
                "--output-dir", temp_dir,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO):
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)
            target = os.path.join(temp_dir, export_deployment_config.DEFAULT_PYTHON_OUTPUT_FILENAME)
            self.assertTrue(os.path.exists(target))
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_export_all_to_output_dir(self):
    """Verifies main() exports both configuration files when --config all and --output-dir is specified."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "all",
                "--output-dir", temp_dir,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO):
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)

            mgmt_file = os.path.join(temp_dir, export_deployment_config.DEFAULT_MGMT_OUTPUT_FILENAME)
            py_file = os.path.join(temp_dir, export_deployment_config.DEFAULT_PYTHON_OUTPUT_FILENAME)

            self.assertTrue(os.path.exists(mgmt_file))
            self.assertTrue(os.path.exists(py_file))

            with open(mgmt_file, "r") as mf:
              mgmt_data = json.load(mf)
            self.assertEqual(mgmt_data["vcfInstanceName"], "vcf-main")

            with open(py_file, "r") as pf:
              py_data = json.load(pf)
            self.assertEqual(py_data["project"], "test-project-10")
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_export_all_with_explicit_mgmt_and_python_paths(self):
    """Verifies main() supports explicit --output-mgmt and --output-python flags with --config all."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(self.sample_tf_outputs, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      custom_mgmt = os.path.join(temp_dir, "m.json")
      custom_py = os.path.join(temp_dir, "p.json")
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "all",
                "--output-mgmt", custom_mgmt,
                "--output-python", custom_py,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO):
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.exists(custom_mgmt))
            self.assertTrue(os.path.exists(custom_py))
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_missing_key_mgmt_raises_error_and_returns_1(self):
    """Verifies main() returns exit code 1 when required mgmt output key is missing."""
    empty_outputs = {"other_key": {"value": 123}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(empty_outputs, f)
      input_file = f.name

    try:
      with mock.patch(
          "sys.argv",
          ["export_deployment_config.py", "-i", input_file, "-c", "mgmt"],
      ):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
          ret = export_deployment_config.main()
          self.assertEqual(ret, 1)
          self.assertIn("not found in Terraform outputs", mock_stderr.getvalue())
    finally:
      if os.path.exists(input_file):
        os.remove(input_file)

  def test_main_missing_key_python_raises_error_and_returns_1(self):
    """Verifies main() returns exit code 1 when required python output key is missing."""
    empty_outputs = {"other_key": {"value": 123}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(empty_outputs, f)
      input_file = f.name

    try:
      with mock.patch(
          "sys.argv",
          ["export_deployment_config.py", "-i", input_file, "-c", "python"],
      ):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
          ret = export_deployment_config.main()
          self.assertEqual(ret, 1)
          self.assertIn("not found in Terraform outputs", mock_stderr.getvalue())
    finally:
      if os.path.exists(input_file):
        os.remove(input_file)

  def test_main_config_all_partial_missing_keys_warns(self):
    """Verifies main() logs warning for missing keys but exports available keys when --config all."""
    only_mgmt = {
        "management_domain_deployment_input_config": {
            "value": {
                "version": "5.2.0",
                "vcfInstanceName": "vcf-only",
            }
        }
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(only_mgmt, f)
      input_file = f.name

    with tempfile.TemporaryDirectory() as temp_dir:
      try:
        with mock.patch(
            "sys.argv",
            [
                "export_deployment_config.py",
                "-i", input_file,
                "-c", "all",
                "--output-dir", temp_dir,
            ],
        ):
          with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            ret = export_deployment_config.main()
            self.assertEqual(ret, 0)
            self.assertIn("Warning: 'python_scripts_input_config' not found", mock_stderr.getvalue())

            mgmt_file = os.path.join(temp_dir, export_deployment_config.DEFAULT_MGMT_OUTPUT_FILENAME)
            py_file = os.path.join(temp_dir, export_deployment_config.DEFAULT_PYTHON_OUTPUT_FILENAME)

            self.assertTrue(os.path.exists(mgmt_file))
            self.assertFalse(os.path.exists(py_file))
      finally:
        if os.path.exists(input_file):
          os.remove(input_file)

  def test_main_config_all_both_missing_keys_warns_and_succeeds(self):
    """Verifies main() logs warnings when both keys missing in --config all and returns 0."""
    empty = {"other": 123}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
      json.dump(empty, f)
      input_file = f.name

    try:
      with mock.patch(
          "sys.argv",
          ["export_deployment_config.py", "-i", input_file, "-c", "all"],
      ):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
          ret = export_deployment_config.main()
          self.assertEqual(ret, 0)
          self.assertIn("Warning: 'management_domain_deployment_input_config' not found", mock_stderr.getvalue())
          self.assertIn("Warning: 'python_scripts_input_config' not found", mock_stderr.getvalue())
    finally:
      if os.path.exists(input_file):
        os.remove(input_file)

  @mock.patch("export_deployment_config.get_terraform_outputs")
  @mock.patch("sys.stdin.isatty", return_value=True)
  def test_main_live_terraform_fallback(self, mock_isatty, mock_get_tf):
    """Verifies that main() calls get_terraform_outputs when stdin is a tty and no --input-file."""
    mock_get_tf.return_value = self.sample_tf_outputs
    with mock.patch(
        "sys.argv",
        ["export_deployment_config.py", "-c", "mgmt", "-d", "/tf/dir"],
    ):
      with mock.patch("sys.stdout", new_callable=io.StringIO):
        ret = export_deployment_config.main()
        self.assertEqual(ret, 0)
        mock_get_tf.assert_called_once_with("/tf/dir")

  @mock.patch("sys.stdin.isatty", return_value=False)
  @mock.patch("export_deployment_config.load_outputs_from_file_or_stdin")
  def test_main_stdin_pipe_detection(self, mock_load, mock_isatty):
    """Verifies that main() reads from stdin when piped (isatty is False) and no --input-file."""
    mock_load.return_value = self.sample_tf_outputs
    with mock.patch(
        "sys.argv",
        ["export_deployment_config.py", "-c", "mgmt"],
    ):
      with mock.patch("sys.stdout", new_callable=io.StringIO):
        ret = export_deployment_config.main()
        self.assertEqual(ret, 0)
        mock_load.assert_called_once_with("-")

  def test_reorder_network_specs_include_ip_address(self):
    """Verifies that includeIpAddress in networkSpecs is ordered after gateway and before vlanId."""
    unordered = {
        "networkSpecs": [
            {
                "standbyUplinks": [],
                "vlanId": 200,
                "mtu": 8700,
                "includeIpAddress": ["10.200.2.3", "10.200.2.4", "10.200.2.5"],
                "activeUplinks": ["uplink0"],
                "ipAddressVersion": "IPv4",
                "teamingPolicy": "loadbalance_loadbased",
                "gateway": "10.200.2.1",
                "subnet": "10.200.2.0/24",
                "portGroupKey": "mgmt-domain-cl01-vds01-pg-vmotion",
                "networkType": "VMOTION",
            }
        ]
    }
    ordered = export_deployment_config.reorder_object(unordered, "__root_mgmt__")
    net = ordered["networkSpecs"][0]
    self.assertEqual(
        list(net.keys()),
        [
            "networkType",
            "subnet",
            "gateway",
            "includeIpAddress",
            "vlanId",
            "mtu",
            "portGroupKey",
            "activeUplinks",
            "teamingPolicy",
            "ipAddressVersion",
            "standbyUplinks",
        ],
    )
    self.assertEqual(
        net["includeIpAddress"],
        ["10.200.2.3", "10.200.2.4", "10.200.2.5"],
    )


if __name__ == "__main__":
  unittest.main()
