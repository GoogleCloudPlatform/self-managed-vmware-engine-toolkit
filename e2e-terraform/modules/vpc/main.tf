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
  vpc_network_name = var.create_vpc ? (
    var.vpc_network != null ? var.vpc_network : "${var.resource_name_prefix}-vpc"
  ) : var.vpc_network

  vpc_name_only = local.vpc_network_name != null ? split("/", local.vpc_network_name)[length(split("/", local.vpc_network_name)) - 1] : null

  vpc_network_self_link = var.create_vpc ? google_compute_network.vpc[0].self_link : (
    length(data.google_compute_network.existing_vpc) > 0 ? data.google_compute_network.existing_vpc[0].self_link : (
      can(regex("^https://|^projects/", var.vpc_network)) ? var.vpc_network : (
        var.project_id != null && var.project_id != "" ? "projects/${var.project_id}/global/networks/${var.vpc_network}" : var.vpc_network
      )
    )
  )

  formatted_domain_name = var.domain_name != null && var.domain_name != "" ? (
    endswith(var.domain_name, ".") ? var.domain_name : "${var.domain_name}."
  ) : null

  formatted_reverse_domain_name = var.reverse_domain_name != null && var.reverse_domain_name != "" ? (
    endswith(var.reverse_domain_name, ".") ? var.reverse_domain_name : "${var.reverse_domain_name}."
  ) : null

  effective_forward_zone_name = var.create_dns_zones ? (
    var.forward_zone_name != null ? var.forward_zone_name : "${var.resource_name_prefix}-forward-zone"
  ) : (var.setup_cloud_dns ? var.forward_zone_name : null)

  effective_reverse_zone_name = var.create_dns_zones ? (
    var.reverse_zone_name != null ? var.reverse_zone_name : "${var.resource_name_prefix}-reverse-zone"
  ) : (var.setup_cloud_dns ? var.reverse_zone_name : null)

  effective_gcp_subnet_name = var.create_gcp_subnet ? (
    var.gcp_subnet_name != null ? var.gcp_subnet_name : "${var.resource_name_prefix}-gcp-subnet"
  ) : var.gcp_subnet_name

  gcp_subnet_self_link = var.create_gcp_subnet ? google_compute_subnetwork.gcp_subnet[0].self_link : data.google_compute_subnetwork.existing_gcp_subnet[0].self_link

  effective_gcp_subnet_cidr = var.create_gcp_subnet ? var.gcp_subnet_cidr : data.google_compute_subnetwork.existing_gcp_subnet[0].ip_cidr_range

  create_dns_policy         = var.dns_policy_name != null && var.dns_policy_name != ""
  effective_dns_policy_name = var.dns_policy_name
}

# ==============================================================================
# 1. VPC Network Creation (Conditional) & Verification Data Source
# ==============================================================================

resource "google_compute_network" "vpc" {
  count                   = var.create_vpc ? 1 : 0
  project                 = var.project_id
  name                    = local.vpc_network_name
  auto_create_subnetworks = false
  routing_mode            = var.routing_mode
  mtu                     = 8896
}

data "google_compute_network" "existing_vpc" {
  count   = var.create_vpc ? 0 : 1
  project = var.project_id
  name    = local.vpc_name_only
}

# ==============================================================================
# 2. Standard GCP Subnetwork Creation / Reference (without resolve_subnet_mask)
# ==============================================================================

resource "google_compute_subnetwork" "gcp_subnet" {
  count                    = var.create_gcp_subnet ? 1 : 0
  project                  = var.project_id
  name                     = local.effective_gcp_subnet_name
  ip_cidr_range            = var.gcp_subnet_cidr
  region                   = var.region
  network                  = local.vpc_network_self_link
  private_ip_google_access = true

  depends_on = [google_compute_network.vpc]
}

data "google_compute_subnetwork" "existing_gcp_subnet" {
  count   = var.create_gcp_subnet ? 0 : 1
  project = var.project_id
  name    = local.effective_gcp_subnet_name
  region  = var.region

  lifecycle {
    postcondition {
      condition     = endswith(self.network, local.vpc_name_only)
      error_message = "The input GCP subnetwork '${local.effective_gcp_subnet_name}' does not belong to the input VPC network '${local.vpc_network_name}'."
    }
  }
}

# ==============================================================================
# 3. Security Firewall Rule (Conditional)
# ==============================================================================

resource "google_compute_firewall" "allow_all_ingress" {
  count     = var.create_firewalls ? 1 : 0
  name      = "${var.resource_name_prefix}-firewall-rule"
  network   = local.vpc_network_name
  project   = var.project_id
  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]

  depends_on = [google_compute_network.vpc]
}

# ==============================================================================
# 4. Cloud DNS Managed Zones & Inbound Policy (Conditional)
# ==============================================================================

# Forward Managed Private DNS Zone
resource "google_dns_managed_zone" "forward_zone" {
  count       = var.create_dns_zones ? 1 : 0
  project     = var.project_id
  name        = local.effective_forward_zone_name
  dns_name    = local.formatted_domain_name
  description = "Private forward DNS zone for ${local.formatted_domain_name}"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = local.vpc_network_self_link
    }
  }

  depends_on = [google_compute_network.vpc]
}

# Reverse Managed Private DNS Zone
resource "google_dns_managed_zone" "reverse_zone" {
  count       = var.create_dns_zones ? 1 : 0
  project     = var.project_id
  name        = local.effective_reverse_zone_name
  dns_name    = local.formatted_reverse_domain_name
  description = "Private reverse DNS zone for ${local.formatted_reverse_domain_name}"
  visibility  = "private"

  private_visibility_config {
    networks {
      network_url = local.vpc_network_self_link
    }
  }

  depends_on = [google_compute_network.vpc]
}

# Inbound DNS Forwarding Policy
resource "google_dns_policy" "dns_policy" {
  count                     = local.create_dns_policy ? 1 : 0
  project                   = var.project_id
  name                      = local.effective_dns_policy_name
  enable_inbound_forwarding = true

  networks {
    network_url = local.vpc_network_self_link
  }

  depends_on = [google_compute_network.vpc]
}

# Look up Cloud DNS Inbound Forwarding reserved IP addresses created by the DNS policy (or existing in VPC)
data "google_compute_addresses" "dns_resolvers" {
  project = var.project_id
  region  = var.region
  filter  = "purpose=\"DNS_RESOLVER\""

  depends_on = [google_dns_policy.dns_policy]
}

# ==============================================================================
# 5. Plan-Phase Module Validation Checks
# ==============================================================================

check "validate_existing_vpc_name" {
  assert {
    condition     = var.create_vpc || (var.vpc_network != null && var.vpc_network != "")
    error_message = "vpc_network name must be explicitly provided when create_vpc is false."
  }
}

check "validate_existing_dns_zones" {
  assert {
    condition     = !var.setup_cloud_dns || var.create_dns_zones || (var.forward_zone_name != null && var.forward_zone_name != "" && var.reverse_zone_name != null && var.reverse_zone_name != "")
    error_message = "When setup_cloud_dns is true and create_dns_zones is false, both forward_zone_name and reverse_zone_name must be explicitly provided."
  }
}

check "validate_dns_domain_names" {
  assert {
    condition = !var.create_dns_zones || (
      (var.domain_name != null && var.domain_name != "") &&
      (var.reverse_domain_name != null && var.reverse_domain_name != "")
    )
    error_message = "Both domain_name and reverse_domain_name are required when create_dns_zones is true."
  }
}

check "validate_existing_gcp_subnet" {
  assert {
    condition     = var.create_gcp_subnet || (var.gcp_subnet_name != null && var.gcp_subnet_name != "")
    error_message = "When create_gcp_subnet is false, gcp_subnet_name must be explicitly provided."
  }
}

check "validate_gcp_subnet_cidr" {
  assert {
    condition     = !var.create_gcp_subnet || (var.gcp_subnet_cidr != null && var.gcp_subnet_cidr != "" && can(cidrhost(var.gcp_subnet_cidr, 0)))
    error_message = "When create_gcp_subnet is true, gcp_subnet_cidr must be explicitly provided as a valid IPv4 CIDR string (e.g. 10.0.100.0/29)."
  }
}

