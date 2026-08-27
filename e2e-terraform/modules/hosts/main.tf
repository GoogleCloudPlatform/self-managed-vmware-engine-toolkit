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
      source                = "hashicorp/google"
      configuration_aliases = [google.alpha]
    }
  }
}

locals {
  effective_node_names = var.node_names != null ? var.node_names : [
    for i in range(var.number_of_nodes) : format("%s-node-%d", var.resource_name_prefix, i + 1)
  ]

  formatted_domain_name = var.domain_name != null && var.domain_name != "" ? (
    endswith(var.domain_name, ".") ? var.domain_name : "${var.domain_name}."
  ) : null

  effective_hostnames = [
    for name in local.effective_node_names : "${name}.${trimsuffix(var.domain_name, ".")}"
  ]

  effective_availability_count = var.create_placement_policy ? var.availability_count : data.google_compute_resource_policy.existing_policy[0].group_placement_policy[0].availability_domain_count

  effective_availability_domains = var.availability_domains != null ? var.availability_domains : [
    for i in range(var.number_of_nodes) : ((i % local.effective_availability_count) + 1)
  ]

  esxi_hosts_dns_map = {
    for i, name in local.effective_node_names : name => google_compute_instance.nodes[i].network_interface[0].network_ip
  }

  node_ptr_record_names = {
    for name, ip in local.esxi_hosts_dns_map : name => "${join(".", reverse(split(".", ip)))}.in-addr.arpa."
  }

  effective_placement_policy_name = var.create_placement_policy ? (
    var.placement_policy_name != null ? var.placement_policy_name : "${var.resource_name_prefix}-placement-policy"
  ) : var.placement_policy_name

  # Management Subnet CIDR Range Bounds for Validation
  mgmt_cidr_parts     = (var.mgmt_subnet_cidr != null && var.mgmt_subnet_cidr != "" && can(cidrnetmask(var.mgmt_subnet_cidr))) ? split("/", var.mgmt_subnet_cidr) : []
  mgmt_cidr_octets    = length(local.mgmt_cidr_parts) == 2 ? [for o in split(".", local.mgmt_cidr_parts[0]) : parseint(o, 10)] : []
  mgmt_cidr_start_int = length(local.mgmt_cidr_octets) == 4 ? (local.mgmt_cidr_octets[0] * 16777216 + local.mgmt_cidr_octets[1] * 65536 + local.mgmt_cidr_octets[2] * 256 + local.mgmt_cidr_octets[3]) : 0
  mgmt_cidr_mask      = length(local.mgmt_cidr_parts) == 2 ? parseint(local.mgmt_cidr_parts[1], 10) : 0
  mgmt_cidr_end_int   = local.mgmt_cidr_start_int + (local.mgmt_cidr_mask > 0 ? pow(2, 32 - local.mgmt_cidr_mask) : 0)

  # vSAN Subnet CIDR Range Bounds for Validation
  vsan_cidr_parts     = (var.vsan_subnet_cidr != null && var.vsan_subnet_cidr != "" && can(cidrnetmask(var.vsan_subnet_cidr))) ? split("/", var.vsan_subnet_cidr) : []
  vsan_cidr_octets    = length(local.vsan_cidr_parts) == 2 ? [for o in split(".", local.vsan_cidr_parts[0]) : parseint(o, 10)] : []
  vsan_cidr_start_int = length(local.vsan_cidr_octets) == 4 ? (local.vsan_cidr_octets[0] * 16777216 + local.vsan_cidr_octets[1] * 65536 + local.vsan_cidr_octets[2] * 256 + local.vsan_cidr_octets[3]) : 0
  vsan_cidr_mask      = length(local.vsan_cidr_parts) == 2 ? parseint(local.vsan_cidr_parts[1], 10) : 0
  vsan_cidr_end_int   = local.vsan_cidr_start_int + (local.vsan_cidr_mask > 0 ? pow(2, 32 - local.vsan_cidr_mask) : 0)

  # vMotion Subnet CIDR Range Bounds for Validation
  vmotion_cidr_parts     = (var.vmotion_subnet_cidr != null && var.vmotion_subnet_cidr != "" && can(cidrnetmask(var.vmotion_subnet_cidr))) ? split("/", var.vmotion_subnet_cidr) : []
  vmotion_cidr_octets    = length(local.vmotion_cidr_parts) == 2 ? [for o in split(".", local.vmotion_cidr_parts[0]) : parseint(o, 10)] : []
  vmotion_cidr_start_int = length(local.vmotion_cidr_octets) == 4 ? (local.vmotion_cidr_octets[0] * 16777216 + local.vmotion_cidr_octets[1] * 65536 + local.vmotion_cidr_octets[2] * 256 + local.vmotion_cidr_octets[3]) : 0
  vmotion_cidr_mask      = length(local.vmotion_cidr_parts) == 2 ? parseint(local.vmotion_cidr_parts[1], 10) : 0
  vmotion_cidr_end_int   = local.vmotion_cidr_start_int + (local.vmotion_cidr_mask > 0 ? pow(2, 32 - local.vmotion_cidr_mask) : 0)

  # NSX TEP Subnet CIDR Range Bounds for Validation
  nsx_tep_cidr_parts     = (var.nsx_tep_subnet_cidr != null && var.nsx_tep_subnet_cidr != "" && can(cidrnetmask(var.nsx_tep_subnet_cidr))) ? split("/", var.nsx_tep_subnet_cidr) : []
  nsx_tep_cidr_octets    = length(local.nsx_tep_cidr_parts) == 2 ? [for o in split(".", local.nsx_tep_cidr_parts[0]) : parseint(o, 10)] : []
  nsx_tep_cidr_start_int = length(local.nsx_tep_cidr_octets) == 4 ? (local.nsx_tep_cidr_octets[0] * 16777216 + local.nsx_tep_cidr_octets[1] * 65536 + local.nsx_tep_cidr_octets[2] * 256 + local.nsx_tep_cidr_octets[3]) : 0
  nsx_tep_cidr_mask      = length(local.nsx_tep_cidr_parts) == 2 ? parseint(local.nsx_tep_cidr_parts[1], 10) : 0
  nsx_tep_cidr_end_int   = local.nsx_tep_cidr_start_int + (local.nsx_tep_cidr_mask > 0 ? pow(2, 32 - local.nsx_tep_cidr_mask) : 0)

  # Dynamic Subnets CIDR Range Bounds Map (subnet_name => { start_int, end_int })
  dynamic_subnets_cidr_ranges = {
    for s in var.additional_dynamic_subnets : s.subnet_name => {
      start_int = (
        parseint(split(".", split("/", s.subnet_cidr)[0])[0], 10) * 16777216 +
        parseint(split(".", split("/", s.subnet_cidr)[0])[1], 10) * 65536 +
        parseint(split(".", split("/", s.subnet_cidr)[0])[2], 10) * 256 +
        parseint(split(".", split("/", s.subnet_cidr)[0])[3], 10)
      )
      end_int = (
        parseint(split(".", split("/", s.subnet_cidr)[0])[0], 10) * 16777216 +
        parseint(split(".", split("/", s.subnet_cidr)[0])[1], 10) * 65536 +
        parseint(split(".", split("/", s.subnet_cidr)[0])[2], 10) * 256 +
        parseint(split(".", split("/", s.subnet_cidr)[0])[3], 10)
      ) + pow(2, 32 - parseint(split("/", s.subnet_cidr)[1], 10))
    } if s.subnet_cidr != null && s.subnet_cidr != "" && can(cidrnetmask(s.subnet_cidr))
  }
}

# ==============================================================================
# 1. Placement Policy
# ==============================================================================

resource "google_compute_resource_policy" "placement_policy" {
  count   = var.create_placement_policy ? 1 : 0
  project = var.project_id
  name    = local.effective_placement_policy_name
  region  = var.region

  group_placement_policy {
    availability_domain_count = var.availability_count
  }
}

data "google_compute_resource_policy" "existing_policy" {
  count   = var.create_placement_policy ? 0 : 1
  project = var.project_id
  name    = local.effective_placement_policy_name
  region  = var.region
}

# ==============================================================================
# 2. Modular IP Allocators for Host Network Interfaces
# ==============================================================================

module "mgmt_ip_allocator" {
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = var.mgmt_subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-mgmt-ip-%s"
  ip_address_type       = var.mgmt_ip_address_type
  entities              = [for i in range(var.number_of_nodes) : tostring(i + 1)]
  ip_values             = var.mgmt_ip_values
}

module "vsan_ip_allocator" {
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = var.vsan_subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-vsan-ip-%s"
  ip_address_type       = var.vsan_ip_address_type
  entities              = [for i in range(var.number_of_nodes) : tostring(i + 1)]
  ip_values             = var.vsan_ip_values
}

module "vmotion_ip_allocator" {
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = var.vmotion_subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-vmotion-ip-%s"
  ip_address_type       = var.vmotion_ip_address_type
  entities              = [for i in range(var.number_of_nodes) : tostring(i + 1)]
  ip_values             = var.vmotion_ip_values
}

module "nsx_tep_ip_allocator" {
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = var.nsx_tep_subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-nsx-tep-ip-%s"
  ip_address_type       = var.nsx_tep_ip_address_type
  entities              = [for i in range(var.number_of_nodes) : tostring(i + 1)]
  ip_values             = var.nsx_tep_ip_values
}

module "dynamic_nic_ip_allocators" {
  for_each              = { for nic in var.additional_dynamic_nics : nic.name => nic }
  source                = "../ip_allocator"
  project_id            = var.project_id
  region                = var.region
  subnetwork            = each.value.subnet_name
  resource_name_prefix  = var.resource_name_prefix
  address_name_template = "%s-${each.key}-ip-%s"
  ip_address_type       = each.value.ip_address_type
  entities              = [for i in range(var.number_of_nodes) : tostring(i + 1)]
  ip_values             = each.value.ip_values != null ? each.value.ip_values : []
}

# ==============================================================================
# 3. GCE Bare Metal Node Disks & Instances
# ==============================================================================

resource "google_compute_disk" "boot_disks" {
  count                  = var.number_of_nodes
  project                = var.project_id
  name                   = "${local.effective_node_names[count.index]}-boot-disk"
  zone                   = var.zone
  image                  = var.esxi_image
  type                   = "hyperdisk-balanced"
  size                   = 128
  provisioned_iops       = 10000 # IOPS (I/O operations per second)
  provisioned_throughput = 290   # Throughput in MB/s

  guest_os_features {
    type = "IDPF"
  }

  guest_os_features {
    type = "GVNIC"
  }

  guest_os_features {
    type = "MULTI_IP_SUBNET"
  }

  labels = {
    gcve-node = "true"
  }
}

resource "google_compute_instance" "nodes" {
  count               = var.number_of_nodes
  project             = var.project_id
  name                = local.effective_node_names[count.index]
  machine_type        = var.machine_type
  zone                = var.zone
  deletion_protection = var.deletion_protection
  hostname            = local.effective_hostnames[count.index]
  can_ip_forward      = true

  labels = {
    gcve-node = "true"
  }
  tags = ["mm-gcve-node"]

  lifecycle {
    ignore_changes = [scratch_disk]
  }

  boot_disk {
    source = google_compute_disk.boot_disks[count.index].self_link
  }

  service_account {
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  network_performance_config {
    total_egress_bandwidth_tier = "TIER_1"
  }

  resource_policies = [
    var.create_placement_policy ? google_compute_resource_policy.placement_policy[0].self_link : data.google_compute_resource_policy.existing_policy[0].self_link
  ]

  scheduling {
    availability_domain = local.effective_availability_domains[count.index]
    on_host_maintenance = "TERMINATE"
    automatic_restart   = true
  }

  # Management NIC (nic0)
  network_interface {
    subnetwork = var.mgmt_subnet_name
    nic_type   = "IDPF"
    stack_type = "IPV4_ONLY"
    network_ip = module.mgmt_ip_allocator.effective_ips[count.index]
  }

  # vSAN NIC
  network_interface {
    subnetwork = var.vsan_subnet_name
    vlan       = var.vsan_vlan_id
    stack_type = "IPV4_ONLY"
    network_ip = module.vsan_ip_allocator.effective_ips[count.index]
  }

  # vMotion NIC
  network_interface {
    subnetwork = var.vmotion_subnet_name
    vlan       = var.vmotion_vlan_id
    stack_type = "IPV4_ONLY"
    network_ip = module.vmotion_ip_allocator.effective_ips[count.index]
  }

  # NSX TEP NIC
  network_interface {
    subnetwork = var.nsx_tep_subnet_name
    vlan       = var.nsx_tep_vlan_id
    stack_type = "IPV4_ONLY"
    network_ip = module.nsx_tep_ip_allocator.effective_ips[count.index]
  }

  # Additional Dynamic NICs
  dynamic "network_interface" {
    for_each = var.additional_dynamic_nics
    content {
      subnetwork = network_interface.value.subnet_name
      vlan       = network_interface.value.vlan_id
      stack_type = "IPV4_ONLY"
      network_ip = module.dynamic_nic_ip_allocators[network_interface.value.name].effective_ips[count.index]
    }
  }
}

# ==============================================================================
# 4. Attach Instances to Network Endpoint Groups (NEGs)
# ==============================================================================

# Attach host instances to Management NEG (batch resource for all nodes - only in cluster_creation mode)
resource "google_compute_network_endpoints" "mgmt_endpoints" {
  provider               = google.alpha
  count                  = (var.deployment_mode == "cluster_creation" && var.mgmt_neg_name != null && var.mgmt_neg_name != "") ? 1 : 0
  project                = var.project_id
  network_endpoint_group = var.mgmt_neg_name
  zone                   = var.zone
  deletion_policy        = "ABANDON" # To prevent detach call during destroy, instance deletion does not depend on detachment (implicitly handled)

  dynamic "network_endpoints" {
    for_each = google_compute_instance.nodes[*].name
    content {
      instance = network_endpoints.value
    }
  }
}

# Attach host instances to NSX TEP NEG (batch resource for all nodes - only in cluster_creation mode)
resource "google_compute_network_endpoints" "nsx_endpoints" {
  provider               = google.alpha
  count                  = (var.deployment_mode == "cluster_creation" && var.nsx_neg_name != null && var.nsx_neg_name != "") ? 1 : 0
  project                = var.project_id
  network_endpoint_group = var.nsx_neg_name
  zone                   = var.zone
  deletion_policy        = "ABANDON" # To prevent detach call during destroy, instance deletion does not depend on detachment (implicitly handled)

  dynamic "network_endpoints" {
    for_each = google_compute_instance.nodes[*].name
    content {
      instance = network_endpoints.value
    }
  }
}

# ==============================================================================
# 5. Cloud DNS Records for Bare-Metal ESXi Hosts (Forward A & Reverse PTR)
# ==============================================================================

resource "google_dns_record_set" "node_forward_a_records" {
  for_each     = (var.create_dns_records && var.forward_zone_name != null && var.forward_zone_name != "") ? local.esxi_hosts_dns_map : {}
  project      = var.project_id
  name         = "${each.key}.${local.formatted_domain_name}"
  managed_zone = var.forward_zone_name
  type         = "A"
  ttl          = var.dns_ttl
  rrdatas      = [each.value]

  depends_on = [google_compute_instance.nodes]
}

resource "google_dns_record_set" "node_reverse_ptr_records" {
  for_each     = (var.create_dns_records && var.reverse_zone_name != null && var.reverse_zone_name != "") ? local.esxi_hosts_dns_map : {}
  project      = var.project_id
  name         = local.node_ptr_record_names[each.key]
  managed_zone = var.reverse_zone_name
  type         = "PTR"
  ttl          = var.dns_ttl
  rrdatas      = ["${each.key}.${local.formatted_domain_name}"]

  depends_on = [google_compute_instance.nodes]
}

# ==============================================================================
# 6. Plan-Phase Module Validation Checks
# ==============================================================================

check "validate_existing_placement_policy_name" {
  assert {
    condition     = var.create_placement_policy || (var.placement_policy_name != null && var.placement_policy_name != "")
    error_message = "placement_policy_name must be explicitly provided when create_placement_policy is false."
  }
}

check "validate_node_names_count" {
  assert {
    condition     = var.node_names == null || length(var.node_names) == 0 || length(var.node_names) == var.number_of_nodes
    error_message = "Length of node_names (${length(var.node_names != null ? var.node_names : [])}) must equal number_of_nodes (${var.number_of_nodes})."
  }
}

check "validate_availability_domains" {
  assert {
    condition = var.availability_domains == null || length(var.availability_domains) == 0 || (
      length(var.availability_domains) == var.number_of_nodes &&
      alltrue([
        for ad in var.availability_domains :
        ad >= 1 && ad <= var.availability_count
      ])
    )
    error_message = "When availability_domains is specified, its length (${length(var.availability_domains != null ? var.availability_domains : [])}) must match number_of_nodes (${var.number_of_nodes}), and each value must be between 1 and availability_count (${var.availability_count})."
  }
}

check "custom_ip_counts" {
  assert {
    condition = (
      (!contains(["ephemeral_custom", "reserved_custom"], var.mgmt_ip_address_type) ? (length(var.mgmt_ip_values) == 0 || length(var.mgmt_ip_values) == var.number_of_nodes) : length(var.mgmt_ip_values) == var.number_of_nodes) &&
      (!contains(["ephemeral_custom", "reserved_custom"], var.vsan_ip_address_type) ? (length(var.vsan_ip_values) == 0 || length(var.vsan_ip_values) == var.number_of_nodes) : length(var.vsan_ip_values) == var.number_of_nodes) &&
      (!contains(["ephemeral_custom", "reserved_custom"], var.vmotion_ip_address_type) ? (length(var.vmotion_ip_values) == 0 || length(var.vmotion_ip_values) == var.number_of_nodes) : length(var.vmotion_ip_values) == var.number_of_nodes) &&
      (!contains(["ephemeral_custom", "reserved_custom"], var.nsx_tep_ip_address_type) ? (length(var.nsx_tep_ip_values) == 0 || length(var.nsx_tep_ip_values) == var.number_of_nodes) : length(var.nsx_tep_ip_values) == var.number_of_nodes) &&
      alltrue([
        for nic in var.additional_dynamic_nics :
        contains(["ephemeral_custom", "reserved_custom"], nic.ip_address_type) ? (nic.ip_values != null && length(nic.ip_values) == var.number_of_nodes) : (nic.ip_values == null || length(nic.ip_values) == 0 || length(nic.ip_values) == var.number_of_nodes)
      ])
    )
    error_message = "When an IP allocation mode is set to 'ephemeral_custom' or 'reserved_custom', the corresponding ip_values list (mgmt_ip_values, vsan_ip_values, vmotion_ip_values, nsx_tep_ip_values) must contain at least number_of_nodes (${var.number_of_nodes}) entries."
  }
}

check "validate_dynamic_subnets_and_nics_match" {
  assert {
    condition = (
      length(setsubtract([for s in var.additional_dynamic_subnets : s.subnet_name], [for nic in var.additional_dynamic_nics : nic.subnet_name])) == 0 &&
      length(setsubtract([for nic in var.additional_dynamic_nics : nic.subnet_name], [for s in var.additional_dynamic_subnets : s.subnet_name])) == 0
    )
    error_message = "Configured additional_dynamic_subnets and additional_dynamic_nics subnet names do not match. Each additional dynamic subnet must correspond to an additional dynamic NIC and vice versa."
  }
}

check "validate_host_dns_zones" {
  assert {
    condition = !var.create_dns_records || (
      (var.forward_zone_name != null && var.forward_zone_name != "") &&
      (var.reverse_zone_name != null && var.reverse_zone_name != "") &&
      (var.reverse_domain_name != null && var.reverse_domain_name != "" && can(regex("in-addr\\.arpa", var.reverse_domain_name)))
    )
    error_message = "When create_dns_records is true, forward_zone_name, reverse_zone_name, and reverse_domain_name must all be explicitly provided, and reverse_domain_name must contain 'in-addr.arpa'."
  }
}

check "vlan_id_uniqueness" {
  assert {
    condition = length(distinct(concat(
      [var.vsan_vlan_id, var.vmotion_vlan_id, var.nsx_tep_vlan_id],
      [for nic in var.additional_dynamic_nics : nic.vlan_id]
    ))) == 3 + length(var.additional_dynamic_nics)
    error_message = "All configured VLAN IDs (vSAN: ${var.vsan_vlan_id}, vMotion: ${var.vmotion_vlan_id}, NSX TEP: ${var.nsx_tep_vlan_id}, and dynamic NICs) must be distinct."
  }
}

check "validate_mgmt_ips_in_subnet" {
  assert {
    condition = (
      var.mgmt_subnet_cidr == null || var.mgmt_subnet_cidr == "" || (
        alltrue([
          for ip in var.mgmt_ip_values :
          ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.mgmt_cidr_start_int &&
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.mgmt_cidr_end_int
          )
        ])
      )
    )
    error_message = "Configured Management IP addresses in mgmt_ip_values do not belong to the management subnet CIDR (${var.mgmt_subnet_cidr != null ? var.mgmt_subnet_cidr : ""})."
  }
}

check "validate_vsan_ips_in_subnet" {
  assert {
    condition = (
      var.vsan_subnet_cidr == null || var.vsan_subnet_cidr == "" || (
        alltrue([
          for ip in var.vsan_ip_values :
          ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.vsan_cidr_start_int &&
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.vsan_cidr_end_int
          )
        ])
      )
    )
    error_message = "Configured vSAN IP addresses in vsan_ip_values do not belong to the vSAN subnet CIDR (${var.vsan_subnet_cidr != null ? var.vsan_subnet_cidr : ""})."
  }
}

check "validate_vmotion_ips_in_subnet" {
  assert {
    condition = (
      var.vmotion_subnet_cidr == null || var.vmotion_subnet_cidr == "" || (
        alltrue([
          for ip in var.vmotion_ip_values :
          ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.vmotion_cidr_start_int &&
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.vmotion_cidr_end_int
          )
        ])
      )
    )
    error_message = "Configured vMotion IP addresses in vmotion_ip_values do not belong to the vMotion subnet CIDR (${var.vmotion_subnet_cidr != null ? var.vmotion_subnet_cidr : ""})."
  }
}

check "validate_nsx_tep_ips_in_subnet" {
  assert {
    condition = (
      var.nsx_tep_subnet_cidr == null || var.nsx_tep_subnet_cidr == "" || (
        alltrue([
          for ip in var.nsx_tep_ip_values :
          ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.nsx_tep_cidr_start_int &&
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.nsx_tep_cidr_end_int
          )
        ])
      )
    )
    error_message = "Configured NSX TEP IP addresses in nsx_tep_ip_values do not belong to the NSX TEP subnet CIDR (${var.nsx_tep_subnet_cidr != null ? var.nsx_tep_subnet_cidr : ""})."
  }
}

check "validate_dynamic_nic_ips_in_subnet" {
  assert {
    condition = alltrue([
      for nic in var.additional_dynamic_nics :
      !contains(keys(local.dynamic_subnets_cidr_ranges), nic.subnet_name) || (
        alltrue([
          for ip in(nic.ip_values != null ? nic.ip_values : []) :
          ip == "" || !can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip)) || (
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) >= local.dynamic_subnets_cidr_ranges[nic.subnet_name].start_int &&
            (parseint(split(".", ip)[0], 10) * 16777216 + parseint(split(".", ip)[1], 10) * 65536 + parseint(split(".", ip)[2], 10) * 256 + parseint(split(".", ip)[3], 10)) < local.dynamic_subnets_cidr_ranges[nic.subnet_name].end_int
          )
        ])
      )
    ])
    error_message = "One or more dynamic NIC IP addresses in additional_dynamic_nics do not belong to their corresponding subnet CIDR range."
  }
}

