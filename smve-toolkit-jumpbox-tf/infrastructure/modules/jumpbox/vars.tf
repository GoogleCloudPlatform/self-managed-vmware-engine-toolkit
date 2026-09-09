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
# File: infrastructure/modules/jumpbox/vars.tf
# Description: Input variables for the Jumpbox submodule.
# ==============================================================================

variable "project_id" {
  type        = string
  description = "The target GCP Project ID."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "The 'project_id' must be 6 to 30 characters long, start with a lowercase letter, contain only lowercase letters, digits, and hyphens, and not end with a hyphen."
  }
}

variable "zone" {
  type        = string
  description = "The target GCP Zone for the VM deployment."

  validation {
    condition     = can(regex("^[a-z]+-[a-z0-9]+-[a-z0-9]+$", var.zone))
    error_message = "The 'zone' must be a valid GCP zone identifier format (e.g., 'us-central1-a', 'europe-west1-b')."
  }
}

variable "jumpbox_name" {
  type        = string
  description = "The name of the jumpbox GCE instance."

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.jumpbox_name))
    error_message = "The 'jumpbox_name' must be 1 to 63 characters long, begin with a lowercase letter, contain only lowercase letters, numbers, and hyphens, and end with a lowercase letter or number (RFC1035 compliant)."
  }
}

variable "subnet_name" {
  type        = string
  description = "The name or self_link of the subnetwork (in the VPC hosting the ESXi nodes) where the VM will be attached."
}

variable "service_account_email" {
  type        = string
  description = "The Service Account email attached to the VM."

  validation {
    condition     = can(regex("^[a-z0-9-]+@[a-z0-9-.]+\\.gserviceaccount\\.com$", var.service_account_email))
    error_message = "The 'service_account_email' must be a valid GCP Service Account email ending in '.gserviceaccount.com'."
  }
}

variable "machine_type" {
  type        = string
  description = "The machine type for the jumpbox VM instance."
  default     = "e2-micro"

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)+$", var.machine_type))
    error_message = "The 'machine_type' must be a valid GCP machine type identifier format (e.g., 'e2-micro', 'e2-medium', 'n2-standard-4', or 'custom-2-4096')."
  }
}

variable "boot_disk_size" {
  type        = number
  description = "The boot disk size in GB for the jumpbox VM instance."
  default     = 30

  validation {
    condition     = var.boot_disk_size >= 10 && var.boot_disk_size <= 65536
    error_message = "The 'boot_disk_size' must be an integer between 10 GB (minimum required for OS image) and 65536 GB."
  }
}

variable "boot_disk_type" {
  type        = string
  description = "The boot disk type (e.g. pd-balanced, pd-standard, pd-ssd) for the jumpbox VM instance."
  default     = "pd-balanced"

  validation {
    condition     = contains(["pd-standard", "pd-balanced", "pd-ssd", "pd-extreme"], var.boot_disk_type)
    error_message = "The 'boot_disk_type' must be one of: 'pd-standard', 'pd-balanced', 'pd-ssd', 'pd-extreme'."
  }
}

variable "boot_disk_image" {
  type        = string
  description = "The OS boot disk image family or specific image."
  default     = "debian-cloud/debian-12"
}

variable "region" {
  type        = string
  description = "The GCP region for looking up regional resources (e.g., reserved internal IP addresses). If omitted, derived from zone."
  default     = ""
}

variable "internal_ip" {
  type        = string
  description = "Static internal IPv4 address (e.g., '10.10.0.5') or reserved internal IP address name/URI (e.g., 'my-reserved-ip') to assign to the jumpbox VM. If omitted or empty, GCP assigns an ephemeral/dynamic internal IP."
  default     = ""

  validation {
    condition     = var.internal_ip == "" || can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", var.internal_ip)) || can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.internal_ip)) || can(regex("^projects/.+/regions/.+/addresses/.+$", var.internal_ip))
    error_message = "The 'internal_ip' must be an empty string, a valid IPv4 address (e.g., '10.10.0.5'), an RFC1035-compliant reserved address name, or a full address resource URI."
  }
}
