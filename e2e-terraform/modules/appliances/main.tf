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
  # ----------------------------------------------------------------------------
  # 1. Precomputed Integer Bounds for IP Range Strings ("start_ip-end_ip")
  # ----------------------------------------------------------------------------
  range_entries_metadata = {
    for k, v in merge(var.mgmt_ip_values, var.nsx_ip_values) : k => {
      start_int = (
        parseint(split(".", split("-", v)[0])[0], 10) * 16777216 +
        parseint(split(".", split("-", v)[0])[1], 10) * 65536 +
        parseint(split(".", split("-", v)[0])[2], 10) * 256 +
        parseint(split(".", split("-", v)[0])[3], 10)
      )
      end_int = (
        parseint(split(".", split("-", v)[1])[0], 10) * 16777216 +
        parseint(split(".", split("-", v)[1])[1], 10) * 65536 +
        parseint(split(".", split("-", v)[1])[2], 10) * 256 +
        parseint(split(".", split("-", v)[1])[3], 10)
      )
    }
    if can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}-(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", v))
  }

  # ----------------------------------------------------------------------------
  # 2. Unified Expansion Pipeline for Management & NSX Datapath Appliances
  # ----------------------------------------------------------------------------
  expanded_appliances = {
    for group, ip_map in { mgmt = var.mgmt_ip_values, nsx = var.nsx_ip_values } : group => flatten([
      for name, val in ip_map : (
        # Case A: IPv4 Range (e.g., "10.200.0.50-10.200.0.80") -> <name>-1, <name>-2, ...
        can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}-(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", val)) ? [
          for i in range(local.range_entries_metadata[name].end_int - local.range_entries_metadata[name].start_int + 1) : {
            name = (local.range_entries_metadata[name].end_int - local.range_entries_metadata[name].start_int + 1) == 1 ? name : "${name}-${i + 1}"
            ip = format(
              "%d.%d.%d.%d",
              floor((local.range_entries_metadata[name].start_int + i) / 16777216) % 256,
              floor((local.range_entries_metadata[name].start_int + i) / 65536) % 256,
              floor((local.range_entries_metadata[name].start_int + i) / 256) % 256,
              (local.range_entries_metadata[name].start_int + i) % 256
            )
          }
          ] : (
          # Case B: Positive Integer Count (e.g., "6") -> <name>-1..6 with automatic IP allocation
          can(regex("^[1-9][0-9]*$", val)) ? [
            for i in range(parseint(val, 10)) : {
              name = parseint(val, 10) == 1 ? name : "${name}-${i + 1}"
              ip   = ""
            }
            ] : [
            # Case C: Single Static IP ("10.200.0.9") or Empty String ("") -> single entity
            {
              name = name
              ip   = val
            }
          ]
        )
      )
    ])
  }

  mgmt_expanded_entities = local.expanded_appliances["mgmt"]
  nsx_expanded_entities  = local.expanded_appliances["nsx"]

  # Dynamically derive appliance lists directly from user-supplied input maps
  mgmt_appliances      = [for item in local.mgmt_expanded_entities : item.name]
  mgmt_appliance_count = length(local.mgmt_appliances)
  mgmt_entity_ip_map = {
    for item in local.mgmt_expanded_entities : item.name => item.ip
    if item.ip != ""
  }

  nsx_appliances      = [for item in local.nsx_expanded_entities : item.name]
  nsx_appliance_count = length(local.nsx_appliances)
  nsx_entity_ip_map = {
    for item in local.nsx_expanded_entities : item.name => item.ip
    if item.ip != ""
  }

  # All configured appliance IP mappings directly from forwarding rules
  mgmt_appliance_ips = {
    for name in local.mgmt_appliances : name => google_compute_forwarding_rule.mgmt_forwarding_rules[name].ip_address
  }

  nsx_appliance_ips = {
    for name in local.nsx_appliances : name => google_compute_forwarding_rule.nsx_forwarding_rules[name].ip_address
  }

  formatted_domain_name = var.domain_name != null && var.domain_name != "" ? (
    endswith(var.domain_name, ".") ? var.domain_name : "${var.domain_name}."
  ) : null

  # DNS records are created only for the IPs mentioned in the management appliances
  appliance_dns_records = {
    for item in local.mgmt_expanded_entities : item.name => (
      item.ip != "" ? item.ip : local.mgmt_appliance_ips[item.name]
    )
    if item.ip != "" || (var.mgmt_ip_address_type != "reserved_custom" && var.mgmt_ip_address_type != "ephemeral_custom")
  }

  appliance_ptr_record_names = {
    for name, ip in local.appliance_dns_records : name => "${join(".", reverse(split(".", ip)))}.in-addr.arpa."
  }

  # CIDR validation calculations for Management subnet
  mgmt_cidr_ip   = split("/", var.mgmt_subnet_cidr)[0]
  mgmt_cidr_mask = parseint(split("/", var.mgmt_subnet_cidr)[1], 10)
  mgmt_cidr_start_int = (
    parseint(split(".", local.mgmt_cidr_ip)[0], 10) * 16777216 +
    parseint(split(".", local.mgmt_cidr_ip)[1], 10) * 65536 +
    parseint(split(".", local.mgmt_cidr_ip)[2], 10) * 256 +
    parseint(split(".", local.mgmt_cidr_ip)[3], 10)
  )
  mgmt_cidr_end_int = local.mgmt_cidr_start_int + pow(2, 32 - local.mgmt_cidr_mask)

  # CIDR validation calculations for NSX TEP subnet
  nsx_tep_cidr_ip   = split("/", var.nsx_tep_subnet_cidr)[0]
  nsx_tep_cidr_mask = parseint(split("/", var.nsx_tep_subnet_cidr)[1], 10)
  nsx_tep_cidr_start_int = (
    parseint(split(".", local.nsx_tep_cidr_ip)[0], 10) * 16777216 +
    parseint(split(".", local.nsx_tep_cidr_ip)[1], 10) * 65536 +
    parseint(split(".", local.nsx_tep_cidr_ip)[2], 10) * 256 +
    parseint(split(".", local.nsx_tep_cidr_ip)[3], 10)
  )
  nsx_tep_cidr_end_int = local.nsx_tep_cidr_start_int + pow(2, 32 - local.nsx_tep_cidr_mask)
}

# ==============================================================================
# 1. Modular IP Allocators for Forwarding Rules
# ==============================================================================

module "mgmt_ip_allocator" {
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = var.mgmt_subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-%s-ip"
  ip_address_type       = var.mgmt_ip_address_type
  entities              = local.mgmt_appliances
  ip_values             = local.mgmt_entity_ip_map
}

module "nsx_ip_allocator" {
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = var.nsx_tep_subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-%s-ip"
  ip_address_type       = var.nsx_ip_address_type
  entities              = local.nsx_appliances
  ip_values             = local.nsx_entity_ip_map
}

# ==============================================================================
# 2. Regional Backend Services & Forwarding Rules for Management Appliances
# ==============================================================================

resource "google_compute_region_backend_service" "mgmt_backends" {
  for_each                        = toset(local.mgmt_appliances)
  project                         = var.project_id
  name                            = "${var.resource_name_prefix}-${each.key}-backend"
  region                          = var.region
  protocol                        = "UNSPECIFIED"
  load_balancing_scheme           = "INTERNAL"
  network                         = var.vpc_network
  connection_draining_timeout_sec = 0

  ha_policy {
    fast_ip_move = "GARP_RA"
    leader {
      backend_group = var.mgmt_neg_self_link
      network_endpoint {
        instance = var.leader_instance
      }
    }
  }

  backend {
    group          = var.mgmt_neg_self_link
    balancing_mode = "CONNECTION"
  }
}

resource "google_compute_forwarding_rule" "mgmt_forwarding_rules" {
  for_each              = toset(local.mgmt_appliances)
  project               = var.project_id
  name                  = "${var.resource_name_prefix}-${each.key}-fr"
  region                = var.region
  load_balancing_scheme = "INTERNAL"
  backend_service       = google_compute_region_backend_service.mgmt_backends[each.key].self_link
  subnetwork            = var.mgmt_subnet_name
  network               = var.vpc_network
  ip_protocol           = "L3_DEFAULT"
  all_ports             = true
  allow_global_access   = true
  ip_address            = module.mgmt_ip_allocator.effective_ip_map[each.key]
}

# ==============================================================================
# 3. Regional Backend Services & Forwarding Rules for NSX Datapath Appliances
# ==============================================================================

resource "google_compute_region_backend_service" "nsx_backends" {
  for_each                        = toset(local.nsx_appliances)
  project                         = var.project_id
  name                            = "${var.resource_name_prefix}-${each.key}-backend"
  region                          = var.region
  protocol                        = "UNSPECIFIED"
  load_balancing_scheme           = "INTERNAL"
  network                         = var.vpc_network
  connection_draining_timeout_sec = 0

  ha_policy {
    fast_ip_move = "GARP_RA"
    leader {
      backend_group = var.nsx_neg_self_link
      network_endpoint {
        instance = var.leader_instance
      }
    }
  }

  backend {
    group          = var.nsx_neg_self_link
    balancing_mode = "CONNECTION"
  }
}

resource "google_compute_forwarding_rule" "nsx_forwarding_rules" {
  for_each              = toset(local.nsx_appliances)
  project               = var.project_id
  name                  = "${var.resource_name_prefix}-${each.key}-fr"
  region                = var.region
  load_balancing_scheme = "INTERNAL"
  backend_service       = google_compute_region_backend_service.nsx_backends[each.key].self_link
  subnetwork            = var.nsx_tep_subnet_name
  network               = var.vpc_network
  ip_protocol           = "L3_DEFAULT"
  all_ports             = true
  allow_global_access   = true
  ip_address            = module.nsx_ip_allocator.effective_ip_map[each.key]
}

# ==============================================================================
# 4. Cloud DNS Records for Management Appliances (Forward A & Reverse PTR)
# ==============================================================================

resource "google_dns_record_set" "appliance_forward_a_records" {
  for_each     = (var.create_dns_records && var.forward_zone_name != null && var.forward_zone_name != "") ? local.appliance_dns_records : {}
  project      = var.project_id
  name         = "${each.key}.${local.formatted_domain_name}"
  managed_zone = var.forward_zone_name
  type         = "A"
  ttl          = var.dns_ttl
  rrdatas      = [each.value]

  depends_on = [google_compute_forwarding_rule.mgmt_forwarding_rules]
}

resource "google_dns_record_set" "appliance_reverse_ptr_records" {
  for_each     = (var.create_dns_records && var.reverse_zone_name != null && var.reverse_zone_name != "") ? local.appliance_dns_records : {}
  project      = var.project_id
  name         = local.appliance_ptr_record_names[each.key]
  managed_zone = var.reverse_zone_name
  type         = "PTR"
  ttl          = var.dns_ttl
  rrdatas      = ["${each.key}.${local.formatted_domain_name}"]

  depends_on = [google_compute_forwarding_rule.mgmt_forwarding_rules]
}

# ==============================================================================
# 5. Plan-Phase Module Validation Checks
# ==============================================================================

check "validate_appliance_dns_zones" {
  assert {
    condition = !var.create_dns_records || (
      (var.forward_zone_name != null && var.forward_zone_name != "") &&
      (var.reverse_zone_name != null && var.reverse_zone_name != "") &&
      (var.domain_name != null && var.domain_name != "") &&
      (var.reverse_domain_name != null && var.reverse_domain_name != "" && can(regex("in-addr\\.arpa", var.reverse_domain_name)))
    )
    error_message = "When create_dns_records is true, domain_name, forward_zone_name, reverse_zone_name, and reverse_domain_name must all be explicitly provided, and reverse_domain_name must contain 'in-addr.arpa'."
  }
}

check "validate_appliance_mgmt_ips_in_subnet" {
  assert {
    condition = alltrue([
      for item in local.mgmt_expanded_entities :
      item.ip == "" || (
        (parseint(split(".", item.ip)[0], 10) * 16777216 + parseint(split(".", item.ip)[1], 10) * 65536 + parseint(split(".", item.ip)[2], 10) * 256 + parseint(split(".", item.ip)[3], 10)) >= local.mgmt_cidr_start_int &&
        (parseint(split(".", item.ip)[0], 10) * 16777216 + parseint(split(".", item.ip)[1], 10) * 65536 + parseint(split(".", item.ip)[2], 10) * 256 + parseint(split(".", item.ip)[3], 10)) < local.mgmt_cidr_end_int
      )
    ])
    error_message = "Configured Management appliance IP addresses in mgmt_ip_values do not belong to the management subnet CIDR (${var.mgmt_subnet_cidr})."
  }
}

check "validate_appliance_nsx_ips_in_subnet" {
  assert {
    condition = alltrue([
      for item in local.nsx_expanded_entities :
      item.ip == "" || (
        (parseint(split(".", item.ip)[0], 10) * 16777216 + parseint(split(".", item.ip)[1], 10) * 65536 + parseint(split(".", item.ip)[2], 10) * 256 + parseint(split(".", item.ip)[3], 10)) >= local.nsx_tep_cidr_start_int &&
        (parseint(split(".", item.ip)[0], 10) * 16777216 + parseint(split(".", item.ip)[1], 10) * 65536 + parseint(split(".", item.ip)[2], 10) * 256 + parseint(split(".", item.ip)[3], 10)) < local.nsx_tep_cidr_end_int
      )
    ])
    error_message = "Configured NSX datapath appliance IP addresses in nsx_ip_values do not belong to the NSX TEP subnet CIDR (${var.nsx_tep_subnet_cidr})."
  }
}
