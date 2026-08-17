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

# ==============================================================================
# File: infrastructure/vars.tf
# Description: Defines all input variables for the main infrastructure module.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Project ID
# ------------------------------------------------------------------------------
variable "project_id" {
  type        = string
  description = <<EOT
Meaning: The GCP Project ID where all resources (VPC/subnet, Jumpbox instance) will be provisioned.
Pre-req: An existing Google Cloud Project with billing enabled, and required APIs enabled (compute.googleapis.com, iap.googleapis.com). If the project is hosting the ESXi hosts, it should have secretmanager.googleapis.com,
compute.googleapis.com APIs enabled for smooth execution of the python scripts from the jumpbox.
Possible value: Standard GCP project ID string, e.g., "my-gcp-project-12345".
Required or Not: Required.
EOT

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "The 'project_id' must be 6 to 30 characters long, start with a lowercase letter, contain only lowercase letters, digits, and hyphens, and not end with a hyphen."
  }
}

# ------------------------------------------------------------------------------
# 2. Region
# ------------------------------------------------------------------------------
variable "region" {
  type        = string
  description = <<EOT
Meaning: The GCP region where the subnetwork and NAT resources will be deployed.
Pre-req: Region must be supported in your GCP project and have necessary compute resources available.
Possible value: Any valid GCP region identifier, e.g., "us-central1", "europe-west1", "asia-east1".
Required or Not: Required.
EOT

  validation {
    condition     = can(regex("^[a-z]+-[a-z0-9]+$", var.region))
    error_message = "The 'region' must be a valid GCP region string (e.g., 'us-central1', 'europe-west1')."
  }
}

# ------------------------------------------------------------------------------
# 3. Subnet Name (Optional)
# ------------------------------------------------------------------------------
variable "subnet_name" {
  type        = string
  default     = "smve-toolkit-subnet"
  description = <<EOT
Meaning: The name of the GCP Subnetwork used for the jumpbox.
Pre-req: If `create_subnet` is set to false, this subnetwork must already exist in the specified `vpc_name` and `region`, with connectivity to target ESXi host(s) and available IP capacity for 1 GCE instance.
Possible value: RFC1035 compliant GCP resource name string, e.g., "smve-toolkit-subnet" or "custom-jumpbox-subnet".
Required or Not: Optional (defaults to "smve-toolkit-subnet").
EOT

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.subnet_name))
    error_message = "The 'subnet_name' must be 1 to 63 characters long, begin with a lowercase letter, contain only lowercase letters, numbers, and hyphens, and end with a lowercase letter or number (RFC1035 compliant)."
  }
}

# ------------------------------------------------------------------------------
# 4. Create Subnet Flag (Optional)
# ------------------------------------------------------------------------------
variable "create_subnet" {
  type        = bool
  default     = true
  description = <<EOT
Meaning: Flag determining whether Terraform should create a new subnetwork (`true`) or look up an existing subnetwork (`false`).
Pre-req: If set to `true`, `vpc_name` and `subnet_cidr` must be supplied. If set to `false`, an existing subnet matching `subnet_name` in `region` must exist.
Possible value: `true` or `false`.
Required or Not: Optional (defaults to `true`).
EOT
}

# ------------------------------------------------------------------------------
# 5. VPC Name (Conditionally Required)
# ------------------------------------------------------------------------------
variable "vpc_name" {
  type        = string
  default     = ""
  description = <<EOT
Meaning: The name of the VPC network where the subnet exists or will be created. The VPC must have network connectivity to the target ESXi host(s) (e.g. via VPC Peering, Cloud VPN, Direct Interconnect, or being the ESXi VPC itself).
Pre-req: The VPC network must exist in the target GCP project.
Possible value: VPC network name string, e.g., "custom-vpc-network" or "default".
Required or Not: Required if `create_subnet = true`; Optional if an existing subnet is supplied (`create_subnet = false`).
EOT
}

# ------------------------------------------------------------------------------
# 6. Subnet CIDR (Conditionally Required)
# ------------------------------------------------------------------------------
variable "subnet_cidr" {
  type        = string
  default     = ""
  description = <<EOT
Meaning: The IPv4 CIDR block for the subnet to be created. Minimum mask size is /29 (e.g., 8 IP addresses).
Pre-req: Must be an unallocated, valid primary CIDR range within the host VPC network space. Minimum mask size must be /29 or larger (e.g., /28, /24).
Possible value: Standard IPv4 CIDR string, e.g., "10.10.10.0/28" or "172.16.0.0/24".
Required or Not: Required if `create_subnet = true`; Not required if using an existing subnet (`create_subnet = false`).
EOT
}

# ------------------------------------------------------------------------------
# 7. Jumpbox Name (Optional)
# ------------------------------------------------------------------------------
variable "jumpbox_name" {
  type        = string
  default     = "smve-toolkit-jumpbox"
  description = <<EOT
Meaning: The name assigned to the GCE virtual machine instance acting as the jumpbox.
Pre-req: Must be a unique GCE instance name within the target GCP project and zone.
Possible value: RFC1035 compliant string, e.g., "smve-toolkit-jumpbox" or "esxi-prep-jumpbox".
Required or Not: Optional (defaults to "smve-toolkit-jumpbox").
EOT

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.jumpbox_name))
    error_message = "The 'jumpbox_name' must be 1 to 63 characters long, begin with a lowercase letter, contain only lowercase letters, numbers, and hyphens, and end with a lowercase letter or number (RFC1035 compliant)."
  }
}

# ------------------------------------------------------------------------------
# 8. Zone (Optional - Recommended to match ESXi zone)
# ------------------------------------------------------------------------------
variable "zone" {
  type        = string
  default     = ""
  description = <<EOT
Meaning: The specific GCP zone within `region` where the jumpbox VM will be created.
RECOMMENDATION: It is strongly recommended to specify the exact GCP zone where your ESXi instances/hosts reside. Deploying the jumpbox in the same zone minimizes network latency, avoids inter-zone data egress charges, and optimizes routing during script execution.
Pre-req: Zone must exist within the selected `region` and match the zone hosting your target ESXi instances. If left empty (""), Terraform defaults to `$${var.region}-a`.
Possible value: GCP zone identifier string, e.g., "us-central1-a", "europe-west1-b".
Required or Not: Optional (defaults to `$${var.region}-a`, but user should preferably specify the zone matching ESXi instances).
EOT

  validation {
    condition     = var.zone == "" || can(regex("^[a-z]+-[a-z0-9]+-[a-z0-9]+$", var.zone))
    error_message = "The 'zone' must be an empty string (to default to '<region>-a') or a valid GCP zone identifier format (e.g., 'us-central1-a', 'europe-west1-b')."
  }
}

# ------------------------------------------------------------------------------
# 9. Enable Internet Egress Flag (Optional)
# ------------------------------------------------------------------------------
variable "enable_internet" {
  type        = bool
  default     = true
  description = <<EOT
Meaning: Flag determining whether Terraform should create a Cloud Router and Cloud NAT gateway in the region for outbound internet access (e.g. software/package downloads). Set to `false` post-setup to tear down NAT/Router and disable internet egress.
Pre-req: If `create_subnet = false` (using existing subnet) and that subnet/VPC already has Cloud NAT and a default internet route (0.0.0.0/0 via default-internet-gateway), set `enable_internet = false`. If using an existing subnet without NAT, leave `enable_internet = true` to provision Cloud Router and NAT for it during setup.
Possible value: `true` or `false`.
Required or Not: Optional (defaults to `true`).
EOT
}

# ------------------------------------------------------------------------------
# 10. Machine Type (Optional)
# ------------------------------------------------------------------------------
variable "machine_type" {
  type        = string
  default     = "e2-micro"
  description = <<EOT
Meaning: The machine type for the jumpbox GCE VM instance.
Pre-req: Must be a valid GCP machine type available in the selected zone.
Possible value: GCP machine type string, e.g., "e2-micro", "e2-small", "e2-medium", "n2-standard-4", or custom machine shape "custom-2-4096".
Required or Not: Optional (defaults to "e2-micro").
EOT

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)+$", var.machine_type))
    error_message = "The 'machine_type' must be a valid GCP machine type identifier format (e.g., 'e2-micro', 'e2-medium', 'n2-standard-4', or 'custom-2-4096')."
  }
}

# ------------------------------------------------------------------------------
# 11. Boot Disk Size (Optional)
# ------------------------------------------------------------------------------
variable "boot_disk_size" {
  type        = number
  default     = 30
  description = <<EOT
Meaning: The boot disk size in GB for the jumpbox GCE VM instance.
Pre-req: Minimum size of 10 GB required for standard Linux OS images.
Possible value: Positive integer representing disk size in GB, e.g., 30, 50, 100.
Required or Not: Optional (defaults to 30).
EOT

  validation {
    condition     = var.boot_disk_size >= 10 && var.boot_disk_size <= 65536
    error_message = "The 'boot_disk_size' must be an integer between 10 GB (minimum required for OS image) and 65536 GB."
  }
}

# ------------------------------------------------------------------------------
# 12. Boot Disk Type (Optional)
# ------------------------------------------------------------------------------
variable "boot_disk_type" {
  type        = string
  default     = "pd-balanced"
  description = <<EOT
Meaning: The persistent disk type for the jumpbox boot disk.
Pre-req: Must be a supported disk type in GCP (e.g., pd-balanced, pd-standard, pd-ssd, pd-extreme).
Possible value: "pd-balanced", "pd-standard", "pd-ssd", "pd-extreme".
Required or Not: Optional (defaults to "pd-balanced").
EOT

  validation {
    condition     = contains(["pd-standard", "pd-balanced", "pd-ssd", "pd-extreme"], var.boot_disk_type)
    error_message = "The 'boot_disk_type' must be one of: 'pd-standard', 'pd-balanced', 'pd-ssd', 'pd-extreme'."
  }
}

# ------------------------------------------------------------------------------
# 13. Boot Disk Image (Optional)
# ------------------------------------------------------------------------------
variable "boot_disk_image" {
  type        = string
  default     = "debian-cloud/debian-12"
  description = <<EOT
Meaning: The OS boot disk image family or specific image self_link for the jumpbox VM.
Pre-req: Must be a valid OS image available in GCP (e.g., Debian 12, Ubuntu 22.04 LTS). Debian 12 is recommended for optimal compatibility with the SMVE Toolkit.
Possible value: Image family or image resource URI, e.g., "debian-cloud/debian-12", "ubuntu-os-cloud/ubuntu-2204-lts".
Required or Not: Optional (defaults to "debian-cloud/debian-12").
EOT
}

# ------------------------------------------------------------------------------
# 14. Jumpbox Internal IP (Optional)
# ------------------------------------------------------------------------------
variable "jumpbox_internal_ip" {
  type        = string
  default     = ""
  description = <<EOT
Meaning: Static internal IPv4 address or reserved internal IP address name/URI to assign to the jumpbox VM. If omitted or empty (""), GCP dynamically allocates an ephemeral internal IP from the subnet.
Pre-req: If specifying a literal IPv4 address, it must be an unallocated IP within the subnet's CIDR range. If specifying a reserved address name or URI, the reserved compute address (`google_compute_address`) must already exist in the target region and subnetwork.
Possible value: IPv4 address string (e.g. "10.10.0.5"), reserved IP address resource name (e.g. "my-reserved-jumpbox-ip"), or full resource URI (e.g. "projects/my-project/regions/us-central1/addresses/my-reserved-jumpbox-ip").
Required or Not: Optional (defaults to "" for dynamic/ephemeral internal IP).
EOT

  validation {
    condition     = var.jumpbox_internal_ip == "" || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", var.jumpbox_internal_ip)) || can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.jumpbox_internal_ip)) || can(regex("^projects/.+/regions/.+/addresses/.+$", var.jumpbox_internal_ip))
    error_message = "The 'jumpbox_internal_ip' must be an empty string, a valid IPv4 address (e.g., '10.10.0.5'), an RFC1035-compliant reserved address name, or a full address resource URI."
  }
}

# ------------------------------------------------------------------------------
# 15. Service Account Email (Optional)
# ------------------------------------------------------------------------------
variable "service_account_email" {
  type        = string
  default     = ""
  description = <<EOT
Meaning: The email of the Service Account to attach to the Jumpbox VM and target in the IAP SSH ingress firewall rule.
Pre-req: If specified, the Service Account must exist in GCP and have appropriate permissions. If left empty (""), the module automatically queries and uses the default Compute Engine service account (<project-number>-compute@developer.gserviceaccount.com).
Possible value: Valid GCP Service Account email string, e.g., "my-custom-sa@my-project.iam.gserviceaccount.com", or "" for Compute Engine default SA.
Required or Not: Optional (defaults to "" for default Compute Engine SA).
EOT

  validation {
    condition     = var.service_account_email == "" || can(regex("^[a-z0-9-]+@[a-z0-9-.]+\\.gserviceaccount\\.com$", var.service_account_email))
    error_message = "The 'service_account_email' must be an empty string (to default to Compute Engine default SA) or a valid GCP Service Account email ending in '.gserviceaccount.com'."
  }
}
