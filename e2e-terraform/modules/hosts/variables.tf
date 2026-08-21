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

variable "project_id" {
  type        = string
  description = "GCP Project ID for host compute instances."
}

variable "region" {
  type        = string
  description = "Target GCP Region for infrastructure provisioning."
}

variable "zone" {
  type        = string
  description = "Target GCP Zone for bare-metal ESXi hosts."
}

variable "resource_name_prefix" {
  type        = string
  default     = "myvcf"
  description = "Global prefix prepended to all generated resource names."
}

# ------------------------------------------------------------------------------
# Bare-Metal ESXi Compute Hosts
# ------------------------------------------------------------------------------

variable "number_of_nodes" {
  type        = number
  default     = 4
  description = "Total number of bare-metal ESXi compute nodes provisioned (range 1 to 32)."
  validation {
    condition     = var.number_of_nodes >= 1 && var.number_of_nodes <= 32
    error_message = "Number of nodes must be between 1 and 32."
  }
}

variable "machine_type" {
  type        = string
  default     = "z3-highmem-192-highlssd-metal"
  description = "Bare-metal machine type (z3-highmem-192-highlssd-metal or z3-highmem-192-metal)."
  validation {
    condition     = contains(["z3-highmem-192-highlssd-metal", "z3-highmem-192-metal"], var.machine_type)
    error_message = "Machine type must be either 'z3-highmem-192-highlssd-metal' or 'z3-highmem-192-metal'."
  }
}

variable "esxi_image" {
  type        = string
  description = "Full resource URI of the ESXi OS image for bare-metal host instances (e.g. 'projects/<project>/global/images/<image-name>'). Must be a valid full ESXi image resource URI."
  validation {
    condition     = can(regex("^(?:https://www\\.googleapis\\.com/compute/v1/)?projects/[^/]+/global/images/.+$", var.esxi_image))
    error_message = "esxi_image must be a valid full ESXi image resource URI (e.g. 'projects/<project>/global/images/vmware-esxi-9-1-0-dm-v20260513' or 'projects/<project>/global/images/esxi-8-0-2-12345678')."
  }
}

variable "node_names" {
  type        = list(string)
  default     = null
  description = "Explicit list of GCE node instance names."
}

variable "domain_name" {
  type        = string
  description = "Domain name appended to node names to generate node FQDN hostnames (and used in DNS)."
}

variable "deletion_protection" {
  type        = bool
  default     = true
  description = "Protects instances from accidental deletion via GCE API / Terraform."
}

# ------------------------------------------------------------------------------
# Placement Policy
# ------------------------------------------------------------------------------

variable "create_placement_policy" {
  type        = bool
  default     = true
  description = "Flag to create a new placement policy (true) or reference an existing one (false). If false, the input placement policy is expected to exist in GCP."
}

variable "placement_policy_name" {
  type        = string
  default     = null
  description = "Resource name of the Compute placement policy. Created if create_placement_policy is true. Expected to exist in GCP if create_placement_policy is false."
}

variable "availability_count" {
  type        = number
  default     = 6
  description = "Number of availability domains configured in the placement policy (range 5 to 8)."
  validation {
    condition     = var.availability_count >= 5 && var.availability_count <= 8
    error_message = "availability_count must be between 5 and 8."
  }
}

variable "availability_domains" {
  type        = list(number)
  default     = null
  description = "Optional list of availability domain IDs per host (values 1 to availability_count). Defaults to round-robin distribution (1 to availability_count) if not specified."
  validation {
    condition     = var.availability_domains == null || alltrue([for ad in var.availability_domains : ad >= 1])
    error_message = "All elements in availability_domains must be greater than or equal to 1."
  }
}

# ------------------------------------------------------------------------------
# Management NIC Configuration
# ------------------------------------------------------------------------------

variable "mgmt_subnet_name" {
  type        = string
  description = "Name of the Management subnetwork for nic0."
}

variable "mgmt_subnet_cidr" {
  type        = string
  default     = null
  description = "Optional CIDR block of the Management subnetwork for IP validation."
}

variable "mgmt_neg_name" {
  type        = string
  default     = null
  description = "Resource name of the Management NIC NEG to attach host instances to."
}

variable "mgmt_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for Management NIC: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_ephemeral", "reserved_custom", "reserved"], var.mgmt_ip_address_type)
    error_message = "Management NIC IP address type must be one of: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  }
}

variable "mgmt_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IP addresses for Management NICs (required for custom modes)."
  validation {
    condition     = alltrue([for ip in var.mgmt_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in mgmt_ip_values must be valid non-empty IPv4 address strings."
  }
}

# ------------------------------------------------------------------------------
# vSAN NIC Configuration
# ------------------------------------------------------------------------------

variable "vsan_subnet_name" {
  type        = string
  description = "Name of the vSAN storage subnetwork."
}

variable "vsan_subnet_cidr" {
  type        = string
  default     = null
  description = "Optional CIDR block of the vSAN subnetwork for IP validation."
}

variable "vsan_vlan_id" {
  type        = number
  default     = 3
  description = "VLAN ID tag assigned to the vSAN network interface (allowed: 2–255)."
  validation {
    condition     = var.vsan_vlan_id >= 2 && var.vsan_vlan_id <= 255
    error_message = "VLAN ID must be between 2 and 255."
  }
}

variable "vsan_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for vSAN NIC: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_ephemeral", "reserved_custom", "reserved"], var.vsan_ip_address_type)
    error_message = "vSAN IP address type must be one of: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  }
}

variable "vsan_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IP addresses for vSAN NICs (required for custom modes)."
  validation {
    condition     = alltrue([for ip in var.vsan_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in vsan_ip_values must be valid non-empty IPv4 address strings."
  }
}

# ------------------------------------------------------------------------------
# vMotion NIC Configuration
# ------------------------------------------------------------------------------

variable "vmotion_subnet_name" {
  type        = string
  description = "Name of the vMotion migration subnetwork."
}

variable "vmotion_subnet_cidr" {
  type        = string
  default     = null
  description = "Optional CIDR block of the vMotion subnetwork for IP validation."
}

variable "vmotion_vlan_id" {
  type        = number
  default     = 2
  description = "VLAN ID tag assigned to the vMotion network interface (allowed: 2–255)."
  validation {
    condition     = var.vmotion_vlan_id >= 2 && var.vmotion_vlan_id <= 255
    error_message = "VLAN ID must be between 2 and 255."
  }
}

variable "vmotion_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for vMotion NIC: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_ephemeral", "reserved_custom", "reserved"], var.vmotion_ip_address_type)
    error_message = "vMotion IP address type must be one of: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  }
}

variable "vmotion_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IP addresses for vMotion NICs (required for custom modes)."
  validation {
    condition     = alltrue([for ip in var.vmotion_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in vmotion_ip_values must be valid non-empty IPv4 address strings."
  }
}

# ------------------------------------------------------------------------------
# NSX TEP NIC Configuration
# ------------------------------------------------------------------------------

variable "nsx_tep_subnet_name" {
  type        = string
  description = "Name of the NSX TEP encapsulation subnetwork."
}

variable "nsx_tep_subnet_cidr" {
  type        = string
  default     = null
  description = "Optional CIDR block of the NSX TEP subnetwork for IP validation."
}

variable "nsx_tep_vlan_id" {
  type        = number
  default     = 4
  description = "VLAN ID tag assigned to the NSX TEP network interface (allowed: 2–255)."
  validation {
    condition     = var.nsx_tep_vlan_id >= 2 && var.nsx_tep_vlan_id <= 255
    error_message = "VLAN ID must be between 2 and 255."
  }
}

variable "nsx_tep_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for NSX TEP NIC: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_ephemeral", "reserved_custom", "reserved"], var.nsx_tep_ip_address_type)
    error_message = "NSX TEP IP address type must be one of: ephemeral_automatic, ephemeral_custom, reserved_ephemeral, reserved_custom."
  }
}

variable "nsx_tep_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IP addresses for NSX TEP NICs (required for custom modes)."
  validation {
    condition     = alltrue([for ip in var.nsx_tep_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in nsx_tep_ip_values must be valid non-empty IPv4 address strings."
  }
}

variable "nsx_neg_name" {
  type        = string
  default     = null
  description = "Resource name of the NSX TEP NIC NEG to attach host instances to."
}

# ------------------------------------------------------------------------------
# Dynamic NIC Configuration
# ------------------------------------------------------------------------------

variable "additional_dynamic_nics" {
  type = list(object({
    name            = string
    subnet_name     = string
    vlan_id         = number
    ip_address_type = optional(string, "ephemeral_automatic")
    ip_values       = optional(list(string), [])
  }))
  default     = []
  description = "List of additional dynamic NIC configurations."
  validation {
    condition = alltrue([
      for nic in var.additional_dynamic_nics :
      nic.vlan_id >= 2 && nic.vlan_id <= 255 &&
      contains(["ephemeral_automatic", "ephemeral_custom", "reserved_ephemeral", "reserved_custom", "reserved"], nic.ip_address_type) &&
      alltrue([for ip in nic.ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    ])
    error_message = "Each dynamic NIC must have a valid vlan_id (2-255), supported ip_address_type, and all elements in ip_values must be valid non-empty IPv4 address strings."
  }
}

variable "additional_dynamic_subnets" {
  type = list(object({
    subnet_name = string
    subnet_cidr = optional(string)
  }))
  default     = []
  description = "List of customer-defined dynamic L2 subnets."
}

# ------------------------------------------------------------------------------
# Cloud DNS Record Configuration for ESXi Hosts
# ------------------------------------------------------------------------------

variable "create_dns_records" {
  type        = bool
  default     = true
  description = "Whether to create Cloud DNS forward (A) and reverse (PTR) records for ESXi hosts."
}

variable "forward_zone_name" {
  type        = string
  default     = null
  description = "Forward Cloud DNS managed zone name. When provided and create_dns_records is true, forward A records are created for all ESXi hosts."
}

variable "reverse_zone_name" {
  type        = string
  default     = null
  description = "Reverse Cloud DNS managed zone name. When provided and create_dns_records is true, reverse PTR records are created for all ESXi hosts."
}

variable "reverse_domain_name" {
  type        = string
  default     = null
  description = "Reverse lookup domain name (in-addr.arpa.) for reverse PTR record calculation (required when create_dns_records is true)."
  validation {
    condition     = var.reverse_domain_name == null || can(regex("in-addr\\.arpa", var.reverse_domain_name))
    error_message = "reverse_domain_name must contain 'in-addr.arpa' (e.g. '10.in-addr.arpa.' or '0.200.10.in-addr.arpa.')."
  }
}

variable "dns_ttl" {
  type        = number
  default     = 300
  description = "Time-to-live (TTL) in seconds for host DNS record sets."
}
