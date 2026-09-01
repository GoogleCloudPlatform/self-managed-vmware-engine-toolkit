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

locals {
  formatted_domain = length(regexall("\\.$", var.domain_name)) > 0 ? var.domain_name : "${var.domain_name}."

  # All active subnets in the VPC
  all_vpc_subnet_names = compact(concat([
    module.subnets.mgmt_subnet_name,
    module.subnets.vsan_subnet_name,
    module.subnets.vmotion_subnet_name,
    module.subnets.nsx_tep_subnet_name
  ], [for s in values(module.subnets.dynamic_subnets) : s.name]))

  all_vpc_subnet_self_links = compact(concat([
    module.subnets.mgmt_subnet_self_link,
    module.subnets.vsan_subnet_self_link,
    module.subnets.vmotion_subnet_self_link,
    module.subnets.nsx_tep_subnet_self_link
  ], [for s in values(module.subnets.dynamic_subnets) : s.self_link]))

  # All active subnet CIDRs in the VPC
  all_vpc_subnet_cidrs = compact(concat([
    module.subnets.mgmt_subnet_cidr,
    module.subnets.vsan_subnet_cidr,
    module.subnets.vmotion_subnet_cidr,
    module.subnets.nsx_tep_subnet_cidr
  ], [for s in values(module.subnets.dynamic_subnets) : s.cidr]))

  # Cloud DNS Inbound Forwarding Reserved IPs (filtered to only include IPs falling within the cluster VPC subnets)
  dns_inbound_ips = distinct([
    for ip in module.vpc.dns_reserved_ips : ip
    if length(local.all_vpc_subnet_cidrs) == 0 || anytrue([
      for cidr in local.all_vpc_subnet_cidrs :
      cidrhost(format("%s/%s", ip, split("/", cidr)[1]), 0) == cidrhost(cidr, 0)
    ])
  ])

  # Management subnet Cloud DNS Inbound Forwarding Reserved IP
  mgmt_dns_reserved_ips = [
    for ip in module.vpc.dns_reserved_ips : ip
    if(module.subnets.mgmt_subnet_cidr != null && module.subnets.mgmt_subnet_cidr != "") && (
      cidrhost(format("%s/%s", ip, split("/", module.subnets.mgmt_subnet_cidr)[1]), 0) == cidrhost(module.subnets.mgmt_subnet_cidr, 0)
    )
  ]
  mgmt_dns_reserved_ip = length(local.mgmt_dns_reserved_ips) > 0 ? local.mgmt_dns_reserved_ips[0] : null

  # Host ESXi nodes FQDN and IP mapping
  node_hosts_mapping = {
    for i, name in module.hosts.node_names : name => {
      fqdn = "${name}.${local.formatted_domain}"
      ip   = module.hosts.node_primary_ips[i]
      type = "esxi_host"
    }
  }

  # VCF Management appliances FQDN and IP mapping
  mgmt_appliances_mapping = {
    for name, ip in module.appliances.management_forwarding_rule_ips : name => {
      fqdn = "${name}.${local.formatted_domain}"
      ip   = ip
      type = "management_appliance"
    }
  }

  # NSX Datapath Edge appliances FQDN and IP mapping
  nsx_datapath_mapping = {
    for name, ip in module.appliances.nsx_datapath_forwarding_rule_ips : name => {
      fqdn = "${name}.${local.formatted_domain}"
      ip   = ip
      type = "nsx_datapath_edge"
    }
  }
}

# ==============================================================================
# 1. GCP RESOURCE SELF-LINKS
# ==============================================================================

output "gcp_resources_self_links" {
  value = {
    # VPC Network and L2 Subnetworks
    vpc = {
      network         = module.vpc.vpc_network_self_link
      primary_subnet  = module.subnets.mgmt_subnet_self_link
      vsan_subnet     = module.subnets.vsan_subnet_self_link
      vmotion_subnet  = module.subnets.vmotion_subnet_self_link
      nsx_tep_subnet  = module.subnets.nsx_tep_subnet_self_link
      dynamic_subnets = { for k, v in module.subnets.dynamic_subnets : k => v.self_link }
    }

    # Bare-Metal Compute Nodes & Zonal NEGs
    nodes = {
      instances        = module.hosts.node_self_links
      placement_policy = module.hosts.placement_policy_self_link
      primary_neg      = module.subnets.mgmt_neg_self_link
      nsx_neg          = module.subnets.nsx_neg_self_link
      reserved_ips = {
        primary = module.hosts.primary_reserved_addresses
        vsan    = module.hosts.vsan_reserved_addresses
        vmotion = module.hosts.vmotion_reserved_addresses
        nsx_tep = module.hosts.nsx_tep_reserved_addresses
        dynamic = module.hosts.dynamic_reserved_addresses
      }
    }

    # Regional Load Balanced VCF Management & NSX Datapath Appliances
    appliances = {
      management_backend_services   = module.appliances.management_backend_services
      management_forwarding_rules   = module.appliances.management_forwarding_rules
      management_reserved_ips       = module.appliances.management_reserved_addresses
      nsx_datapath_backend_services = module.appliances.nsx_datapath_backend_services
      nsx_datapath_forwarding_rules = module.appliances.nsx_datapath_forwarding_rules
      nsx_datapath_reserved_ips     = module.appliances.nsx_reserved_addresses
    }

    # VPC Ingress Firewall Rules
    firewalls = var.create_firewalls ? {
      allow_all_ingress = module.vpc.firewall_rule_allow_all_self_link
    } : null

    # Cloud DNS Managed Zones & Inbound Policy (DO NOT USE THE DNS RESERVED IPs IN THE IP POOL INPUT FOR DEPLOYING MANAGEMENT OR WORKLOAD DOMAIN CLUSTERS)
    dns = {
      forward_zone     = module.vpc.forward_zone_name != null ? "https://www.googleapis.com/dns/v1/projects/${local.project_id}/managedZones/${module.vpc.forward_zone_name}" : null
      reverse_zone     = module.vpc.reverse_zone_name != null ? "https://www.googleapis.com/dns/v1/projects/${local.project_id}/managedZones/${module.vpc.reverse_zone_name}" : null
      dns_policy       = module.vpc.dns_policy_self_link
      dns_reserved_ips = length(local.dns_inbound_ips) > 0 ? format("[%s]", join(", ", local.dns_inbound_ips)) : null
    }
  }
  description = "Self links of all provisioned and referenced GCP resources organized in a modular structure"
}

# ==============================================================================
# 2. HOST AND APPLIANCE TO FQDN & IP MAPPINGS
# ==============================================================================

output "host_and_appliance_mappings" {
  value       = merge(local.node_hosts_mapping, local.mgmt_appliances_mapping, local.nsx_datapath_mapping)
  description = "Comprehensive mapping of all bare-metal ESXi hosts and VCF/NSX appliances to their FQDN and assigned IP address"
}

# ==============================================================================
# 3. SUBNETWORK CIDRS AND HOST IP MAPS
# ==============================================================================

output "cluster_network_host_ips" {
  value = {
    primary = {
      subnet_name = module.subnets.mgmt_subnet_name
      subnet_cidr = module.subnets.mgmt_subnet_cidr
      host_ips = {
        for i, name in module.hosts.node_names : name => module.hosts.node_primary_ips[i]
      }
    }
    vsan = {
      subnet_name = module.subnets.vsan_subnet_name
      subnet_cidr = module.subnets.vsan_subnet_cidr
      vlan_id     = var.vsan_vlan_id
      host_ips = {
        for i, name in module.hosts.node_names : name => module.hosts.node_vsan_ips[i]
      }
    }
    vmotion = {
      subnet_name = module.subnets.vmotion_subnet_name
      subnet_cidr = module.subnets.vmotion_subnet_cidr
      vlan_id     = var.vmotion_vlan_id
      host_ips = {
        for i, name in module.hosts.node_names : name => module.hosts.node_vmotion_ips[i]
      }
    }
    nsx_tep = {
      subnet_name = module.subnets.nsx_tep_subnet_name
      subnet_cidr = module.subnets.nsx_tep_subnet_cidr
      vlan_id     = var.nsx_tep_vlan_id
      host_ips = {
        for i, name in module.hosts.node_names : name => module.hosts.node_nsx_tep_ips[i]
      }
    }
    dynamic_nics = {
      for idx, nic in var.additional_dynamic_nics : nic.name => {
        subnet_name = nic.subnet_name
        subnet_cidr = lookup(module.subnets.dynamic_subnet_cidrs, nic.subnet_name, null)
        vlan_id     = nic.vlan_id
        host_ips = {
          for i, name in module.hosts.node_names : name => module.hosts.node_dynamic_nic_ips[nic.name][i]
        }
      }
    }
  }
  description = "Subnetwork CIDRs and host name to host IP mappings for each cluster network (Primary, vSAN, vMotion, NSX TEP, and dynamic NICs)"
}

# ==============================================================================
# 4. PYTHON AUTOMATION SCRIPT INPUT CONFIGURATION
# ==============================================================================

output "python_scripts_input_config" {
  value = {
    # GCP Project ID
    project = var.project_id

    # GCP Compute Engine Zone
    zone = var.zone

    # List of all provisioned bare-metal ESXi host instance names
    gce_nodes = module.hosts.node_names

    # Secret Manager secret resource path containing the ESXi root password
    esxi_root_password_secret = "<user_should_input>"

    # VCF Deployment and initialization parameters
    vcf_deployment_config = {
      # Target bare-metal instance name to host the initial deployment workloads
      target_gce_node = length(module.hosts.node_names) > 0 ? module.hosts.node_names[0] : "<user_should_input>"

      # Subnet CIDR for the Offline Depot PSC endpoint
      offline_depot_subnet_cidr = "<user_should_input>"

      # Secret Manager secret resource path containing the VCF appliance root password
      vcf_appliance_root_password_secret = "<user_should_input>"

      # Secret Manager secret resource path containing the VCF appliance local user password
      vcf_appliance_local_user_password_secret = "<user_should_input>"

      # Forwarding rule resource for SDDC Manager / VCF Installer
      vcf_installer_ip_source = lookup(module.appliances.management_forwarding_rules, "sddc-manager", lookup(module.appliances.management_forwarding_rules, "vcf", lookup(module.appliances.management_forwarding_rules, "cloudproxy", null)))

      # Fully qualified domain name of the SDDC Manager (VCF Installer)
      vcf_installer_fqdn = "sddc-manager.${local.formatted_domain}"

      # Cloud DNS Inbound Reserved IP for the management subnet
      dns_server = local.mgmt_dns_reserved_ip
    }
  }
  description = "Input configuration schema and populated values for Python post-deployment automation scripts"
}

# ==============================================================================
# 5. NEG ATTACHMENT COMMANDS & STATUS
# ==============================================================================

output "neg_attachment_commands" {
  value       = module.hosts.neg_attachment_commands
  description = "gcloud CLI commands to attach newly added ESXi host instances to Management and NSX NEGs in 'node_addition' mode, or confirmation that NEGs are already attached in 'cluster_creation' and 'appliance_addition' modes"
}
