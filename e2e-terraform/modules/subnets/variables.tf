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
  description = "GCP Project ID for subnets and NEGs."
}

variable "region" {
  type        = string
  description = "Target GCP Region for subnets."
}

variable "zone" {
  type        = string
  description = "Target GCP Zone for zonal NEGs."
}

variable "resource_name_prefix" {
  type        = string
  default     = "my-vcf"
  description = "Global prefix prepended to all generated resource names."
}

variable "vpc_network" {
  type        = string
  description = "VPC Network name or self-link to which the subnets belong."
}

variable "create_subnets_and_negs" {
  type        = bool
  default     = false
  description = "Single toggle determining whether Terraform creates new subnets and NEGs (true) or validates/references existing ones (false). If false, input subnets and NEGs are expected to exist in GCP."
}

# ------------------------------------------------------------------------------
# Management Subnetwork & NEG
# ------------------------------------------------------------------------------

variable "mgmt_subnet_name" {
  type        = string
  default     = null
  description = "Name of the Management subnetwork. Expected to exist in GCP if create_subnets_and_negs is false."
}

variable "mgmt_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for Management subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.mgmt_subnet_cidr == null || can(cidrnetmask(var.mgmt_subnet_cidr))
    error_message = "mgmt_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.1.0/24)."
  }
}

variable "mgmt_neg_name" {
  type        = string
  default     = null
  description = "Resource name of the Management NIC NEG. Created if create_subnets_and_negs is true. Expected to exist in GCP if create_subnets_and_negs is false."
}

# ------------------------------------------------------------------------------
# vSAN Storage Subnetwork
# ------------------------------------------------------------------------------

variable "vsan_subnet_name" {
  type        = string
  default     = null
  description = "Name of the vSAN storage subnetwork. Expected to exist in GCP if create_subnets_and_negs is false."
}

variable "vsan_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for vSAN storage subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.vsan_subnet_cidr == null || can(cidrnetmask(var.vsan_subnet_cidr))
    error_message = "vsan_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.2.0/24)."
  }
}

# ------------------------------------------------------------------------------
# vMotion Migration Subnetwork
# ------------------------------------------------------------------------------

variable "vmotion_subnet_name" {
  type        = string
  default     = null
  description = "Name of the vMotion migration subnetwork. Expected to exist in GCP if create_subnets_and_negs is false."
}

variable "vmotion_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for vMotion migration subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.vmotion_subnet_cidr == null || can(cidrnetmask(var.vmotion_subnet_cidr))
    error_message = "vmotion_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.3.0/24)."
  }
}

# ------------------------------------------------------------------------------
# NSX TEP Overlay Subnetwork & NEG
# ------------------------------------------------------------------------------

variable "nsx_tep_subnet_name" {
  type        = string
  default     = null
  description = "Name of the NSX TEP encapsulation subnetwork. Expected to exist in GCP if create_subnets_and_negs is false."
}

variable "nsx_tep_subnet_cidr" {
  type        = string
  default     = null
  description = "IPv4 CIDR range for NSX TEP subnetwork (required if create_subnets_and_negs = true)."
  validation {
    condition     = var.nsx_tep_subnet_cidr == null || can(cidrnetmask(var.nsx_tep_subnet_cidr))
    error_message = "nsx_tep_subnet_cidr must be a valid IPv4 CIDR string (e.g. 10.0.4.0/24)."
  }
}

variable "nsx_neg_name" {
  type        = string
  default     = null
  description = "Resource name of the NSX TEP NIC NEG. Created if create_subnets_and_negs is true. Expected to exist in GCP if create_subnets_and_negs is false."
}

# ------------------------------------------------------------------------------
# Dynamic VLAN Subnetworks
# ------------------------------------------------------------------------------

variable "additional_dynamic_subnets" {
  type = list(object({
    subnet_name = string
    subnet_cidr = optional(string, null)
  }))
  default     = []
  description = "List of additional dynamic L2 subnets to create or reference. Expected to exist in GCP if create_subnets_and_negs is false."
  validation {
    condition = alltrue([
      for s in var.additional_dynamic_subnets : (
        s.subnet_name != null && s.subnet_name != "" &&
        (s.subnet_cidr == null || can(cidrnetmask(s.subnet_cidr)))
      )
    ])
    error_message = "Dynamic subnets must have a non-empty subnet_name and a valid subnet_cidr if provided."
  }
}
