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

output "effective_ips" {
  value = [
    for i, name in var.entities : (
      local.is_ephemeral_custom ? (try(local.entity_ip_map[name], "") != "" ? local.entity_ip_map[name] : null) : (
        local.is_reserved ? google_compute_address.reserved_ip[name].address : null
      )
    )
  ]
  description = "List of effective IP addresses to bind to instances or forwarding rules (null for ephemeral_automatic, custom IP for ephemeral_custom, reserved IP for reserved_automatic and reserved_custom)"
}

output "effective_ip_map" {
  value = {
    for name in var.entities : name => (
      local.is_ephemeral_custom ? (try(local.entity_ip_map[name], "") != "" ? local.entity_ip_map[name] : null) : (
        local.is_reserved ? google_compute_address.reserved_ip[name].address : null
      )
    )
  }
  description = "Map of entity names to effective IP addresses"
}

output "reserved_addresses" {
  value       = local.is_reserved ? [for e in var.entities : google_compute_address.reserved_ip[e].address] : []
  description = "List of reserved IP address values (empty if not reserved)"
}

output "reserved_address_self_links" {
  value       = local.is_reserved ? [for e in var.entities : google_compute_address.reserved_ip[e].self_link] : []
  description = "List of self links for reserved IP address resources (empty if not reserved)"
}
