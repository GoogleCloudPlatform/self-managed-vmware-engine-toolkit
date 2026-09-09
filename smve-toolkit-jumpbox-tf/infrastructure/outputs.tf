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
# File: infrastructure/outputs.tf
# Description: Specifies the output values returned after successful deployment.
# ==============================================================================

output "jumpbox_name" {
  description = "The name of the provisioned jumpbox GCE instance."
  value       = module.jumpbox.instance_name
}

output "jumpbox_internal_ip" {
  description = "The internal (private) IP address of the jumpbox instance."
  value       = module.jumpbox.internal_ip
}

output "jumpbox_zone" {
  description = "The GCP zone where the jumpbox instance is deployed."
  value       = local.effective_zone
}

output "service_account_email" {
  description = "The Service Account attached to the Jumpbox VM and targeted in the IAP firewall rule."
  value       = local.effective_service_account
}

output "subnet_name" {
  description = "The name of the subnet used by the jumpbox in the VPC hosting the ESXi nodes."
  value       = module.network.subnet_name
}

output "gcloud_ssh_command" {
  description = "Command for the user to SSH into the jumpbox using IAP tunneling."
  value       = "gcloud compute ssh ${module.jumpbox.instance_name} --project=${var.project_id} --zone=${local.effective_zone} --tunnel-through-iap"
}

output "router_name" {
  description = "The name of the provisioned Cloud Router (if enable_internet = true)."
  value       = module.network.router_name
}

output "nat_name" {
  description = "The name of the provisioned Cloud NAT gateway (if enable_internet = true)."
  value       = module.network.nat_name
}

output "route_name" {
  description = "The name of the provisioned default internet route (if enable_internet = true)."
  value       = module.network.route_name
}

output "firewall_rule_name" {
  description = "The name of the provisioned IAP SSH firewall rule."
  value       = module.network.firewall_rule_name
}
