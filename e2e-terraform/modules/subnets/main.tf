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
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source                = "hashicorp/google"
      version               = ">= 4.80.0"
    }
  }
}

locals {
  vpc_name_only = split("/", var.vpc_network)[length(split("/", var.vpc_network)) - 1]

  effective_mgmt_subnet_name = var.create_subnets_and_negs ? (
    var.mgmt_subnet_name != null ? var.mgmt_subnet_name : "${var.resource_name_prefix}-mgmt-subnet"
  ) : var.mgmt_subnet_name

  effective_vsan_subnet_name = var.create_subnets_and_negs ? (
    var.vsan_subnet_name != null ? var.vsan_subnet_name : "${var.resource_name_prefix}-vsan-subnet"
  ) : var.vsan_subnet_name

  effective_vmotion_subnet_name = var.create_subnets_and_negs ? (
    var.vmotion_subnet_name != null ? var.vmotion_subnet_name : "${var.resource_name_prefix}-vmotion-subnet"
  ) : var.vmotion_subnet_name

  effective_nsx_tep_subnet_name = var.create_subnets_and_negs ? (
    var.nsx_tep_subnet_name != null ? var.nsx_tep_subnet_name : "${var.resource_name_prefix}-nsx-tep-subnet"
  ) : var.nsx_tep_subnet_name

  effective_mgmt_neg_name = var.create_subnets_and_negs ? (
    var.mgmt_neg_name != null ? var.mgmt_neg_name : "${var.resource_name_prefix}-mgmt-neg"
  ) : var.mgmt_neg_name

  effective_nsx_neg_name = var.create_subnets_and_negs ? (
    var.nsx_neg_name != null ? var.nsx_neg_name : "${var.resource_name_prefix}-nsx-neg"
  ) : var.nsx_neg_name
}

# ==============================================================================
# 1. Subnetworks Creation (When create_subnets_and_negs = true)
# ==============================================================================

# Management Subnetwork (Untagged Native VLAN on nic0)
resource "google_compute_subnetwork" "mgmt_subnet" {
  count                    = var.create_subnets_and_negs ? 1 : 0
  project                  = var.project_id
  name                     = local.effective_mgmt_subnet_name
  ip_cidr_range            = var.mgmt_subnet_cidr
  region                   = var.region
  network                  = var.vpc_network
  resolve_subnet_mask      = "ARP_BROADCAST_PRIMARY_RANGE_WITH_LEARNING"
  private_ip_google_access = true
}

# vSAN Storage Subnetwork
resource "google_compute_subnetwork" "vsan_subnet" {
  count                    = var.create_subnets_and_negs ? 1 : 0
  project                  = var.project_id
  name                     = local.effective_vsan_subnet_name
  ip_cidr_range            = var.vsan_subnet_cidr
  region                   = var.region
  network                  = var.vpc_network
  resolve_subnet_mask      = "ARP_BROADCAST_PRIMARY_RANGE_WITH_LEARNING"
  private_ip_google_access = true
}

# vMotion Migration Subnetwork
resource "google_compute_subnetwork" "vmotion_subnet" {
  count                    = var.create_subnets_and_negs ? 1 : 0
  project                  = var.project_id
  name                     = local.effective_vmotion_subnet_name
  ip_cidr_range            = var.vmotion_subnet_cidr
  region                   = var.region
  network                  = var.vpc_network
  resolve_subnet_mask      = "ARP_BROADCAST_PRIMARY_RANGE_WITH_LEARNING"
  private_ip_google_access = true
}

# NSX TEP Overlay Subnetwork
resource "google_compute_subnetwork" "nsx_tep_subnet" {
  count                    = var.create_subnets_and_negs ? 1 : 0
  project                  = var.project_id
  name                     = local.effective_nsx_tep_subnet_name
  ip_cidr_range            = var.nsx_tep_subnet_cidr
  region                   = var.region
  network                  = var.vpc_network
  resolve_subnet_mask      = "ARP_BROADCAST_PRIMARY_RANGE_WITH_LEARNING"
  private_ip_google_access = true
}

# Additional Dynamic VLAN Subnetworks
resource "google_compute_subnetwork" "dynamic_subnets" {
  for_each                 = var.create_subnets_and_negs ? { for s in var.additional_dynamic_subnets : s.subnet_name => s } : {}
  project                  = var.project_id
  name                     = each.value.subnet_name
  ip_cidr_range            = each.value.subnet_cidr
  region                   = var.region
  network                  = var.vpc_network
  resolve_subnet_mask      = "ARP_BROADCAST_PRIMARY_RANGE_WITH_LEARNING"
  private_ip_google_access = true
}

# ==============================================================================
# 2. Subnetwork Existence Checks (When create_subnets_and_negs = false)
# ==============================================================================

data "google_compute_subnetwork" "existing_mgmt_subnet" {
  count   = var.create_subnets_and_negs ? 0 : 1
  project = var.project_id
  name    = local.effective_mgmt_subnet_name
  region  = var.region

  lifecycle {
    postcondition {
      condition     = endswith(self.network, local.vpc_name_only)
      error_message = "The input Management subnetwork '${local.effective_mgmt_subnet_name}' does not belong to the input VPC network '${var.vpc_network}'."
    }
  }
}

data "google_compute_subnetwork" "existing_vsan_subnet" {
  count   = var.create_subnets_and_negs ? 0 : 1
  project = var.project_id
  name    = local.effective_vsan_subnet_name
  region  = var.region

  lifecycle {
    postcondition {
      condition     = endswith(self.network, local.vpc_name_only)
      error_message = "The input vSAN subnetwork '${local.effective_vsan_subnet_name}' does not belong to the input VPC network '${var.vpc_network}'."
    }
  }
}

data "google_compute_subnetwork" "existing_vmotion_subnet" {
  count   = var.create_subnets_and_negs ? 0 : 1
  project = var.project_id
  name    = local.effective_vmotion_subnet_name
  region  = var.region

  lifecycle {
    postcondition {
      condition     = endswith(self.network, local.vpc_name_only)
      error_message = "The input vMotion subnetwork '${local.effective_vmotion_subnet_name}' does not belong to the input VPC network '${var.vpc_network}'."
    }
  }
}

data "google_compute_subnetwork" "existing_nsx_tep_subnet" {
  count   = var.create_subnets_and_negs ? 0 : 1
  project = var.project_id
  name    = local.effective_nsx_tep_subnet_name
  region  = var.region

  lifecycle {
    postcondition {
      condition     = endswith(self.network, local.vpc_name_only)
      error_message = "The input NSX TEP subnetwork '${local.effective_nsx_tep_subnet_name}' does not belong to the input VPC network '${var.vpc_network}'."
    }
  }
}

data "google_compute_subnetwork" "existing_dynamic_subnets" {
  for_each = var.create_subnets_and_negs ? {} : { for s in var.additional_dynamic_subnets : s.subnet_name => s }
  project  = var.project_id
  name     = each.value.subnet_name
  region   = var.region

  lifecycle {
    postcondition {
      condition     = endswith(self.network, local.vpc_name_only)
      error_message = "The input dynamic subnetwork '${each.value.subnet_name}' does not belong to the input VPC network '${var.vpc_network}'."
    }
  }
}

# ==============================================================================
# 3. Network Endpoint Groups (NEGs) Creation (create_subnets_and_negs = true)
# ==============================================================================

resource "google_compute_network_endpoint_group" "mgmt_neg" {
  count                 = var.create_subnets_and_negs ? 1 : 0
  project               = var.project_id
  name                  = local.effective_mgmt_neg_name
  zone                  = var.zone
  network               = var.vpc_network
  subnetwork            = local.effective_mgmt_subnet_name
  network_endpoint_type = "GCE_VM_IP_DEDICATED_BACKEND"

  depends_on = [google_compute_subnetwork.mgmt_subnet]
}

resource "google_compute_network_endpoint_group" "nsx_neg" {
  count                 = var.create_subnets_and_negs ? 1 : 0
  project               = var.project_id
  name                  = local.effective_nsx_neg_name
  zone                  = var.zone
  network               = var.vpc_network
  subnetwork            = local.effective_nsx_tep_subnet_name
  network_endpoint_type = "GCE_VM_IP_DEDICATED_BACKEND"

  depends_on = [google_compute_subnetwork.nsx_tep_subnet]
}

# ==============================================================================
# 4. Network Endpoint Groups (NEGs) Lookups (create_subnets_and_negs = false)
# ==============================================================================

data "google_compute_network_endpoint_group" "existing_mgmt_neg" {
  count   = (!var.create_subnets_and_negs && var.mgmt_neg_name != null) ? 1 : 0
  project = var.project_id
  name    = local.effective_mgmt_neg_name
  zone    = var.zone
}

data "google_compute_network_endpoint_group" "existing_nsx_neg" {
  count   = (!var.create_subnets_and_negs && var.nsx_neg_name != null) ? 1 : 0
  project = var.project_id
  name    = local.effective_nsx_neg_name
  zone    = var.zone
}

# ==============================================================================
# 5. Plan-Phase Module Validation Checks
# ==============================================================================

check "validate_existing_subnet_names" {
  assert {
    condition = var.create_subnets_and_negs || (
      (var.mgmt_subnet_name != null && var.mgmt_subnet_name != "") &&
      (var.vsan_subnet_name != null && var.vsan_subnet_name != "") &&
      (var.vmotion_subnet_name != null && var.vmotion_subnet_name != "") &&
      (var.nsx_tep_subnet_name != null && var.nsx_tep_subnet_name != "")
    )
    error_message = "When create_subnets_and_negs is false, all required subnet names (mgmt_subnet_name, vsan_subnet_name, vmotion_subnet_name, nsx_tep_subnet_name) must be explicitly provided."
  }
}

check "subnet_cidr_when_creating" {
  assert {
    condition = !var.create_subnets_and_negs || (
      (var.mgmt_subnet_cidr != null && var.mgmt_subnet_cidr != "") &&
      (var.vsan_subnet_cidr != null && var.vsan_subnet_cidr != "") &&
      (var.vmotion_subnet_cidr != null && var.vmotion_subnet_cidr != "") &&
      (var.nsx_tep_subnet_cidr != null && var.nsx_tep_subnet_cidr != "") &&
      alltrue([
        for s in var.additional_dynamic_subnets : s.subnet_cidr != null && s.subnet_cidr != ""
      ])
    )
    error_message = "Subnet CIDR range (mgmt_subnet_cidr, vsan_subnet_cidr, vmotion_subnet_cidr, nsx_tep_subnet_cidr, and dynamic subnet_cidrs) must be provided whenever creating a new subnet."
  }
}
