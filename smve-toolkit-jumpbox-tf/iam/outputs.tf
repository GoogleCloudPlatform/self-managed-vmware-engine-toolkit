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
# File: iam/outputs.tf
# Description: Output values for the Standalone IAM Terraform module.
# ==============================================================================

output "terraform_runner_iam_roles_granted" {
  description = "List of IAM roles granted to the Terraform runner identity."
  value       = [for b in google_project_iam_member.terraform_runner_roles : b.role]
}

output "jumpbox_ssh_user_iam_roles_granted" {
  description = "List of IAM roles granted to the Jumpbox SSH user identity."
  value       = [for b in google_project_iam_member.jumpbox_ssh_user_roles : b.role]
}

output "jumpbox_script_runner_iam_roles_granted" {
  description = "List of IAM roles granted to the Jumpbox script runner identity."
  value       = [for b in google_project_iam_member.jumpbox_script_runner_roles : b.role]
}
