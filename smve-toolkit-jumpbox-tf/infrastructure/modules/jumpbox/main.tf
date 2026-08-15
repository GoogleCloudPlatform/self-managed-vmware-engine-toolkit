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
# File: infrastructure/modules/jumpbox/main.tf
# Description: Provisions the Jumpbox GCE instance without a public IP,
#              attached to the designated Service Account, with OS Login enabled.
# ==============================================================================

# ------------------------------------------------------------------------------
# Local Variables
# Resolves whether `internal_ip` is an IPv4 literal, reserved address name/URI, or empty.
# ------------------------------------------------------------------------------
locals {
  has_internal_ip = var.internal_ip != ""

  # Check if internal_ip is a literal IPv4 address (e.g. "10.10.0.5")
  is_ipv4 = local.has_internal_ip && can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.internal_ip))

  # If provided and not a literal IPv4 address, treat it as a reserved address name or URI
  is_reserved_address = local.has_internal_ip && !local.is_ipv4

  # Extract clean resource name if a full URI / self_link was provided
  reserved_address_name = local.is_reserved_address ? element(reverse(split("/", var.internal_ip)), 0) : ""

  # Determine region for looking up regional reserved compute address
  effective_region = var.region != "" ? var.region : join("-", slice(split("-", var.zone), 0, 2))

  # Resolve the effective IP string to assign to the instance
  effective_network_ip = local.is_ipv4 ? var.internal_ip : (
    local.is_reserved_address ? data.google_compute_address.reserved_internal_ip[0].address : null
  )
}

# ------------------------------------------------------------------------------
# Data Source: Look up Reserved Static Internal IP (Conditional)
# Used when `var.internal_ip` is specified as a reserved IP address name or self_link.
# ------------------------------------------------------------------------------
data "google_compute_address" "reserved_internal_ip" {
  count   = local.is_reserved_address ? 1 : 0
  name    = local.reserved_address_name
  project = var.project_id
  region  = local.effective_region
}

resource "google_compute_instance" "jumpbox" {
  name         = var.jumpbox_name
  machine_type = var.machine_type
  zone         = var.zone
  project      = var.project_id

  # Boot Disk Configuration
  boot_disk {
    initialize_params {
      image = var.boot_disk_image
      size  = var.boot_disk_size
      type  = var.boot_disk_type
    }
  }

  # Network Interface Configuration (Private IP ONLY - NO Public IP)
  network_interface {
    subnetwork         = var.subnet_name
    subnetwork_project = var.project_id
    network_ip         = local.effective_network_ip

    # Omitting `access_config` ensures that NO public IP is assigned to the VM.
    # Access is strictly controlled via Google Cloud IAP Tunneling.
  }

  # Metadata Configuration: Enables OS Login for IAM-authenticated SSH access
  metadata = {
    enable-oslogin = "TRUE"
  }

  # Service Account Attachment (Configured Service Account)
  service_account {
    email  = var.service_account_email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  # Shielded VM Configuration (Recommended Security Baseline)
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # Allow stopping instance for updates to machine_type, disk, etc.
  allow_stopping_for_update = true
}
