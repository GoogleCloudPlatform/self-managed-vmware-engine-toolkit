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
      source  = "hashicorp/google"
      version = ">= 4.80.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9.0"
    }
  }
}

locals {
  project_id = var.project_id
  region     = var.region
  zone       = var.zone
}

provider "google" {
  project = local.project_id
  region  = local.region
  zone    = local.zone
}

# ==============================================================================
# 1. VPC Module: Network Creation, Firewall Rules, DNS Zones & Policy
# ==============================================================================

module "vpc" {
  source = "./modules/vpc"

  project_id           = var.project_id
  region               = var.region
  resource_name_prefix = var.resource_name_prefix
  vpc_network          = var.vpc_network
  create_vpc           = var.create_vpc
  routing_mode         = var.routing_mode
  create_firewalls     = var.create_firewalls

  # Cloud DNS Zones, GCP Subnet & Inbound Policy
  setup_cloud_dns     = var.setup_cloud_dns
  create_gcp_subnet   = var.create_gcp_subnet
  gcp_subnet_name     = var.gcp_subnet_name
  gcp_subnet_cidr     = var.gcp_subnet_cidr
  create_dns_zones    = var.create_dns_zones
  dns_policy_name     = var.dns_policy_name
  domain_name         = var.domain_name
  reverse_domain_name = var.reverse_domain_name
  forward_zone_name   = var.forward_zone_name
  reverse_zone_name   = var.reverse_zone_name
}

# ==============================================================================
# 2. Subnets Module: L2 Broadcast Subnetworks & Zonal NEGs
# ==============================================================================

module "subnets" {
  source = "./modules/subnets"


  project_id              = var.project_id
  region                  = var.region
  zone                    = var.zone
  resource_name_prefix    = var.resource_name_prefix
  vpc_network             = module.vpc.vpc_network_name
  create_subnets_and_negs = var.create_subnets_and_negs

  # Management Subnet & NEG
  mgmt_subnet_name = var.mgmt_subnet_name
  mgmt_subnet_cidr = var.mgmt_subnet_cidr
  mgmt_neg_name    = var.mgmt_neg_name

  # vSAN Subnet
  vsan_subnet_name = var.vsan_subnet_name
  vsan_subnet_cidr = var.vsan_subnet_cidr

  # vMotion Subnet
  vmotion_subnet_name = var.vmotion_subnet_name
  vmotion_subnet_cidr = var.vmotion_subnet_cidr

  # NSX TEP Subnet & NEG
  nsx_tep_subnet_name = var.nsx_tep_subnet_name
  nsx_tep_subnet_cidr = var.nsx_tep_subnet_cidr
  nsx_neg_name        = var.nsx_neg_name

  # Additional Dynamic Subnets
  additional_dynamic_subnets = var.additional_dynamic_subnets

  depends_on = [module.vpc]
}

# ==============================================================================
# 3. Hosts Module: Compute Instances, Placement Policy, IP Allocation, NEG Attachments, DNS Records
# ==============================================================================

module "hosts" {
  source = "./modules/hosts"


  project_id           = var.project_id
  region               = var.region
  zone                 = var.zone
  resource_name_prefix = var.resource_name_prefix
  deployment_mode      = var.deployment_mode
  number_of_nodes      = var.number_of_nodes
  machine_type         = var.machine_type
  # Full ESXi image resource URI must be provided (e.g. 'projects/<project>/global/images/<image-name>')
  esxi_image              = var.esxi_image
  node_names              = var.node_names
  domain_name             = var.domain_name
  deletion_protection     = var.deletion_protection
  create_placement_policy = var.create_placement_policy
  placement_policy_name   = var.placement_policy_name
  availability_count      = var.availability_count
  availability_domains    = var.availability_domains

  # Management NIC
  mgmt_subnet_name     = module.subnets.mgmt_subnet_name
  mgmt_subnet_cidr     = var.mgmt_subnet_cidr
  mgmt_neg_name        = module.subnets.mgmt_neg_name
  mgmt_ip_address_type = var.mgmt_nic_ip_address_type
  mgmt_ip_values       = var.mgmt_nic_ip_values

  # vSAN NIC
  vsan_subnet_name     = module.subnets.vsan_subnet_name
  vsan_subnet_cidr     = var.vsan_subnet_cidr
  vsan_vlan_id         = var.vsan_vlan_id
  vsan_ip_address_type = var.vsan_ip_address_type
  vsan_ip_values       = var.vsan_ip_values

  # vMotion NIC
  vmotion_subnet_name     = module.subnets.vmotion_subnet_name
  vmotion_subnet_cidr     = var.vmotion_subnet_cidr
  vmotion_vlan_id         = var.vmotion_vlan_id
  vmotion_ip_address_type = var.vmotion_ip_address_type
  vmotion_ip_values       = var.vmotion_ip_values

  # NSX TEP NIC
  nsx_tep_subnet_name     = module.subnets.nsx_tep_subnet_name
  nsx_tep_subnet_cidr     = var.nsx_tep_subnet_cidr
  nsx_tep_vlan_id         = var.nsx_tep_vlan_id
  nsx_tep_ip_address_type = var.nsx_tep_ip_address_type
  nsx_tep_ip_values       = var.nsx_tep_ip_values
  nsx_neg_name            = module.subnets.nsx_neg_name

  # Dynamic NICs
  additional_dynamic_nics    = var.additional_dynamic_nics
  additional_dynamic_subnets = var.additional_dynamic_subnets

  # Host Cloud DNS Records
  setup_cloud_dns     = var.setup_cloud_dns
  forward_zone_name   = module.vpc.forward_zone_name
  reverse_zone_name   = module.vpc.reverse_zone_name
  reverse_domain_name = var.reverse_domain_name
  dns_ttl             = var.dns_ttl

  depends_on = [module.subnets]
}

# ==============================================================================
# 4. Appliances Module: Management & NSX Regional ILBs, Forwarding Rules, DNS Records
# ==============================================================================

module "appliances" {
  source = "./modules/appliances"

  project_id           = var.project_id
  region               = var.region
  zone                 = var.zone
  resource_name_prefix = var.resource_name_prefix
  vpc_network          = module.vpc.vpc_network_name
  mgmt_subnet_name     = module.subnets.mgmt_subnet_name
  nsx_tep_subnet_name  = module.subnets.nsx_tep_subnet_name
  mgmt_subnet_cidr     = var.mgmt_subnet_cidr
  nsx_tep_subnet_cidr  = var.nsx_tep_subnet_cidr
  mgmt_neg_self_link   = module.subnets.mgmt_neg_self_link
  nsx_neg_self_link    = module.subnets.nsx_neg_self_link
  leader_instance      = length(module.hosts.node_names) > 0 ? module.hosts.node_names[0] : null
  mgmt_ip_address_type = var.mgmt_ip_address_type
  mgmt_ip_values       = var.mgmt_ip_values
  nsx_ip_address_type  = var.nsx_ip_address_type
  nsx_ip_values        = var.nsx_ip_values
  domain_name          = var.domain_name
  reverse_domain_name  = var.reverse_domain_name
  forward_zone_name    = module.vpc.forward_zone_name
  reverse_zone_name    = module.vpc.reverse_zone_name
  dns_ttl              = var.dns_ttl
  setup_cloud_dns      = var.setup_cloud_dns

  depends_on = [module.hosts]
}
