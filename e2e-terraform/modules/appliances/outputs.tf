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

output "management_backend_services" {
  value = {
    for idx, name in local.mgmt_appliances : name => google_compute_region_backend_service.mgmt_backends[idx].self_link
  }
  description = "Map of management appliance names to their regional backend service self links"
}

output "management_forwarding_rules" {
  value = {
    for idx, name in local.mgmt_appliances : name => google_compute_forwarding_rule.mgmt_forwarding_rules[idx].self_link
  }
  description = "Map of management appliance names to their regional forwarding rule self links"
}

output "management_forwarding_rule_ips" {
  value = {
    for idx, name in local.mgmt_appliances : name => google_compute_forwarding_rule.mgmt_forwarding_rules[idx].ip_address
  }
  description = "Map of management appliance names to their assigned forwarding rule IP addresses"
}

output "management_reserved_addresses" {
  value       = module.mgmt_ip_allocator.reserved_addresses
  description = "List of reserved IP address values for management forwarding rules (empty if not reserved)"
}

output "nsx_datapath_backend_services" {
  value = {
    for idx, name in local.nsx_appliances : name => google_compute_region_backend_service.nsx_backends[idx].self_link
  }
  description = "Map of NSX datapath appliance names to their regional backend service self links"
}

output "nsx_datapath_forwarding_rules" {
  value = {
    for idx, name in local.nsx_appliances : name => google_compute_forwarding_rule.nsx_forwarding_rules[idx].self_link
  }
  description = "Map of NSX datapath appliance names to their regional forwarding rule self links"
}

output "nsx_datapath_forwarding_rule_ips" {
  value = {
    for idx, name in local.nsx_appliances : name => google_compute_forwarding_rule.nsx_forwarding_rules[idx].ip_address
  }
  description = "Map of NSX datapath appliance names to their assigned forwarding rule IP addresses"
}


output "nsx_reserved_addresses" {
  value       = module.nsx_ip_allocator.reserved_addresses
  description = "List of reserved IP address values for NSX datapath forwarding rules (empty if not reserved)"
}

output "appliance_dns_forward_a_records" {
  value       = [for r in google_dns_record_set.appliance_forward_a_records : r.name]
  description = "List of created forward A record FQDNs for appliances"
}

output "appliance_dns_reverse_ptr_records" {
  value       = [for r in google_dns_record_set.appliance_reverse_ptr_records : r.name]
  description = "List of created reverse PTR record names for appliances"
}
