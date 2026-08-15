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
# File: infrastructure/modules/network/vars.tf
# Description: Input variables for the Network submodule.
# ==============================================================================

variable "project_id" {
  type        = string
  description = "The target GCP Project ID."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "The 'project_id' must be 6 to 30 characters long, start with a lowercase letter, contain only lowercase letters, digits, and hyphens, and not end with a hyphen."
  }
}

variable "region" {
  type        = string
  description = "The target GCP Region for the subnet."

  validation {
    condition     = can(regex("^[a-z]+-[a-z0-9]+$", var.region))
    error_message = "The 'region' must be a valid GCP region string (e.g., 'us-central1', 'europe-west1')."
  }
}

variable "vpc_name" {
  type        = string
  description = "The VPC network name in which the subnet exists or will be created."
}

variable "subnet_name" {
  type        = string
  default     = "smve-toolkit-jumpbox-subnet"
  description = "The name of the subnet to create or fetch."

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$", var.subnet_name))
    error_message = "The 'subnet_name' must be 1 to 63 characters long, begin with a lowercase letter, contain only lowercase letters, numbers, and hyphens, and end with a lowercase letter or number (RFC1035 compliant)."
  }
}

variable "create_subnet" {
  type        = bool
  default     = true
  description = "Whether to create a new subnet (true) or fetch an existing one (false)."
}

variable "subnet_cidr" {
  type        = string
  description = "The IPv4 CIDR range for the new subnet (min /29). Required if create_subnet = true."
}

variable "service_account_email" {
  type        = string
  description = "The Service Account email used as the target for the IAP firewall rule."

  validation {
    condition     = can(regex("^[a-z0-9-]+@[a-z0-9-.]+\\.gserviceaccount\\.com$", var.service_account_email))
    error_message = "The 'service_account_email' must be a valid GCP Service Account email ending in '.gserviceaccount.com'."
  }
}

variable "enable_internet" {
  type        = bool
  default     = true
  description = "Whether to create Cloud Router, Cloud NAT, and default internet route for outbound internet access."
}
