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

output "vpc_network_name" {
  value       = local.vpc_network_name
  description = "The effective name of the VPC network"
}

output "vpc_network_self_link" {
  value       = local.vpc_network_self_link
  description = "The URI/self-link of the VPC network"
}

output "gcp_subnet_name" {
  value       = local.effective_gcp_subnet_name
  description = "Name of the GCP standard subnetwork for DNS resolution and offline depot"
}

output "gcp_subnet_self_link" {
  value       = local.gcp_subnet_self_link
  description = "Self-link URI of the GCP standard subnetwork for DNS resolution and offline depot"
}

output "gcp_subnet_cidr" {
  value       = local.effective_gcp_subnet_cidr
  description = "IPv4 CIDR block of the GCP standard subnetwork"
}

output "firewall_rule_allow_all_self_link" {
  value       = length(google_compute_firewall.allow_all_ingress) > 0 ? google_compute_firewall.allow_all_ingress[0].self_link : null
  description = "The self link of the allow-all ingress firewall rule (null if not created)"
}

# ------------------------------------------------------------------------------
# Cloud DNS Managed Zones & Policy Outputs
# ------------------------------------------------------------------------------

output "forward_zone_name" {
  value       = local.effective_forward_zone_name
  description = "Effective name of the forward managed DNS zone"
}

output "forward_zone_dns_name" {
  value       = var.domain_name
  description = "Forward DNS domain name"
}

output "forward_zone_id" {
  value       = length(google_dns_managed_zone.forward_zone) > 0 ? google_dns_managed_zone.forward_zone[0].id : null
  description = "The ID of the forward managed DNS zone (null if not created)"
}

output "reverse_zone_name" {
  value       = local.effective_reverse_zone_name
  description = "Effective name of the reverse managed DNS zone"
}

output "reverse_zone_dns_name" {
  value       = var.reverse_domain_name
  description = "Reverse DNS domain name"
}

output "reverse_zone_id" {
  value       = length(google_dns_managed_zone.reverse_zone) > 0 ? google_dns_managed_zone.reverse_zone[0].id : null
  description = "The ID of the reverse managed DNS zone (null if not created)"
}

output "dns_policy_name" {
  value       = local.effective_dns_policy_name
  description = "Effective name of the Cloud DNS inbound forwarding policy"
}

output "dns_policy_id" {
  value       = length(google_dns_policy.dns_policy) > 0 ? google_dns_policy.dns_policy[0].id : null
  description = "The ID of the Cloud DNS inbound forwarding policy (null if not created)"
}

output "dns_policy_self_link" {
  value       = local.create_dns_policy ? "https://www.googleapis.com/dns/v1/projects/${var.project_id}/policies/${local.effective_dns_policy_name}" : null
  description = "The URI/self-link of the Cloud DNS inbound forwarding policy"
}

output "dns_resolver_addresses" {
  value = [
    for addr in data.google_compute_addresses.dns_resolvers.addresses : {
      name    = addr.name
      address = addr.address
      status  = addr.status
    }
  ]
  description = "List of DNS resolver reserved IP address objects discovered in the region"
}

output "dns_reserved_ips" {
  value = [
    for addr in data.google_compute_addresses.dns_resolvers.addresses : addr.address
  ]
  description = "List of IP addresses reserved by Cloud DNS inbound forwarding policy"
}

