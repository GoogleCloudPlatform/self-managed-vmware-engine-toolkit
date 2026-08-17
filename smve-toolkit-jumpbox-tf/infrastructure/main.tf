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
# File: infrastructure/main.tf
# Description: Main entry point for SMVE Toolkit Jumpbox Terraform module.
#              Orchestrates network/subnet creation, IAP firewall rules,
#              Cloud Router, Cloud NAT, and jumpbox GCE instance deployment.
# ==============================================================================

# Configure the Google Cloud Provider with the specified project and region.
provider "google" {
  project = var.project_id
  region  = var.region
}

# ------------------------------------------------------------------------------
# Data Source: Compute Engine Default Service Account
# Automatically fetches the default Compute Engine SA (<project-number>-compute@developer.gserviceaccount.com)
# used as fallback if var.service_account_email is left empty ("").
# ------------------------------------------------------------------------------
data "google_compute_default_service_account" "default" {
  project = var.project_id
}

# ------------------------------------------------------------------------------
# Local Variables
# Resolve effective zone and service account defaults.
# ------------------------------------------------------------------------------
locals {
  # If zone is not explicitly provided, default to zone 'a' in the specified region.
  effective_zone = var.zone != "" ? var.zone : "${var.region}-a"

  # If service_account_email is not explicitly provided, default to the Compute Engine default SA.
  effective_service_account = var.service_account_email != "" ? var.service_account_email : data.google_compute_default_service_account.default.email
}

# ------------------------------------------------------------------------------
# Module 1: Network & Firewall Setup
# Manages conditional subnetwork provisioning (creation or fetching existing)
# and creates the requisite ingress firewall rule allowing IAP SSH access
# scoped specifically to the Jumpbox service account.
# It also enables internet access via NAT by creating a Cloud NAT and a Cloud Router.
# ------------------------------------------------------------------------------
module "network" {
  source = "./modules/network"

  project_id            = var.project_id
  region                = var.region
  vpc_name              = var.vpc_name
  subnet_name           = var.subnet_name
  create_subnet         = var.create_subnet
  subnet_cidr           = var.subnet_cidr
  service_account_email = local.effective_service_account
  enable_internet       = var.enable_internet
}

# ------------------------------------------------------------------------------
# Module 2: Jumpbox Instance Provisioning
# Creates a compute engine instance without a public IP, attached to the
# designated Service Account, and configured with OS Login for secure IAP SSH access.
# ------------------------------------------------------------------------------
module "jumpbox" {
  source = "./modules/jumpbox"

  project_id            = var.project_id
  region                = var.region
  zone                  = local.effective_zone
  jumpbox_name          = var.jumpbox_name
  subnet_name           = module.network.subnet_name
  service_account_email = local.effective_service_account
  machine_type          = var.machine_type
  boot_disk_size        = var.boot_disk_size
  boot_disk_type        = var.boot_disk_type
  boot_disk_image       = var.boot_disk_image
  internal_ip           = var.jumpbox_internal_ip

  # Ensure network and firewall infrastructure exist before provisioning VM
  depends_on = [module.network]
}
