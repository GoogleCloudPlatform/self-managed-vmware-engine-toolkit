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
# File: iam/main.tf
# Description: Provisions GCP IAM role bindings for the Terraform runner,
#              Jumpbox SSH user, and the Jumpbox script runner.
# ==============================================================================

# Configure the Google Cloud Provider with the specified project.
provider "google" {
  project = var.project_id
}

# ------------------------------------------------------------------------------
# Local Variables
# Format member strings to ensure valid GCP IAM prefixes.
# ------------------------------------------------------------------------------
locals {
  formatted_terraform_runner = startswith(var.terraform_runner, "user:") || startswith(var.terraform_runner, "serviceAccount:") ? var.terraform_runner : (
    endswith(var.terraform_runner, ".gserviceaccount.com") ? "serviceAccount:${var.terraform_runner}" : "user:${var.terraform_runner}"
  )

  formatted_jumpbox_ssh_user = startswith(var.jumpbox_ssh_user, "user:") || startswith(var.jumpbox_ssh_user, "serviceAccount:") ? var.jumpbox_ssh_user : (
    endswith(var.jumpbox_ssh_user, ".gserviceaccount.com") ? "serviceAccount:${var.jumpbox_ssh_user}" : "user:${var.jumpbox_ssh_user}"
  )

  formatted_jumpbox_script_runner = startswith(var.jumpbox_script_runner, "user:") ? var.jumpbox_script_runner : "user:${var.jumpbox_script_runner}"
}

# ------------------------------------------------------------------------------
# IAM Bindings for Terraform Runner Identity
# Roles granted:
#   - roles/compute.networkAdmin
#   - roles/compute.instanceAdmin.v1
#   - roles/compute.securityAdmin
#   - roles/iam.serviceAccountUser
# ------------------------------------------------------------------------------
resource "google_project_iam_member" "terraform_runner_roles" {
  for_each = toset([
    "roles/compute.networkAdmin",
    "roles/compute.instanceAdmin.v1",
    "roles/compute.securityAdmin",
    "roles/iam.serviceAccountUser"
  ])

  project = var.project_id
  role    = each.key
  member  = local.formatted_terraform_runner
}

# ------------------------------------------------------------------------------
# IAM Bindings for Jumpbox SSH User Identity
# Roles granted:
#   - roles/iap.tunnelResourceAccessor
#   - roles/compute.viewer
# ------------------------------------------------------------------------------
resource "google_project_iam_member" "jumpbox_ssh_user_roles" {
  for_each = toset([
    "roles/iap.tunnelResourceAccessor",
    "roles/compute.viewer"
  ])

  project = var.project_id
  role    = each.key
  member  = local.formatted_jumpbox_ssh_user
}

# ------------------------------------------------------------------------------
# IAM Bindings for Jumpbox Script Runner Identity
# Roles granted:
#   - roles/secretmanager.secretAccessor (to retrieve passwords from GCP Secret Manager)
#   - roles/compute.admin (to query/manage GCE bare metal host state)
#   - roles/resourcemanager.projectIamAdmin (to grant required permissions to Drift Manager P4SA)
# ------------------------------------------------------------------------------
resource "google_project_iam_member" "jumpbox_script_runner_roles" {
  for_each = toset([
    "roles/secretmanager.secretAccessor",
    "roles/compute.admin",
    "roles/resourcemanager.projectIamAdmin"
  ])

  project = var.project_id
  role    = each.key
  member  = local.formatted_jumpbox_script_runner
}

# ------------------------------------------------------------------------------
# IAM Bindings for GCVE Drift Manager Per-Product Per-Project Service Account (P4SA)
# Role granted:
#   - roles/compute.networkAdmin (to discover VPCs/subnets, resolve instances/forwarding rules,
#     and update Regional Backend Service leaders during IP move reconciliation)
# ------------------------------------------------------------------------------
data "google_project" "project" {
  project_id = var.project_id
}

resource "google_project_iam_member" "drift_manager_p4sa_roles" {
  project = var.project_id
  role    = "roles/compute.networkAdmin"
  member  = "serviceAccount:service-${data.google_project.project.number}@${var.drift_manager_producer_project_id}.iam.gserviceaccount.com"
}




