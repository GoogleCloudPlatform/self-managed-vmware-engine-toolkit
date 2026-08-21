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

output "node_names" {
  value       = local.effective_node_names
  description = "List of bare-metal ESXi host instance names"
}

output "node_self_links" {
  value       = google_compute_instance.nodes[*].self_link
  description = "List of self links for the provisioned bare-metal ESXi instances"
}

output "node_mgmt_ips" {
  value       = google_compute_instance.nodes[*].network_interface[0].network_ip
  description = "List of Management NIC IP addresses assigned to ESXi hosts"
}

output "node_primary_ips" {
  value       = google_compute_instance.nodes[*].network_interface[0].network_ip
  description = "Alias for Management NIC IP addresses for compatibility"
}

output "node_vsan_ips" {
  value       = [for instance in google_compute_instance.nodes : instance.network_interface[1].network_ip]
  description = "List of vSAN NIC IP addresses assigned to ESXi hosts"
}

output "node_vmotion_ips" {
  value       = [for instance in google_compute_instance.nodes : instance.network_interface[2].network_ip]
  description = "List of vMotion NIC IP addresses assigned to ESXi hosts"
}

output "node_nsx_tep_ips" {
  value       = [for instance in google_compute_instance.nodes : instance.network_interface[3].network_ip]
  description = "List of NSX TEP NIC IP addresses assigned to ESXi hosts"
}

output "node_dynamic_nic_ips" {
  value = {
    for idx, nic in var.additional_dynamic_nics : nic.name => [
      for instance in google_compute_instance.nodes : instance.network_interface[4 + idx].network_ip
    ]
  }
  description = "Map of dynamic NIC names to lists of assigned IP addresses across all host instances"
}

output "placement_policy_name" {
  value       = var.create_placement_policy ? (length(google_compute_resource_policy.placement_policy) > 0 ? google_compute_resource_policy.placement_policy[0].name : null) : (length(data.google_compute_resource_policy.existing_policy) > 0 ? data.google_compute_resource_policy.existing_policy[0].name : null)
  description = "Name of the compute placement policy"
}

output "placement_policy_self_link" {
  value       = var.create_placement_policy ? (length(google_compute_resource_policy.placement_policy) > 0 ? google_compute_resource_policy.placement_policy[0].self_link : null) : (length(data.google_compute_resource_policy.existing_policy) > 0 ? data.google_compute_resource_policy.existing_policy[0].self_link : null)
  description = "Self link of the compute placement policy"
}

output "mgmt_reserved_addresses" {
  value       = module.mgmt_ip_allocator.reserved_addresses
  description = "List of reserved Management IP addresses (empty if not reserved)"
}

output "primary_reserved_addresses" {
  value       = module.mgmt_ip_allocator.reserved_addresses
  description = "Alias for Management reserved IP addresses for compatibility"
}

output "vsan_reserved_addresses" {
  value       = module.vsan_ip_allocator.reserved_addresses
  description = "List of reserved vSAN IP addresses (empty if not reserved)"
}

output "vmotion_reserved_addresses" {
  value       = module.vmotion_ip_allocator.reserved_addresses
  description = "List of reserved vMotion IP addresses (empty if not reserved)"
}

output "nsx_tep_reserved_addresses" {
  value       = module.nsx_tep_ip_allocator.reserved_addresses
  description = "List of reserved NSX TEP IP addresses (empty if not reserved)"
}

output "dynamic_reserved_addresses" {
  value = {
    for k, v in module.dynamic_nic_ip_allocators : k => v.reserved_addresses
  }
  description = "Map of dynamic NIC names to lists of reserved IP addresses"
}

output "host_dns_forward_a_records" {
  value       = [for r in google_dns_record_set.node_forward_a_records : r.name]
  description = "List of created forward A record FQDNs for ESXi hosts"
}

output "host_dns_reverse_ptr_records" {
  value       = [for r in google_dns_record_set.node_reverse_ptr_records : r.name]
  description = "List of created reverse PTR record names for ESXi hosts"
}
