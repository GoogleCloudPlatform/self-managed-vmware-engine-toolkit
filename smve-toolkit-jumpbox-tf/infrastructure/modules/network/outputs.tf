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
# File: infrastructure/modules/network/outputs.tf
# Description: Output values for the Network submodule.
# ==============================================================================

output "subnet_name" {
  description = "The name of the created or fetched subnet."
  value       = local.subnet_name
}

output "vpc_network_name" {
  description = "The name of the VPC network (hosting the ESXi nodes) containing the subnet."
  value       = local.vpc_network_name
}

output "firewall_rule_name" {
  description = "The name of the created IAP SSH firewall rule."
  value       = google_compute_firewall.allow_iap_ssh.name
}

output "router_name" {
  description = "The name of the created Cloud Router (if enable_internet = true)."
  value       = var.enable_internet ? google_compute_router.nat_router[0].name : ""
}

output "nat_name" {
  description = "The name of the created Cloud NAT gateway (if enable_internet = true)."
  value       = var.enable_internet ? google_compute_router_nat.nat_gateway[0].name : ""
}

output "route_name" {
  description = "The name of the created default internet route (if enable_internet = true)."
  value       = var.enable_internet ? google_compute_route.default_internet_route[0].name : ""
}
