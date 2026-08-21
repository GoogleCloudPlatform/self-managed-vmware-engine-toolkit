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
# 1. Subnetwork Self-Links
# ==============================================================================

output "mgmt_subnet_self_link" {
  value       = var.create_subnets_and_negs ? (length(google_compute_subnetwork.mgmt_subnet) > 0 ? google_compute_subnetwork.mgmt_subnet[0].self_link : null) : (length(data.google_compute_subnetwork.existing_mgmt_subnet) > 0 ? data.google_compute_subnetwork.existing_mgmt_subnet[0].self_link : null)
  description = "Management subnetwork self-link URL"
}

output "vsan_subnet_self_link" {
  value       = var.create_subnets_and_negs ? (length(google_compute_subnetwork.vsan_subnet) > 0 ? google_compute_subnetwork.vsan_subnet[0].self_link : null) : (length(data.google_compute_subnetwork.existing_vsan_subnet) > 0 ? data.google_compute_subnetwork.existing_vsan_subnet[0].self_link : null)
  description = "vSAN storage subnetwork self-link URL"
}

output "vmotion_subnet_self_link" {
  value       = var.create_subnets_and_negs ? (length(google_compute_subnetwork.vmotion_subnet) > 0 ? google_compute_subnetwork.vmotion_subnet[0].self_link : null) : (length(data.google_compute_subnetwork.existing_vmotion_subnet) > 0 ? data.google_compute_subnetwork.existing_vmotion_subnet[0].self_link : null)
  description = "vMotion migration subnetwork self-link URL"
}

output "nsx_tep_subnet_self_link" {
  value       = var.create_subnets_and_negs ? (length(google_compute_subnetwork.nsx_tep_subnet) > 0 ? google_compute_subnetwork.nsx_tep_subnet[0].self_link : null) : (length(data.google_compute_subnetwork.existing_nsx_tep_subnet) > 0 ? data.google_compute_subnetwork.existing_nsx_tep_subnet[0].self_link : null)
  description = "NSX TEP datapath subnetwork self-link URL"
}

output "dynamic_subnets" {
  value = var.create_subnets_and_negs ? {
    for k, v in google_compute_subnetwork.dynamic_subnets : k => {
      name      = v.name
      self_link = v.self_link
      cidr      = v.ip_cidr_range
    }
    } : {
    for k, v in data.google_compute_subnetwork.existing_dynamic_subnets : k => {
      name      = v.name
      self_link = v.self_link
      cidr      = v.ip_cidr_range
    }
  }
  description = "Map of dynamic subnets"
}

# ==============================================================================
# 2. Subnetwork Names & Static Plan-Time CIDRs
# ==============================================================================

output "mgmt_subnet_name" {
  value       = local.effective_mgmt_subnet_name
  description = "Management subnetwork name"
}

output "mgmt_subnet_cidr" {
  value       = var.create_subnets_and_negs ? var.mgmt_subnet_cidr : (length(data.google_compute_subnetwork.existing_mgmt_subnet) > 0 ? data.google_compute_subnetwork.existing_mgmt_subnet[0].ip_cidr_range : null)
  description = "Management subnetwork IPv4 CIDR range"
}

output "vsan_subnet_name" {
  value       = local.effective_vsan_subnet_name
  description = "vSAN storage subnetwork name"
}

output "vsan_subnet_cidr" {
  value       = var.create_subnets_and_negs ? var.vsan_subnet_cidr : (length(data.google_compute_subnetwork.existing_vsan_subnet) > 0 ? data.google_compute_subnetwork.existing_vsan_subnet[0].ip_cidr_range : null)
  description = "vSAN storage subnetwork IPv4 CIDR range"
}

output "vmotion_subnet_name" {
  value       = local.effective_vmotion_subnet_name
  description = "vMotion migration subnetwork name"
}

output "vmotion_subnet_cidr" {
  value       = var.create_subnets_and_negs ? var.vmotion_subnet_cidr : (length(data.google_compute_subnetwork.existing_vmotion_subnet) > 0 ? data.google_compute_subnetwork.existing_vmotion_subnet[0].ip_cidr_range : null)
  description = "vMotion migration subnetwork IPv4 CIDR range"
}

output "nsx_tep_subnet_name" {
  value       = local.effective_nsx_tep_subnet_name
  description = "NSX TEP datapath subnetwork name"
}

output "nsx_tep_subnet_cidr" {
  value       = var.create_subnets_and_negs ? var.nsx_tep_subnet_cidr : (length(data.google_compute_subnetwork.existing_nsx_tep_subnet) > 0 ? data.google_compute_subnetwork.existing_nsx_tep_subnet[0].ip_cidr_range : null)
  description = "NSX TEP datapath subnetwork IPv4 CIDR range"
}

output "dynamic_subnet_cidrs" {
  value = var.create_subnets_and_negs ? {
    for s in var.additional_dynamic_subnets : s.subnet_name => s.subnet_cidr
    } : {
    for k, v in data.google_compute_subnetwork.existing_dynamic_subnets : k => v.ip_cidr_range
  }
  description = "Map of dynamic subnet names to their IPv4 CIDR ranges"
}

# ==============================================================================
# 3. Network Endpoint Groups (NEGs)
# ==============================================================================

output "mgmt_neg_name" {
  value       = local.effective_mgmt_neg_name
  description = "Name of the Management NIC Network Endpoint Group"
}

output "mgmt_neg_self_link" {
  value       = var.create_subnets_and_negs ? (length(google_compute_network_endpoint_group.mgmt_neg) > 0 ? google_compute_network_endpoint_group.mgmt_neg[0].self_link : null) : (length(data.google_compute_network_endpoint_group.existing_mgmt_neg) > 0 ? data.google_compute_network_endpoint_group.existing_mgmt_neg[0].self_link : null)
  description = "Self link URL of the Management NIC Network Endpoint Group"
}

output "nsx_neg_name" {
  value       = local.effective_nsx_neg_name
  description = "Name of the NSX TEP NIC Network Endpoint Group"
}

output "nsx_neg_self_link" {
  value       = var.create_subnets_and_negs ? (length(google_compute_network_endpoint_group.nsx_neg) > 0 ? google_compute_network_endpoint_group.nsx_neg[0].self_link : null) : (length(data.google_compute_network_endpoint_group.existing_nsx_neg) > 0 ? data.google_compute_network_endpoint_group.existing_nsx_neg[0].self_link : null)
  description = "Self link URL of the NSX TEP NIC Network Endpoint Group"
}
