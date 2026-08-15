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
# File: iam/vars.tf
# Description: Input variables for the Standalone IAM Terraform module.
# ==============================================================================

variable "project_id" {
  type        = string
  description = "The target GCP Project ID."
}

variable "terraform_runner" {
  type        = string
  description = "The identity (user: or serviceAccount:) executing Terraform actions."

  validation {
    condition     = can(regex("^(user:|serviceAccount:)?[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.terraform_runner))
    error_message = "The terraform_runner variable must be a valid GCP human user ('user:<email>') or service account ('serviceAccount:<sa-email>')."
  }
}

variable "jumpbox_ssh_user" {
  type        = string
  description = "The identity (user: or serviceAccount:) SSHing into the jumpbox VM via IAP tunneling."

  validation {
    condition     = can(regex("^(user:|serviceAccount:)?[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.jumpbox_ssh_user))
    error_message = "The jumpbox_ssh_user variable must be a valid GCP human user ('user:<email>') or service account ('serviceAccount:<sa-email>')."
  }
}

variable "jumpbox_script_runner" {
  type        = string
  description = "The human user identity (e.g., 'user:admin@example.com') executing the SMVE Toolkit Python scripts on the jumpbox. Service accounts are not allowed."

  validation {
    condition     = can(regex("^(user:)?[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.jumpbox_script_runner)) && !startswith(var.jumpbox_script_runner, "serviceAccount:") && !endswith(var.jumpbox_script_runner, ".gserviceaccount.com")
    error_message = "The jumpbox_script_runner identity can only be a human user (e.g., 'user:operator@example.com' or 'operator@example.com'). Service accounts ('serviceAccount:...' or ending with '.gserviceaccount.com') are not permitted."
  }
}
