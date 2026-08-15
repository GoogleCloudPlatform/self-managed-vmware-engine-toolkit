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
# File: infrastructure/modules/network/main.tf
# Description: Handles subnetwork creation/lookup, configures IAP SSH ingress firewall,
#              and provisions Cloud Router & Cloud NAT for safe outbound internet access.
# ==============================================================================

# ------------------------------------------------------------------------------
# Resource: Create Subnet (Conditional)
# Created only when var.create_subnet is true.
# ------------------------------------------------------------------------------
resource "google_compute_subnetwork" "created_subnet" {
  count = var.create_subnet ? 1 : 0

  name                     = var.subnet_name
  ip_cidr_range            = var.subnet_cidr
  region                   = var.region
  network                  = var.vpc_name
  project                  = var.project_id
  private_ip_google_access = true

  description = "Subnet created for SMVE Toolkit Jumpbox VM"

  lifecycle {
    precondition {
      condition     = var.vpc_name != ""
      error_message = "'vpc_name' must be provided when 'create_subnet' is set to true."
    }
    precondition {
      condition     = try(can(cidrnetmask(var.subnet_cidr)) && tonumber(split("/", var.subnet_cidr)[1]) <= 29, false)
      error_message = "'subnet_cidr' must be a valid IPv4 CIDR range with a prefix length of /29 or larger (e.g. '10.10.0.0/28', /24). GCP VPC subnets require at least a /29 subnet size (minimum 8 IP addresses)."
    }
  }
}

# ------------------------------------------------------------------------------
# Data Source: Fetch Existing Subnet (Conditional)
# Used only when var.create_subnet is false.
# ------------------------------------------------------------------------------
data "google_compute_subnetwork" "existing_subnet" {
  count = var.create_subnet ? 0 : 1

  name    = var.subnet_name
  region  = var.region
  project = var.project_id

  lifecycle {
    postcondition {
      condition     = var.vpc_name == "" || element(reverse(split("/", self.network)), 0) == var.vpc_name
      error_message = "VPC network mismatch: Subnet '${var.subnet_name}' belongs to VPC network '${element(reverse(split("/", self.network)), 0)}', but 'vpc_name' was configured as '${var.vpc_name}'. Either update 'vpc_name' to match or leave it empty (\"\") to auto-detect the VPC from the subnet."
    }
  }
}

# ------------------------------------------------------------------------------
# Local Variables
# Derive the effective Subnet ID, Subnet Name, VPC Network name, Router name, and NAT name.
# ------------------------------------------------------------------------------
locals {
  subnet_id   = var.create_subnet ? google_compute_subnetwork.created_subnet[0].id : data.google_compute_subnetwork.existing_subnet[0].id
  subnet_name = var.create_subnet ? google_compute_subnetwork.created_subnet[0].name : data.google_compute_subnetwork.existing_subnet[0].name

  # Extract network name from existing subnetwork self_link if vpc_name was omitted
  vpc_network_name = var.create_subnet ? var.vpc_name : (
    var.vpc_name != "" ? var.vpc_name : element(reverse(split("/", data.google_compute_subnetwork.existing_subnet[0].network)), 0)
  )

  router_name   = "router-${local.subnet_name}"
  nat_name      = "nat-${local.subnet_name}"
  route_name    = "egress-internet-route-${local.subnet_name}"
  firewall_name = "allow-iap-ssh-${local.subnet_name}"
}

# ------------------------------------------------------------------------------
# Resource: Firewall Rule for IAP Tunneling SSH
# Allows inbound SSH (port 22) traffic exclusively from Google IAP netblock (35.235.240.0/20).
# Targeted via service account to scope access specifically to the Jumpbox VM.
# ------------------------------------------------------------------------------
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = local.firewall_name
  network = local.vpc_network_name
  project = var.project_id

  description = "Allow inbound SSH via Google Cloud Identity-Aware Proxy (IAP) to Jumpbox"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Official Google Cloud IAP TCP forwarding netblock range
  source_ranges = ["35.235.240.0/20"]

  # Target specifically the configured service account for scoped access
  target_service_accounts = [var.service_account_email]
}

# ------------------------------------------------------------------------------
# Resource: Cloud Router for NAT (Conditional)
# Provisions a Cloud Router in the region for outbound internet translation.
# ------------------------------------------------------------------------------
resource "google_compute_router" "nat_router" {
  count   = var.enable_internet ? 1 : 0
  name    = local.router_name
  network = local.vpc_network_name
  region  = var.region
  project = var.project_id

  description = "Cloud Router for SMVE Toolkit Jumpbox NAT gateway"
}

# ------------------------------------------------------------------------------
# Resource: Cloud NAT Gateway (Conditional)
# Provides egress internet connectivity for private jumpbox VM without exposing public IP.
# ------------------------------------------------------------------------------
resource "google_compute_router_nat" "nat_gateway" {
  count                              = var.enable_internet ? 1 : 0
  name                               = local.nat_name
  router                             = google_compute_router.nat_router[0].name
  region                             = var.region
  project                            = var.project_id
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = local.subnet_id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}

# ------------------------------------------------------------------------------
# Resource: Default Internet Route (Conditional)
# Provisions a default route (0.0.0.0/0 -> default-internet-gateway) in the VPC
# ensuring outbound NAT traffic can reach the internet gateway.
# ------------------------------------------------------------------------------
resource "google_compute_route" "default_internet_route" {
  count            = var.enable_internet ? 1 : 0
  name             = local.route_name
  network          = local.vpc_network_name
  dest_range       = "0.0.0.0/0"
  next_hop_gateway = "default-internet-gateway"
  priority         = 1000
  project          = var.project_id

  description = "Default route to default-internet-gateway for SMVE Toolkit Jumpbox Cloud NAT internet egress"
}
