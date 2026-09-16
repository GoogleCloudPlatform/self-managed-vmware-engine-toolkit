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
  description = "GCP Project ID for VPC resources (required)."
  validation {
    condition     = var.project_id != null && var.project_id != ""
    error_message = "project_id is required and must be a non-empty string."
  }
}

variable "region" {
  type        = string
  description = "GCP Region for regional VPC resources and DNS policy."
}

variable "resource_name_prefix" {
  type        = string
  default     = "my-vcf"
  description = "Global prefix prepended to all generated resource names."
}

variable "vpc_network" {
  type        = string
  description = "VPC Network name (created if create_vpc = true, else referenced). Expected to exist in GCP if create_vpc is false."
}

variable "create_vpc" {
  type        = bool
  default     = false
  description = "Whether to create the VPC network (default: false). If false, vpc_network is expected to exist in GCP and have an MTU of 8896."
}

variable "routing_mode" {
  type        = string
  default     = "GLOBAL"
  description = "Routing mode for VPC network (REGIONAL or GLOBAL)."
  validation {
    condition     = contains(["REGIONAL", "GLOBAL"], var.routing_mode)
    error_message = "Routing mode must be either 'REGIONAL' or 'GLOBAL'."
  }
}

# ------------------------------------------------------------------------------
# Security Firewall Rule
# ------------------------------------------------------------------------------

variable "create_firewalls" {
  type        = bool
  default     = true
  description = "Whether to provision a VPC security firewall rule which allows all ingress (<resource_name_prefix>-firewall-rule)."
}

# ------------------------------------------------------------------------------
# Cloud DNS Managed Zones, Records, GCP Subnet & Inbound Policy Creation
# ------------------------------------------------------------------------------

variable "setup_cloud_dns" {
  type        = bool
  default     = true
  description = "Whether to create Cloud DNS forward (A) and reverse (PTR) records for ESXi hosts and appliances."
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
}

variable "create_dns_zones" {
  type        = bool
  default     = true
  description = "Whether to create the forward and reverse Cloud DNS managed zones (true) or reference existing zones/not have DNS zones at all (false)."
}

variable "domain_name" {
  type        = string
  default     = null
  description = "Forward DNS domain name for the forward managed zone."
}

variable "reverse_domain_name" {
  type        = string
  default     = null
  description = "Reverse lookup domain name (in-addr.arpa.) for the reverse managed DNS zone. Required when create_dns_zones is true."
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

variable "dns_policy_name" {
  type        = string
  default     = null
  description = "Resource name of the Cloud DNS inbound forwarding policy to create on the VPC network. Created only when setup_cloud_dns is true. If omitted or null, no DNS policy is created by Terraform."
}
