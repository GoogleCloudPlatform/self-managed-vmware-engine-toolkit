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
  description = "GCP Project ID for IP reservation resources (required)."
  validation {
    condition     = var.project_id != null && var.project_id != ""
    error_message = "project_id is required and must be a non-empty string."
  }
}

variable "region" {
  type        = string
  description = "GCP Region for IP reservation resources"
}

variable "subnetwork" {
  type        = string
  description = "Subnetwork name or self link to allocate IPs from"
}

variable "resource_name_prefix" {
  type        = string
  default     = "my-vcf"
  description = "Prefix for naming reserved IP address resources"
}

variable "ip_address_type" {
  type        = string
  description = "IP allocation mode: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom"
  validation {
    condition     = contains(["ephemeral_automatic", "ephemeral_custom", "reserved_automatic", "reserved_custom"], var.ip_address_type)
    error_message = "ip_address_type must be one of: ephemeral_automatic, ephemeral_custom, reserved_automatic, reserved_custom."
  }
}

variable "entities" {
  type        = list(string)
  default     = []
  description = "List of entity/node/appliance names requiring IP allocation."
  validation {
    condition     = alltrue([for e in var.entities : e != null && e != ""])
    error_message = "All elements in entities must be non-null and non-empty strings."
  }
}

variable "ip_values" {
  type        = any
  default     = []
  description = "Explicit IPv4 addresses to allocate. Supported types: 1) list(string) of valid IPv4 address strings (e.g. ['10.200.0.3', '10.200.0.4']), or 2) map(string) of entity/appliance names to valid IPv4 address strings (e.g. {'sddc-manager' = '10.200.0.9'})."
  validation {
    condition = (
      can(keys(var.ip_values)) ? alltrue([
        for k, v in var.ip_values : v != null && v != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", v))
        ]) : (
        can(length(var.ip_values)) ? alltrue([
          for ip in var.ip_values : ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))
        ]) : false
      )
    )
    error_message = "ip_values can be a list or map containing non-empty valid IPv4 address strings as elements or values."
  }
}

variable "address_name_template" {
  type        = string
  default     = "%s-%s-ip"
  description = "Format template for naming reserved address resources (format(template, prefix, entity))"
}

variable "purpose" {
  type        = string
  default     = null
  description = "The purpose of the resource (e.g., GCE_ENDPOINT, SHARED_LOADBALANCER_VIP)"
}

variable "address_type" {
  type        = string
  default     = "INTERNAL"
  description = "The type of address to reserve (INTERNAL or EXTERNAL)"
}
