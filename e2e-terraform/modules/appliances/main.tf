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
  # Dynamically derive appliance lists directly from user-supplied input maps
  mgmt_appliances      = keys(var.mgmt_ip_values)
  mgmt_appliance_count = length(local.mgmt_appliances)

  nsx_appliances      = keys(var.nsx_ip_values)
  nsx_appliance_count = length(local.nsx_appliances)

  # All configured appliance IP mappings directly from forwarding rules
  mgmt_appliance_ips = {
    for idx, name in local.mgmt_appliances : name => google_compute_forwarding_rule.mgmt_forwarding_rules[idx].ip_address
  }

  nsx_appliance_ips = {
    for idx, name in local.nsx_appliances : name => google_compute_forwarding_rule.nsx_forwarding_rules[idx].ip_address
  }

  formatted_domain_name = var.domain_name != null && var.domain_name != "" ? (
    endswith(var.domain_name, ".") ? var.domain_name : "${var.domain_name}."
  ) : null

  # DNS records are created only for the IPs mentioned in the management appliances
  appliance_dns_records = {
    for name, ip in local.mgmt_appliance_ips : name => ip
    if trimspace(try(var.mgmt_ip_values[name], "")) != "" && try(var.mgmt_ip_values[name], null) != null
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
  ip_values             = var.mgmt_ip_values
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
  ip_values             = var.nsx_ip_values
}

# ==============================================================================
# 2. Regional Backend Services & Forwarding Rules for Management Appliances
# ==============================================================================

resource "google_compute_region_backend_service" "mgmt_backends" {
  count                           = local.mgmt_appliance_count
  project                         = var.project_id
  name                            = "${var.resource_name_prefix}-${local.mgmt_appliances[count.index]}-backend"
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
  count                 = local.mgmt_appliance_count
  project               = var.project_id
  name                  = "${var.resource_name_prefix}-${local.mgmt_appliances[count.index]}-fr"
  region                = var.region
  load_balancing_scheme = "INTERNAL"
  backend_service       = google_compute_region_backend_service.mgmt_backends[count.index].self_link
  subnetwork            = var.mgmt_subnet_name
  network               = var.vpc_network
  ip_protocol           = "L3_DEFAULT"
  all_ports             = true
  allow_global_access   = true
  ip_address            = module.mgmt_ip_allocator.effective_ips[count.index]
}

# ==============================================================================
# 3. Regional Backend Services & Forwarding Rules for NSX Datapath Appliances
# ==============================================================================

resource "google_compute_region_backend_service" "nsx_backends" {
  count                           = local.nsx_appliance_count
  project                         = var.project_id
  name                            = "${var.resource_name_prefix}-${local.nsx_appliances[count.index]}-backend"
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
  count                 = local.nsx_appliance_count
  project               = var.project_id
  name                  = "${var.resource_name_prefix}-${local.nsx_appliances[count.index]}-fr"
  region                = var.region
  load_balancing_scheme = "INTERNAL"
  backend_service       = google_compute_region_backend_service.nsx_backends[count.index].self_link
  subnetwork            = var.nsx_tep_subnet_name
  network               = var.vpc_network
  ip_protocol           = "L3_DEFAULT"
  all_ports             = true
  allow_global_access   = true
  ip_address            = module.nsx_ip_allocator.effective_ips[count.index]
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
      for ip in values(var.mgmt_ip_values) :
      ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
        (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.mgmt_cidr_start_int &&
        (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.mgmt_cidr_end_int
      )
    ])
    error_message = "Configured Management appliance IP addresses in mgmt_ip_values do not belong to the management subnet CIDR (${var.mgmt_subnet_cidr})."
  }
}

check "validate_appliance_nsx_ips_in_subnet" {
  assert {
    condition = alltrue([
      for ip in values(var.nsx_ip_values) :
      ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
        (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.nsx_tep_cidr_start_int &&
        (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.nsx_tep_cidr_end_int
      )
    ])
    error_message = "Configured NSX datapath appliance IP addresses in nsx_ip_values do not belong to the NSX TEP subnet CIDR (${var.nsx_tep_subnet_cidr})."
  }
}
