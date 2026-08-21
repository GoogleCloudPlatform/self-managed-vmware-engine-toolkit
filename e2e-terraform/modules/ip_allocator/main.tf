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

terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

locals {
  is_reserved_custom    = var.ip_address_type == "reserved_custom"
  is_reserved_ephemeral = var.ip_address_type == "reserved_ephemeral" || var.ip_address_type == "reserved"
  is_reserved           = local.is_reserved_custom || local.is_reserved_ephemeral
  is_ephemeral_custom   = var.ip_address_type == "ephemeral_custom"
  count                 = length(var.entities)

  # Extract custom IP value for each entity index whether ip_values is passed as list or map or empty
  ip_addresses = [
    for i, name in var.entities : (
      can(var.ip_values[i]) ? var.ip_values[i] : (
        can(lookup(var.ip_values, name)) ? lookup(var.ip_values, name, null) : (
          can(lookup(var.ip_values, replace(name, "-", ""))) ? lookup(var.ip_values, replace(name, "-", ""), null) : null
        )
      )
    )
  ]
}

# ==============================================================================
# 1. Static Internal IP Reservation (When mode is 'reserved_custom' or 'reserved_ephemeral')
# ==============================================================================

resource "google_compute_address" "reserved_ip" {
  count   = local.is_reserved ? local.count : 0
  project = var.project_id
  region  = var.region

  # Dynamic resource name generation mechanism using format(template, prefix, entity).
  # Examples:
  # 1. Node instance interface IP reservation:
  #    - address_name_template = "%s-mgmt-ip-%s"
  #    - resource_name_prefix  = "vcf-mgmt"
  #    - var.entities          = ["1", "2", "3", "4"]
  #    => Evaluates to: "vcf-mgmt-mgmt-ip-1", "vcf-mgmt-mgmt-ip-2", etc.
  # 2. Control plane appliance IP reservation:
  #    - address_name_template = "%s-%s-ip"
  #    - resource_name_prefix  = "vcf-mgmt"
  #    - var.entities          = ["sddc-manager", "vcenter"]
  #    => Evaluates to: "vcf-mgmt-sddc-manager-ip", "vcf-mgmt-vcenter-ip"
  name = format(var.address_name_template, var.resource_name_prefix, var.entities[count.index])

  subnetwork   = var.subnetwork
  address_type = var.address_type
  purpose      = var.purpose

  address = local.ip_addresses[count.index]
}

# ==============================================================================
# 2. Plan-Phase Validation Checks
# ==============================================================================

check "validate_ip_addresses_count_and_format" {
  assert {
    condition = (
      (!local.is_ephemeral_custom && !local.is_reserved_custom) || (
        (can(keys(var.ip_values)) ? length(keys(var.ip_values)) == local.count : length(var.ip_values) == local.count) &&
        length(local.ip_addresses) == local.count &&
        alltrue([
          for ip in local.ip_addresses :
          ip != null && ip != "" && can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))
        ])
      )
    )
    error_message = "When using custom IP allocation mode ('ephemeral_custom' or 'reserved_custom'), the length of ip_values must match the length of entities (${local.count}), and all entries must be non-null and non-empty valid IPv4 addresses."
  }
}

check "validate_ip_values_length_matches_entities" {
  assert {
    condition = (
      can(keys(var.ip_values)) ||
      length(var.ip_values) == 0 ||
      length(var.ip_values) == local.count
    )
    error_message = "When ip_values is supplied as a list, its length (${can(length(var.ip_values)) ? length(var.ip_values) : 0}) must match the length of entities (${local.count})."
  }
}
