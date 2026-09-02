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
# 1. Project & Geographic Scope
# ==============================================================================

variable "project_id" {
  type        = string
  description = "Target GCP Project ID."
}

variable "region" {
  type        = string
  description = "Target GCP Region for infrastructure provisioning (e.g. us-east4)."
}

variable "zone" {
  type        = string
  description = "Target GCP Zone for bare-metal ESXi host deployment (e.g. us-east4-b)."
}

variable "resource_name_prefix" {
  type        = string
  default     = "myvcf"
  description = "Global prefix prepended to all generated GCP resource names."
}

variable "deployment_mode" {
  type        = string
  default     = "cluster_creation"
  description = "Execution deployment mode: 'cluster_creation' (default, attaches instances to NEGs via Terraform), 'node_addition' (adds nodes and generates NEG attachment commands), or 'appliance_addition' (adds appliances)."

  validation {
    condition     = contains(["cluster_creation", "node_addition", "appliance_addition"], var.deployment_mode)
    error_message = "deployment_mode must be one of: 'cluster_creation', 'node_addition', 'appliance_addition'."
  }
}

# ==============================================================================
# 2. VPC Module Configuration (modules/vpc)
# ==============================================================================

variable "vpc_network" {
  type        = string
  default     = null
  description = "VPC Network name (created if create_vpc = true, else referenced). Expected to exist in GCP if create_vpc is false. Defaults to '<resource_name_prefix>-vpc' if null."
}

variable "create_vpc" {
  type        = bool
  default     = false
  description = "Flag determining whether Terraform creates a new VPC network (true) or references an existing one (false). If false, vpc_network is expected to exist in GCP and have an MTU of 8896 (default: false)."
}

variable "routing_mode" {
  type        = string
  default     = "GLOBAL"
  description = "Dynamic routing mode for the VPC network ('REGIONAL' or 'GLOBAL')."
  validation {
    condition     = contains(["REGIONAL", "GLOBAL"], var.routing_mode)
    error_message = "routing_mode must be either 'REGIONAL' or 'GLOBAL'."
  }
}

variable "create_firewalls" {
  type        = bool
  default     = true
  description = "Whether to provision the VPC allow-all ingress security firewall rule."
}

# 2.1 Cloud DNS Managed Zones, Records, GCP Subnet & Inbound Policy Creation
variable "setup_cloud_dns" {
  type        = bool
  default     = true
  description = "Master switch determining whether to set up Cloud DNS forward (A) and reverse (PTR) records, managed zones, and inbound DNS resolution policy for bare-metal ESXi hosts and VCF/NSX appliances."
}

variable "create_gcp_subnet" {
  type        = bool
  default     = true
  description = "Whether to create a dedicated standard GCP subnetwork (without resolve_subnet_mask) for Cloud DNS inbound resolver IP reservation and Offline Depot PSC endpoint (true) or reference an existing subnetwork (false)."
}

variable "gcp_subnet_name" {
  type        = string
  default     = null
  description = "Resource name of the GCP subnetwork for DNS resolution and offline depot (created if create_gcp_subnet = true, else referenced). Defaults to '<resource_name_prefix>-gcp-subnet' if null."
}

variable "gcp_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for the GCP subnetwork (e.g. '10.0.100.0/29')."
  validation {
    condition     = var.gcp_subnet_cidr == null || can(cidrhost(var.gcp_subnet_cidr, 0))
    error_message = "gcp_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.100.0/29)."
  }
}

variable "create_dns_zones" {
  type        = bool
  default     = true
  description = "Whether to create the forward and reverse Cloud DNS managed zones in GCP (true) or reference existing zones (false)."
}

variable "forward_zone_name" {
  type        = string
  default     = null
  description = "Resource name of the forward managed DNS zone (created if create_dns_zones = true). If create_dns_zones is false and setup_cloud_dns is true, this existing zone name must be provided."
}

variable "reverse_zone_name" {
  type        = string
  default     = null
  description = "Resource name of the reverse managed DNS zone (created if create_dns_zones = true). If create_dns_zones is false and setup_cloud_dns is true, this existing zone name must be provided."
}

variable "reverse_domain_name" {
  type        = string
  default     = null
  description = "Reverse lookup domain name (in-addr.arpa.) for the reverse managed DNS zone and PTR records. Required when create_dns_zones is true."
  validation {
    condition     = var.reverse_domain_name == null || can(regex("in-addr\\.arpa", var.reverse_domain_name))
    error_message = "reverse_domain_name must contain 'in-addr.arpa' (e.g. '10.in-addr.arpa.' or '0.200.10.in-addr.arpa.')."
  }
}

variable "dns_ttl" {
  type        = number
  default     = 300
  description = "Time-to-live (TTL) in seconds for DNS record sets."
}

variable "dns_policy_name" {
  type        = string
  default     = null
  description = "Resource name of the Cloud DNS inbound forwarding policy to create on the VPC network. If omitted or null, no DNS policy is created by Terraform."
}

# ==============================================================================
# 3. Subnets & NEGs Module Configuration (modules/subnets)
# ==============================================================================

variable "create_subnets_and_negs" {
  type        = bool
  default     = true
  description = "Single unified boolean determining whether Terraform creates all L2 subnets and zonal NEGs (true) or references existing ones (false). If false, input subnets and NEGs are expected to exist in GCP."
}

# 3.1 Management Network Subnet & NEG
variable "mgmt_subnet_name" {
  type        = string
  default     = null
  description = "Name of the Management subnetwork. Expected to exist in GCP if create_subnets_and_negs is false. Defaults to '<resource_name_prefix>-mgmt-subnet' if null."
}

variable "mgmt_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for the Management subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.mgmt_subnet_cidr == null || can(cidrnetmask(var.mgmt_subnet_cidr))
    error_message = "mgmt_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.0.0/24)."
  }
}

variable "mgmt_neg_name" {
  type        = string
  default     = null
  description = "Resource name of the Management NIC Network Endpoint Group (NEG). Created if create_subnets_and_negs is true (defaults to '<resource_name_prefix>-mgmt-neg' if null). Expected to exist in GCP if create_subnets_and_negs is false."
}

# 3.2 vSAN Storage Subnet
variable "vsan_subnet_name" {
  type        = string
  default     = null
  description = "Name of the vSAN storage subnetwork. Expected to exist in GCP if create_subnets_and_negs is false. Defaults to '<resource_name_prefix>-vsan-subnet' if null."
}

variable "vsan_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for the vSAN storage subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.vsan_subnet_cidr == null || can(cidrnetmask(var.vsan_subnet_cidr))
    error_message = "vsan_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.1.0/24)."
  }
}

# 3.3 vMotion Migration Subnet
variable "vmotion_subnet_name" {
  type        = string
  default     = null
  description = "Name of the vMotion migration subnetwork. Expected to exist in GCP if create_subnets_and_negs is false. Defaults to '<resource_name_prefix>-vmotion-subnet' if null."
}

variable "vmotion_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for the vMotion migration subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.vmotion_subnet_cidr == null || can(cidrnetmask(var.vmotion_subnet_cidr))
    error_message = "vmotion_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.2.0/24)."
  }
}

# 3.4 NSX TEP Overlay Subnet & NEG
variable "nsx_tep_subnet_name" {
  type        = string
  default     = null
  description = "Name of the NSX TEP encapsulation subnetwork. Expected to exist in GCP if create_subnets_and_negs is false. Defaults to '<resource_name_prefix>-nsx-tep-subnet' if null."
}

variable "nsx_tep_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for the NSX TEP encapsulation subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.nsx_tep_subnet_cidr == null || can(cidrnetmask(var.nsx_tep_subnet_cidr))
    error_message = "nsx_tep_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.3.0/24)."
  }
}

variable "nsx_neg_name" {
  type        = string
  default     = null
  description = "Resource name of the NSX TEP NIC Network Endpoint Group (NEG). Created if create_subnets_and_negs is true (defaults to '<resource_name_prefix>-nsx-neg' if null). Expected to exist in GCP if create_subnets_and_negs is false."
}

# 3.5 Additional Dynamic Subnets
variable "additional_dynamic_subnets" {
  type = list(object({
    subnet_name = string
    subnet_cidr = optional(string, null)
  }))
  default     = []
  description = "List of customer-defined dynamic L2 subnets to create or reference. Expected to exist in GCP if create_subnets_and_negs is false."
  validation {
    condition = alltrue([
      for s in var.additional_dynamic_subnets :
      s.subnet_name != null && s.subnet_name != "" &&
      (s.subnet_cidr == null || can(cidrnetmask(s.subnet_cidr)))
    ])
    error_message = "Each dynamic subnet must have a valid non-empty subnet_name and a valid subnet_cidr if provided."
  }
}

# ==============================================================================
# 4. Bare-Metal ESXi Compute Hosts Module Configuration (modules/hosts)
# ==============================================================================

variable "number_of_nodes" {
  type        = number
  default     = 4
  description = "Total number of bare-metal ESXi compute nodes provisioned (range 1 to 32)."
  validation {
    condition     = var.number_of_nodes >= 1 && var.number_of_nodes <= 32
    error_message = "number_of_nodes must be an integer between 1 and 32."
  }
}

variable "machine_type" {
  type        = string
  default     = "z3-highmem-192-highlssd-metal"
  description = "Bare-metal machine type (e.g. z3-highmem-192-highlssd-metal, z3-highmem-192-metal)."
  validation {
    condition     = contains(["z3-highmem-192-highlssd-metal", "z3-highmem-192-metal"], var.machine_type)
    error_message = "machine_type must be either 'z3-highmem-192-highlssd-metal' or 'z3-highmem-192-metal'."
  }
}

variable "esxi_image" {
  type        = string
  description = "Full resource URI of the ESXi OS boot disk image for bare-metal host instances (e.g. 'projects/<project>/global/images/<image-name>'). Must be a valid full ESXi image resource URI."
  validation {
    condition     = can(regex("^(?:https://www\\.googleapis\\.com/compute/v1/)?projects/[^/]+/global/images/.+$", var.esxi_image))
    error_message = "esxi_image must be a valid full ESXi image resource URI (e.g. 'projects/<project>/global/images/vmware-esxi-9-1-0-dm-v20260513' or 'projects/<project>/global/images/esxi-8-0-2-12345678')."
  }
}

variable "node_names" {
  type        = list(string)
  default     = null
  description = "Explicit list of GCE node instance names. If null, auto-generated as '<resource_name_prefix>-node-1', etc."
}

variable "domain_name" {
  type        = string
  description = "Domain name (e.g. 'vcf.test.gve.') appended to node_names to form ESXi host FQDNs and used as forward DNS zone domain."
  validation {
    condition     = length(var.domain_name) > 0
    error_message = "domain_name must not be empty."
  }
}

variable "deletion_protection" {
  type        = bool
  default     = true
  description = "Protects instances from accidental deletion via GCE API / Terraform."
}

variable "create_placement_policy" {
  type        = bool
  default     = true
  description = "Flag to create a new placement policy (true) or reference an existing one (false). If false, the input placement policy is expected to exist in GCP."
}

variable "placement_policy_name" {
  type        = string
  default     = null
  description = "Resource name of the Compute placement policy. Created if create_placement_policy is true (defaults to '<resource_name_prefix>-placement-policy' if null). Expected to exist in GCP if create_placement_policy is false."
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
    condition     = var.availability_domains == null ? true : alltrue([for ad in var.availability_domains : ad >= 1])
    error_message = "All elements in availability_domains must be greater than or equal to 1."
  }
}

# 4.1 Management NIC Configuration
variable "mgmt_nic_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for Management NIC: 'ephemeral_automatic', 'ephemeral_custom', 'reserved_automatic', 'reserved_custom'."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.mgmt_nic_ip_address_type)
    error_message = "mgmt_nic_ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "mgmt_nic_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IPv4 address strings for Management NICs in mgmt_subnet_cidr (e.g. ['10.200.0.3', '10.200.0.4']). Required when mgmt_nic_ip_address_type is custom ('ephemeral_custom' or 'reserved_custom') and must contain number_of_nodes entries. Leave empty ([]) for automatic modes ('ephemeral_automatic' or 'reserved_automatic')."
  validation {
    condition     = alltrue([for ip in var.mgmt_nic_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in mgmt_nic_ip_values must be valid non-empty IPv4 address strings."
  }
}

# 4.2 vSAN NIC Configuration
variable "vsan_vlan_id" {
  type        = number
  default     = 3
  description = "VLAN ID tag assigned to the vSAN network interface (allowed range: 2 to 255)."
  validation {
    condition     = var.vsan_vlan_id >= 2 && var.vsan_vlan_id <= 255
    error_message = "vsan_vlan_id must be between 2 and 255."
  }
}

variable "vsan_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for vSAN NIC: 'ephemeral_automatic', 'ephemeral_custom', 'reserved_automatic', 'reserved_custom'."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.vsan_ip_address_type)
    error_message = "vsan_ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "vsan_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IPv4 address strings for vSAN NICs in vsan_subnet_cidr (e.g. ['10.200.1.3', '10.200.1.4']). Required when vsan_ip_address_type is custom ('ephemeral_custom' or 'reserved_custom') and must contain number_of_nodes entries. Leave empty ([]) for automatic modes ('ephemeral_automatic' or 'reserved_automatic')."
  validation {
    condition     = alltrue([for ip in var.vsan_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in vsan_ip_values must be valid non-empty IPv4 address strings."
  }
}

# 4.3 vMotion NIC Configuration
variable "vmotion_vlan_id" {
  type        = number
  default     = 2
  description = "VLAN ID tag assigned to the vMotion network interface (allowed range: 2 to 255)."
  validation {
    condition     = var.vmotion_vlan_id >= 2 && var.vmotion_vlan_id <= 255
    error_message = "vmotion_vlan_id must be between 2 and 255."
  }
}

variable "vmotion_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for vMotion NIC: 'ephemeral_automatic', 'ephemeral_custom', 'reserved_automatic', 'reserved_custom'."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.vmotion_ip_address_type)
    error_message = "vmotion_ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "vmotion_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IPv4 address strings for vMotion NICs in vmotion_subnet_cidr (e.g. ['10.200.2.3', '10.200.2.4']). Required when vmotion_ip_address_type is custom ('ephemeral_custom' or 'reserved_custom') and must contain number_of_nodes entries. Leave empty ([]) for automatic modes ('ephemeral_automatic' or 'reserved_automatic')."
  validation {
    condition     = alltrue([for ip in var.vmotion_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in vmotion_ip_values must be valid non-empty IPv4 address strings."
  }
}

# 4.4 NSX TEP NIC Configuration
variable "nsx_tep_vlan_id" {
  type        = number
  default     = 4
  description = "VLAN ID tag assigned to the NSX TEP network interface (allowed range: 2 to 255)."
  validation {
    condition     = var.nsx_tep_vlan_id >= 2 && var.nsx_tep_vlan_id <= 255
    error_message = "nsx_tep_vlan_id must be between 2 and 255."
  }
}

variable "nsx_tep_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for NSX TEP NIC: 'ephemeral_automatic', 'ephemeral_custom', 'reserved_automatic', 'reserved_custom'."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.nsx_tep_ip_address_type)
    error_message = "nsx_tep_ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "nsx_tep_ip_values" {
  type        = list(string)
  default     = []
  description = "List of explicit IPv4 address strings for NSX TEP NICs in nsx_tep_subnet_cidr (e.g. ['10.200.3.3', '10.200.3.4']). Required when nsx_tep_ip_address_type is custom ('ephemeral_custom' or 'reserved_custom') and must contain number_of_nodes entries. Leave empty ([]) for automatic modes ('ephemeral_automatic' or 'reserved_automatic')."
  validation {
    condition     = alltrue([for ip in var.nsx_tep_ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    error_message = "All elements in nsx_tep_ip_values must be valid non-empty IPv4 address strings."
  }
}

# 4.5 Additional Dynamic NICs
variable "additional_dynamic_nics" {
  type = list(object({
    name            = string
    subnet_name     = string
    vlan_id         = number
    ip_address_type = optional(string, "ephemeral_automatic")
    ip_values       = optional(list(string), [])
  }))
  default     = []
  description = "List of customer-defined dynamic VLAN interfaces to attach to bare-metal compute instances. ip_values accepts a list of explicit IPv4 address strings (required when ip_address_type is 'ephemeral_custom' or 'reserved_custom', matching number_of_nodes entries; empty list [] for automatic modes)."
  validation {
    condition = alltrue([
      for nic in var.additional_dynamic_nics :
      nic.vlan_id >= 2 && nic.vlan_id <= 255 &&
      contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], nic.ip_address_type) &&
      alltrue([for ip in nic.ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))])
    ])
    error_message = "Each dynamic NIC must have a valid vlan_id (2-255), supported ip_address_type, and all elements in ip_values must be valid non-empty IPv4 address strings."
  }
}

# ==============================================================================
# 5. Internal Load Balancers & Appliances Module Configuration (modules/appliances)
# ==============================================================================

variable "mgmt_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for Management ILB Forwarding Rules: 'ephemeral_automatic', 'ephemeral_custom', 'reserved_automatic', 'reserved_custom'."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.mgmt_ip_address_type)
    error_message = "mgmt_ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "mgmt_ip_values" {
  type        = map(string)
  default     = {}
  description = "Map of management appliance names to IP values in mgmt_subnet_cidr. Supported input value formats per entry: 1) Single explicit IPv4 address (e.g. '10.200.0.9'), 2) IPv4 address range string 'start_ip-end_ip' (e.g. '10.200.0.50-10.200.0.80') which expands to individual sequential entries (<name>-1, <name>-2, ...), 3) Positive integer count string (e.g. '6') which allocates N automatic IPs (<name>-1, ..., <name>-N) for automatic modes, or 4) Empty string '' for automatic single IP allocation."
}

variable "nsx_ip_address_type" {
  type        = string
  default     = "ephemeral_automatic"
  description = "IP mode for NSX Datapath ILB Forwarding Rules: 'ephemeral_automatic', 'ephemeral_custom', 'reserved_automatic', 'reserved_custom'."
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.nsx_ip_address_type)
    error_message = "nsx_ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "nsx_ip_values" {
  type        = map(string)
  default     = {}
  description = "Map of NSX datapath/edge appliance names to IP values in nsx_tep_subnet_cidr. Supported input value formats per entry: 1) Single explicit IPv4 address (e.g. '10.200.3.10'), 2) IPv4 address range string 'start_ip-end_ip' (e.g. '10.200.3.50-10.200.3.60') which expands to individual sequential entries (<name>-1, <name>-2, ...), 3) Positive integer count string (e.g. '2') which allocates N automatic IPs (<name>-1, ..., <name>-N) for automatic modes, or 4) Empty string '' for automatic single IP allocation."
}

