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
  description = "GCP Project ID for appliance resources."
}

variable "region" {
  type        = string
  description = "Target GCP Region for regional backend services and forwarding rules."
}

variable "zone" {
  type        = string
  description = "Target GCP Zone for zonal NEG associations."
}

variable "resource_name_prefix" {
  type        = string
  default     = "myvcf"
  description = "Global prefix prepended to all generated resource names."
}

variable "vpc_network" {
  type        = string
  description = "VPC Network name or self-link for backend services."
}

variable "mgmt_subnet_name" {
  type        = string
  description = "Management subnetwork name or self-link for management forwarding rules and IP reservations."
}

variable "nsx_tep_subnet_name" {
  type        = string
  description = "NSX TEP subnetwork name or self-link for NSX datapath forwarding rules and IP reservations."
}

variable "mgmt_neg_self_link" {
  type        = string
  description = "Self-link of the Management NIC NEG to attach to management backend services."
}

variable "nsx_neg_self_link" {
  type        = string
  default     = null
  description = "Self-link of the NSX TEP NIC NEG to attach to NSX backend services."
}

variable "leader_instance" {
  type        = string
  description = "Name of the bare-metal leader instance (typically Node 1) for GARP_RA HA policy."
}

variable "mgmt_subnet_cidr" {
  type        = string
  description = "CIDR range of the Management subnet for in-subnet IP verification."
  validation {
    condition     = can(cidrhost(var.mgmt_subnet_cidr, 0))
    error_message = "mgmt_subnet_cidr must be a valid IPv4 CIDR string (e.g., '10.200.0.0/24')."
  }
}

variable "nsx_tep_subnet_cidr" {
  type        = string
  description = "CIDR range of the NSX TEP subnet for in-subnet IP verification."
  validation {
    condition     = can(cidrhost(var.nsx_tep_subnet_cidr, 0))
    error_message = "nsx_tep_subnet_cidr must be a valid IPv4 CIDR string (e.g., '10.200.3.0/24')."
  }
}

# ------------------------------------------------------------------------------
# Management Appliances Configuration
# ------------------------------------------------------------------------------

variable "mgmt_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for Management ILB Forwarding Rules (ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom)."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.mgmt_ip_address_type)
    error_message = "Management IP address type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "mgmt_ip_values" {
  type        = map(string)
  default     = {}
  description = "Map of management appliance names to IP values in mgmt_subnet_cidr. Supported input value formats per entry: 1) Single explicit IPv4 address (e.g. '10.200.0.9'), 2) IPv4 address range string 'start_ip-end_ip' (e.g. '10.200.0.50-10.200.0.80') which expands into sequential entries (<name>-1, <name>-2, ...), 3) Positive integer count string (e.g. '6') which allocates N automatic IPs (<name>-1, ..., <name>-N) for automatic modes, or 4) Empty string '' for single automatic IP allocation."
  validation {
    condition = alltrue([
      for k, v in var.mgmt_ip_values : v == "" || can(regex("^[1-9][0-9]*$", v)) || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", v)) || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}-(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", v))
    ])
    error_message = "All values in mgmt_ip_values must be empty strings, positive integer counts (for automatic modes), valid IPv4 address strings, or IP range strings."
  }
}

# ------------------------------------------------------------------------------
# NSX Datapath Appliances Configuration
# ------------------------------------------------------------------------------

variable "nsx_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for NSX Datapath ILB Forwarding Rules (ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom)."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.nsx_ip_address_type)
    error_message = "NSX IP address type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "nsx_ip_values" {
  type        = map(string)
  default     = {}
  description = "Map of NSX datapath appliance names to IP values in nsx_tep_subnet_cidr. Supported input value formats per entry: 1) Single explicit IPv4 address (e.g. '10.200.3.10'), 2) IPv4 address range string 'start_ip-end_ip' (e.g. '10.200.3.50-10.200.3.60') which expands into sequential entries (<name>-1, <name>-2, ...), 3) Positive integer count string (e.g. '2') which allocates N automatic IPs (<name>-1, ..., <name>-N) for automatic modes, or 4) Empty string '' for single automatic IP allocation."
  validation {
    condition = alltrue([
      for k, v in var.nsx_ip_values : v == "" || can(regex("^[1-9][0-9]*$", v)) || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", v)) || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}-(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", v))
    ])
    error_message = "All values in nsx_ip_values must be empty strings, positive integer counts (for automatic modes), valid IPv4 address strings, or IP range strings."
  }
}

# ------------------------------------------------------------------------------
# Cloud DNS Record Configuration for Appliances
# ------------------------------------------------------------------------------

variable "setup_cloud_dns" {
  type        = bool
  default     = true
  description = "Whether to create Cloud DNS forward (A) and reverse (PTR) records for appliances."
}

variable "domain_name" {
  type        = string
  default     = null
  description = "Forward DNS domain name for appliance A records."
}

variable "reverse_domain_name" {
  type        = string
  default     = null
  description = "Reverse DNS domain name (in-addr.arpa.) for appliance PTR records."
  validation {
    condition     = var.reverse_domain_name == null || can(regex("in-addr\\.arpa", var.reverse_domain_name))
    error_message = "reverse_domain_name must contain 'in-addr.arpa' (e.g. '10.in-addr.arpa.' or '0.200.10.in-addr.arpa.')."
  }
}

variable "forward_zone_name" {
  type        = string
  default     = null
  description = "Forward Cloud DNS managed zone name. When provided and setup_cloud_dns is true, forward A records are created for all appliances."
}

variable "reverse_zone_name" {
  type        = string
  default     = null
  description = "Reverse Cloud DNS managed zone name. When provided and setup_cloud_dns is true, reverse PTR records are created for all appliances."
}

variable "dns_ttl" {
  type        = number
  default     = 300
  description = "Time-to-live (TTL) in seconds for appliance DNS record sets."
}

variable "ntp_ip" {
  type        = string
  default     = null
  description = "IP address for the NTP server forward DNS A record. If provided and setup_cloud_dns is true, an A record (ntp.<domain_name>) pointing to this IP is created."
  validation {
    condition     = var.ntp_ip == null || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", var.ntp_ip))
    error_message = "ntp_ip must be a valid IPv4 address string (e.g. '169.254.169.254') or null."
  }
}
