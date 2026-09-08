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

"""Export Deployment Configuration from Terraform Outputs.

Extracts deployment configuration blocks from Terraform outputs and converts them
into formatted JSON files with strict field ordering aligned with schema specifications:
1. 'management_domain_deployment_input_config' -> VCF Cloud Foundation Deployment JSON input.
2. 'python_scripts_input_config' -> Python post-deployment automation configuration.

Sources supported:
- Live Terraform state via 'terraform output -json'
- Existing Terraform output JSON file or plan output artifact
- Standard input (pipe)

This script uses only Python standard libraries (no external dependencies).
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

# Supported configuration output keys
MGMT_CONFIG_KEY = "management_domain_deployment_input_config"
PYTHON_CONFIG_KEY = "python_scripts_input_config"

DEFAULT_MGMT_OUTPUT_FILENAME = "management_domain_deployment_input.json"
DEFAULT_PYTHON_OUTPUT_FILENAME = "python_scripts_input_config.json"

# Canonical field order maps for schema-compliant JSON serialization
FIELD_ORDERS: Dict[str, List[str]] = {
    "__root_mgmt__": [
        "version",
        "vcfInstanceName",
        "sddcId",
        "ceipEnabled",
        "workflowType",
        "dnsSpec",
        "ntpServers",
        "hostSpecs",
        "vcenterSpec",
        "clusterSpec",
        "dvsSpecs",
        "nsxtSpec",
        "networkSpecs",
        "sddcManagerSpec",
        "managementPoolName",
        "datastoreSpec",
        "vspClusterSpec",
        "fleetLcmSpec",
        "sddcLcmSpec",
        "fleetDepotSpec",
        "telemetryAcceptorSpec",
        "vidbSpec",
        "saltSpec",
        "saltRaasSpec",
        "vcfOperationsSpec",
        "vcfOperationsCollectorSpec",
        "licenseServerSpec",
    ],
    "__root_python__": [
        "project",
        "zone",
        "gce_nodes",
        "esxi_root_password_secret",
        "vcf_deployment_config",
    ],
    "dnsSpec": [
        "subdomain",
        "nameservers",
    ],
    "hostSpecs": [
        "hostname",
        "sslThumbprint",
        "credentials",
    ],
    "credentials": [
        "username",
        "password",
    ],
    "vcenterSpec": [
        "vcenterHostname",
        "vmSize",
        "storageSize",
        "rootVcenterPassword",
        "adminUserSsoPassword",
        "ssoDomain",
        "version",
        "useExistingDeployment",
    ],
    "clusterSpec": [
        "datacenterName",
        "clusterName",
    ],
    "dvsSpecs": [
        "dvsName",
        "vmnicsToUplinks",
        "networks",
        "mtu",
        "nsxTeamings",
        "nsxtSwitchConfig",
    ],
    "vmnicsToUplinks": [
        "id",
        "uplink",
    ],
    "nsxTeamings": [
        "policy",
        "activeUplinks",
    ],
    "nsxtSwitchConfig": [
        "transportZones",
        "hostSwitchOperationalMode",
    ],
    "transportZones": [
        "name",
        "transportType",
    ],
    "nsxtSpec": [
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
    "nsxtManagers": [
        "hostname",
    ],
    "ipAddressPoolSpec": [
        "name",
        "description",
        "subnets",
    ],
    "subnets": [
        "cidr",
        "gateway",
        "ipAddressPoolRanges",
    ],
    "ipAddressPoolRanges": [
        "start",
        "end",
    ],
    "vpcSpec": [
        "dtgwSpec",
    ],
    "dtgwSpec": [
        "vlan",
        "gatewayCidr",
        "externalIpBlockCidr",
        "privateTgwIpBlockCidr",
    ],
    "networkSpecs": [
        "networkType",
        "subnet",
        "gateway",
        "includeIpAddressRanges",
        "vlanId",
        "mtu",
        "portGroupKey",
        "activeUplinks",
        "teamingPolicy",
        "ipAddressVersion",
        "ipAddressAssignmentMode",
    ],
    "includeIpAddressRanges": [
        "startIpAddress",
        "endIpAddress",
    ],
    "sddcManagerSpec": [
        "hostname",
        "rootPassword",
        "sshPassword",
        "localUserPassword",
        "version",
        "useExistingDeployment",
        "sslThumbprint",
    ],
    "datastoreSpec": [
        "vsanSpec",
    ],
    "vsanSpec": [
        "datastoreName",
        "vsanDedup",
        "failuresToTolerate",
        "esaConfig",
        "encryptionConfig",
    ],
    "esaConfig": [
        "enabled",
    ],
    "encryptionConfig": [
        "dataInTransitConfig",
    ],
    "dataInTransitConfig": [
        "enable",
    ],
    "vspClusterSpec": [
        "ipv4Pool",
        "platformFqdn",
        "instanceFqdn",
        "fleetFqdn",
        "size",
        "name",
        "internalClusterCidrIpv4",
        "systemUserPassword",
    ],
    "ipv4Pool": [
        "ipRange",
    ],
    "ipRange": [
        "startIpAddress",
        "endIpAddress",
    ],
    "fleetLcmSpec": [
        "size",
        "hostname",
    ],
    "sddcLcmSpec": [
        "size",
        "hostname",
    ],
    "fleetDepotSpec": [
        "size",
    ],
    "telemetryAcceptorSpec": [
        "size",
    ],
    "vidbSpec": [
        "size",
        "hostname",
    ],
    "saltSpec": [
        "size",
    ],
    "saltRaasSpec": [
        "size",
    ],
    "vcfOperationsSpec": [
        "nodes",
        "applianceSize",
        "adminUserPassword",
        "useExistingDeployment",
    ],
    "nodes": [
        "hostname",
        "rootUserPassword",
        "type",
    ],
    "vcfOperationsCollectorSpec": [
        "applianceSize",
        "hostname",
        "useExistingDeployment",
        "rootUserPassword",
    ],
    "licenseServerSpec": [
        "hostname",
    ],
    "vcf_deployment_config": [
        "target_gce_node",
        "offline_depot_subnet_cidr",
        "vcf_appliance_root_password_secret",
        "vcf_appliance_local_user_password_secret",
        "vcf_installer_ip_source",
        "vcf_installer_fqdn",
        "dns_server",
    ],
}


def reorder_object(obj: Any, parent_key: str = "") -> Any:
  """Recursively orders dictionary keys according to canonical schema specifications.

  Keys present in FIELD_ORDERS for the parent_key are positioned first in exact
  predefined order; any unlisted keys are preserved at the end in their original sequence.

  Args:
      obj: Target dictionary, list, or primitive data value.
      parent_key: Key name of the parent object for schema lookup.

  Returns:
      Reordered dictionary/list or original primitive.
  """
  if isinstance(obj, dict):
    order_list = FIELD_ORDERS.get(parent_key, [])

    def sort_key(k: str) -> tuple:
      if k in order_list:
        return (0, order_list.index(k))
      return (1, k)

    ordered_dict = {}
    for k in sorted(obj.keys(), key=sort_key):
      ordered_dict[k] = reorder_object(obj[k], k)
    return ordered_dict

  if isinstance(obj, list):
    return [reorder_object(item, parent_key) for item in obj]

  return obj


def get_terraform_outputs(terraform_dir: Optional[str] = None) -> Dict[str, Any]:
  """Runs 'terraform output -json' in the specified directory and returns parsed JSON.

  Args:
      terraform_dir: Working directory where Terraform configuration and state reside.

  Returns:
      Dictionary of Terraform outputs.

  Raises:
      RuntimeError: If the terraform CLI command fails or returns non-zero status.
  """
  cwd = terraform_dir or os.getcwd()
  cmd = ["terraform", "output", "-json"]

  try:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
  except FileNotFoundError:
    raise RuntimeError(
        "Error: 'terraform' executable not found in PATH. "
        "Please ensure Terraform is installed or supply an input JSON file with --input-file."
    )
  except subprocess.CalledProcessError as e:
    stderr = e.stderr.strip() if e.stderr else str(e)
    raise RuntimeError(f"Failed to execute 'terraform output -json':\n{stderr}")
  except json.JSONDecodeError as e:
    raise RuntimeError(f"Failed to parse Terraform output as JSON: {e}")


def load_outputs_from_file_or_stdin(file_path: str) -> Dict[str, Any]:
  """Loads and parses JSON data from a file or standard input.

  Args:
      file_path: Path to the JSON file, or '-' to read from standard input.

  Returns:
      Dictionary of loaded JSON data.

  Raises:
      RuntimeError: If reading or JSON parsing fails.
  """
  try:
    if file_path == "-":
      content = sys.stdin.read()
    else:
      with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return json.loads(content)
  except Exception as e:
    raise RuntimeError(f"Error reading JSON from '{file_path}': {e}")


def extract_config_value(outputs: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
  """Extracts the underlying configuration object from Terraform outputs.

  Handles both raw 'terraform output -json' structures (which nest actual values
  under a 'value' key) and direct configuration dictionaries.

  Args:
      outputs: Dictionary of Terraform outputs or direct config.
      key: Target output key name.

  Returns:
      Extracted configuration dictionary, or None if the key is not found.
  """
  if key in outputs:
    entry = outputs[key]
    if isinstance(entry, dict) and "value" in entry:
      return entry["value"]
    return entry

  # Check if the outputs dict is already the extracted target config directly
  if key == MGMT_CONFIG_KEY and "vcfInstanceName" in outputs:
    return outputs
  if key == PYTHON_CONFIG_KEY and "vcf_deployment_config" in outputs:
    return outputs

  return None


def write_json_output(data: Any, output_path: Optional[str] = None) -> None:
  """Serializes data to formatted JSON, writing to a file or stdout.

  Args:
      data: Data structure to serialize.
      output_path: Target file path, '-' for stdout, or None for stdout.
  """
  formatted_json = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

  if not output_path or output_path == "-":
    sys.stdout.write(formatted_json)
    sys.stdout.flush()
  else:
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir and not os.path.exists(output_dir):
      os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
      f.write(formatted_json)
    print(f"Successfully exported configuration to: {output_path}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
  """Parses command line arguments."""
  parser = argparse.ArgumentParser(
      description=(
          "Convert Terraform outputs into deployment configuration JSON files "
          "with preserved field order for VCF Cloud Foundation deployment and Python automation scripts."
      ),
      formatter_class=argparse.RawDescriptionHelpFormatter,
      epilog=(
          "Examples:\n"
          "  # Export Management Domain config from live Terraform state to stdout:\n"
          "  python3 export_deployment_config.py\n\n"
          "  # Export Management Domain config to a specific JSON file:\n"
          "  python3 export_deployment_config.py --output mgmt_input.json\n\n"
          "  # Export Python scripts input config:\n"
          "  python3 export_deployment_config.py --config python --output python_input.json\n\n"
          "  # Export both configurations to an output directory:\n"
          "  python3 export_deployment_config.py --config all --output-dir ./configs\n\n"
          "  # Convert from an existing terraform output JSON file:\n"
          "  python3 export_deployment_config.py --input-file outputs.json --output mgmt_input.json\n\n"
          "  # Pipe terraform output JSON into the script:\n"
          "  terraform output -json | python3 export_deployment_config.py --input-file -\n"
      ),
  )

  parser.add_argument(
      "-i",
      "--input-file",
      help=(
          "Path to Terraform outputs JSON file, or '-' to read from stdin. "
          "If omitted and stdin is not piped, executes 'terraform output -json'."
      ),
  )
  parser.add_argument(
      "-d",
      "--terraform-dir",
      default=".",
      help="Directory to execute 'terraform output -json' in (default: current directory).",
  )
  parser.add_argument(
      "-c",
      "--config",
      choices=["mgmt", "python", "all"],
      default="mgmt",
      help=(
          "Which configuration section to export: "
          "'mgmt' (management_domain_deployment_input_config), "
          "'python' (python_scripts_input_config), or "
          "'all' (both configurations). Default: 'mgmt'."
      ),
  )
  parser.add_argument(
      "-o",
      "--output",
      help=(
          "Path to output JSON file, or '-' for stdout (default). "
          "When --config is 'all', use --output-dir instead."
      ),
  )
  parser.add_argument(
      "--output-dir",
      help=(
          "Directory where JSON configuration files will be saved when "
          "--config is 'all' or when individual filenames are defaulted."
      ),
  )
  parser.add_argument(
      "--output-mgmt",
      help="Explicit output filepath for management_domain_deployment_input_config.",
  )
  parser.add_argument(
      "--output-python",
      help="Explicit output filepath for python_scripts_input_config.",
  )

  return parser.parse_args()


def main() -> int:
  """Main entry point."""
  args = parse_args()

  try:
    # 1. Load Terraform outputs from file, stdin, or live Terraform CLI
    if args.input_file:
      outputs = load_outputs_from_file_or_stdin(args.input_file)
    elif not sys.stdin.isatty():
      outputs = load_outputs_from_file_or_stdin("-")
    else:
      outputs = get_terraform_outputs(args.terraform_dir)

    # 2. Extract and order configurations
    raw_mgmt = extract_config_value(outputs, MGMT_CONFIG_KEY)
    mgmt_config = reorder_object(raw_mgmt, "__root_mgmt__") if raw_mgmt is not None else None

    raw_python = extract_config_value(outputs, PYTHON_CONFIG_KEY)
    python_config = reorder_object(raw_python, "__root_python__") if raw_python is not None else None

    # 3. Export requested configuration(s)
    if args.config == "mgmt":
      if mgmt_config is None:
        raise ValueError(
            f"Output key '{MGMT_CONFIG_KEY}' not found in Terraform outputs. "
            "Ensure Terraform has been applied successfully."
        )
      target_out = args.output_mgmt or args.output
      if not target_out and args.output_dir:
        target_out = os.path.join(args.output_dir, DEFAULT_MGMT_OUTPUT_FILENAME)
      write_json_output(mgmt_config, target_out)

    elif args.config == "python":
      if python_config is None:
        raise ValueError(
            f"Output key '{PYTHON_CONFIG_KEY}' not found in Terraform outputs. "
            "Ensure Terraform has been applied successfully."
        )
      target_out = args.output_python or args.output
      if not target_out and args.output_dir:
        target_out = os.path.join(args.output_dir, DEFAULT_PYTHON_OUTPUT_FILENAME)
      write_json_output(python_config, target_out)

    elif args.config == "all":
      out_dir = args.output_dir or "."
      if mgmt_config is not None:
        mgmt_path = args.output_mgmt or os.path.join(out_dir, DEFAULT_MGMT_OUTPUT_FILENAME)
        write_json_output(mgmt_config, mgmt_path)
      else:
        print(f"Warning: '{MGMT_CONFIG_KEY}' not found in outputs, skipping.", file=sys.stderr)

      if python_config is not None:
        python_path = args.output_python or os.path.join(out_dir, DEFAULT_PYTHON_OUTPUT_FILENAME)
        write_json_output(python_config, python_path)
      else:
        print(f"Warning: '{PYTHON_CONFIG_KEY}' not found in outputs, skipping.", file=sys.stderr)

    return 0

  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  sys.exit(main())
