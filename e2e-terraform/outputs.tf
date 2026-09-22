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
  domain           = trimsuffix(var.domain_name, ".")

  # All active subnets in the VPC
  all_vpc_subnet_names = compact(concat([
    module.vpc.gcp_subnet_name,
    module.subnets.mgmt_subnet_name,
    module.subnets.vsan_subnet_name,
    module.subnets.vmotion_subnet_name,
    module.subnets.nsx_tep_subnet_name
  ], [for s in values(module.subnets.dynamic_subnets) : s.name]))

  all_vpc_subnet_self_links = compact(concat([
    module.vpc.gcp_subnet_self_link,
    module.subnets.mgmt_subnet_self_link,
    module.subnets.vsan_subnet_self_link,
    module.subnets.vmotion_subnet_self_link,
    module.subnets.nsx_tep_subnet_self_link
  ], [for s in values(module.subnets.dynamic_subnets) : s.self_link]))

  # All active subnet CIDRs in the VPC
  all_vpc_subnet_cidrs = compact(concat([
    module.vpc.gcp_subnet_cidr,
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

  # GCP subnet Cloud DNS Inbound Forwarding Reserved IP
  gcp_dns_reserved_ips = [
    for ip in module.vpc.dns_reserved_ips : ip
    if(module.vpc.gcp_subnet_cidr != null && module.vpc.gcp_subnet_cidr != "") && (
      cidrhost(format("%s/%s", ip, split("/", module.vpc.gcp_subnet_cidr)[1]), 0) == cidrhost(module.vpc.gcp_subnet_cidr, 0)
    )
  ]
  gcp_dns_reserved_ip = length(local.gcp_dns_reserved_ips) > 0 ? local.gcp_dns_reserved_ips[0] : null

  # VSP IP range calculation extracted dynamically from VSRT Forwarding Rule IPs
  vsrt_fr_ips = [
    for name, ip in module.appliances.management_forwarding_rule_ips : ip
    if can(regex("vsrt", name)) && ip != null && ip != ""
  ]

  vsrt_ip_int_map = {
    for ip in local.vsrt_fr_ips : (
      parseint(split(".", ip)[0], 10) * 16777216 +
      parseint(split(".", ip)[1], 10) * 65536 +
      parseint(split(".", ip)[2], 10) * 256 +
      parseint(split(".", ip)[3], 10)
    ) => ip
    if can(regex("^(?:[0-9]{1,3}\\.){3}[0-9]{1,3}$", ip))
  }

  vsrt_ip_ints = [
    for k, _ in local.vsrt_ip_int_map : parseint(k, 10)
  ]

  # Fallback to var.mgmt_ip_values if vsrt is specified directly as an IP range string ("start-end")
  vsrt_range_raw   = lookup(var.mgmt_ip_values, "vsrt", "")
  vsrt_range_parts = length(split("-", local.vsrt_range_raw)) == 2 ? split("-", local.vsrt_range_raw) : []

  vsp_start_ip = length(local.vsrt_ip_ints) > 0 ? local.vsrt_ip_int_map[tostring(min(local.vsrt_ip_ints...))] : (
    length(local.vsrt_range_parts) == 2 ? trimspace(local.vsrt_range_parts[0]) : null
  )

  vsp_end_ip = length(local.vsrt_ip_ints) > 0 ? local.vsrt_ip_int_map[tostring(max(local.vsrt_ip_ints...))] : (
    length(local.vsrt_range_parts) == 2 ? trimspace(local.vsrt_range_parts[1]) : null
  )
}

# ==============================================================================
# 1. GCP RESOURCE SELF-LINKS
# ==============================================================================

output "gcp_resources_self_links" {
  value = {
    # VPC Network and L2 Subnetworks
    vpc = {
      network         = module.vpc.vpc_network_self_link
      gcp_subnet      = module.vpc.gcp_subnet_self_link
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
# 2. NEG ATTACHMENT COMMANDS & STATUS
# ==============================================================================

output "neg_attachment_commands" {
  value       = module.hosts.neg_attachment_commands
  description = "gcloud CLI commands to attach newly added ESXi host instances to Management and NSX NEGs in 'node_addition' mode, or confirmation that NEGs are already attached in 'cluster_creation' and 'appliance_addition' modes"
}

# ==============================================================================
# 3. PYTHON AUTOMATION SCRIPT INPUT CONFIGURATION
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

      # Subnet CIDR for the dedicated Offline Depot PSC endpoint (e.g. /29 subnet). Must not overlap with or reuse any existing subnets in the VPC
      offline_depot_subnet_cidr = "<user_should_input>"

      # Secret Manager secret resource path containing the VCF appliance root password
      vcf_appliance_root_password_secret = "<user_should_input>"

      # Secret Manager secret resource path containing the VCF appliance local user password
      vcf_appliance_local_user_password_secret = "<user_should_input>"

      # Forwarding rule resource for SDDC Manager / VCF Installer
      vcf_installer_ip_source = lookup(module.appliances.management_forwarding_rules, "sddcm", null) != null ? replace(module.appliances.management_forwarding_rules["sddcm"], "https://www.googleapis.com/compute/v1/", "") : null

      # Fully qualified domain name of the SDDC Manager (VCF Installer) without trailing dot
      vcf_installer_fqdn = "sddcm.${local.domain}"

      # Cloud DNS Inbound Reserved IP for the GCP subnet (populated when setup_cloud_dns is true; set to '<user_should_input>' when setup_cloud_dns is false)
      dns_server = var.setup_cloud_dns ? local.gcp_dns_reserved_ip : "<user_should_input>"
    }
  }
  description = "Input configuration schema and populated values for Python post-deployment automation scripts"
}

# ==============================================================================
# 4. MANAGEMENT DOMAIN DEPLOYMENT INPUT CONFIGURATION
# ==============================================================================

output "management_domain_deployment_input_config" {
  value = {
    version         = can(regex("esxi-([0-9a-zA-Z]+)-([0-9a-zA-Z]+)-([0-9a-zA-Z]+)", var.esxi_image)) ? join(".", regex("esxi-([0-9a-zA-Z]+)-([0-9a-zA-Z]+)-([0-9a-zA-Z]+)", var.esxi_image)) : "<user_should_input>"
    vcfInstanceName = "vcf1"
    sddcId          = "mgmt-domain"
    ceipEnabled     = false
    workflowType    = "VCF"

    dnsSpec = {
      subdomain   = local.domain
      nameservers = [
        var.setup_cloud_dns ? local.gcp_dns_reserved_ip : "<user_should_input>"
      ]
    }

    ntpServers = [
      "ntp.${local.domain}"
    ]

    hostSpecs = [
      for name in module.hosts.node_names : {
        hostname      = name
        sslThumbprint = "<user_should_input>"
        credentials = {
          username = "root"
          password = "Default123!Default123!"
        }
      }
    ]

    vcenterSpec = {
      vcenterHostname       = "vc01.${local.domain}"
      vmSize                = "medium"
      storageSize           = "lstorage"
      ssoDomain             = "gve.local"
      useExistingDeployment = false
    }

    clusterSpec = {
      datacenterName = "mgmt-domain-dc01"
      clusterName    = "mgmt-domain-cl01"
    }

    dvsSpecs = [
      {
        dvsName = "mgmt-domain-cl01-vds01"
        vmnicsToUplinks = [
          {
            id     = "vmnic0"
            uplink = "uplink0"
          }
        ]
        networks = [
          "MANAGEMENT",
          "VM_MANAGEMENT",
          "VMOTION",
          "VSAN"
        ]
        mtu = 8700
        nsxTeamings = [
          {
            policy = "LOADBALANCE_SRCID"
            activeUplinks = [
              "uplink0"
            ]
          }
        ]
        nsxtSwitchConfig = {
          transportZones = [
            {
              name          = "overlay-tz-mgmt-nsxt"
              transportType = "OVERLAY"
            }
          ]
          hostSwitchOperationalMode = "STANDARD"
        }
      }
    ]

    nsxtSpec = {
      vipFqdn = "nsx01.${local.domain}"
      nsxtManagers = [
        {
          hostname = "nsx02.${local.domain}"
        },
        {
          hostname = "nsx03.${local.domain}"
        },
        {
          hostname = "nsx04.${local.domain}"
        }
      ]
      transportVlanId         = var.nsx_tep_vlan_id
      nsxtManagerSize         = "medium"
      ipAddressPoolSpec = {
        name        = "mgmt-domain-cl01-tep01"
        description = "mgmt-domain-cl01-tep01 descr"
        subnets = [
          {
            cidr    = module.subnets.nsx_tep_subnet_cidr
            gateway = module.subnets.nsx_tep_subnet_cidr != null ? cidrhost(module.subnets.nsx_tep_subnet_cidr, 1) : null
            ipAddressPoolRanges = [
              {
                start = module.subnets.nsx_tep_subnet_cidr != null ? cidrhost(module.subnets.nsx_tep_subnet_cidr, 3) : null
                end   = module.subnets.nsx_tep_subnet_cidr != null ? cidrhost(module.subnets.nsx_tep_subnet_cidr, 100) : null
              }
            ]
          }
        ]
      }
      useExistingDeployment = false
    }

    networkSpecs = [
      {
        networkType  = "MANAGEMENT"
        subnet       = module.subnets.mgmt_subnet_cidr
        gateway      = module.subnets.mgmt_subnet_cidr != null ? cidrhost(module.subnets.mgmt_subnet_cidr, 1) : null
        vlanId       = 0
        mtu          = 8700
        portGroupKey = "mgmt-domain-cl01-vds01-pg-esx-mgmt"
        activeUplinks = [
          "uplink0"
        ]
        teamingPolicy           = "loadbalance_loadbased"
        ipAddressVersion        = "IPv4"
        standbyUplinks          = []
      },
      {
        networkType  = "VM_MANAGEMENT"
        subnet       = module.subnets.mgmt_subnet_cidr
        gateway      = module.subnets.mgmt_subnet_cidr != null ? cidrhost(module.subnets.mgmt_subnet_cidr, 1) : null
        vlanId       = 0
        mtu          = 8700
        portGroupKey = "mgmt-domain-cl01-vds01-pg-vm-mgmt"
        activeUplinks = [
          "uplink0"
        ]
        teamingPolicy           = "loadbalance_loadbased"
        ipAddressVersion        = "IPv4"
        standbyUplinks          = []
      },
      {
        networkType = "VMOTION"
        subnet      = module.subnets.vmotion_subnet_cidr
        gateway     = module.subnets.vmotion_subnet_cidr != null ? cidrhost(module.subnets.vmotion_subnet_cidr, 1) : null
        includeIpAddressRanges = [
          {
            startIpAddress = module.subnets.vmotion_subnet_cidr != null ? cidrhost(module.subnets.vmotion_subnet_cidr, 3) : null
            endIpAddress   = module.subnets.vmotion_subnet_cidr != null ? cidrhost(module.subnets.vmotion_subnet_cidr, 100) : null
          }
        ]
        vlanId       = var.vmotion_vlan_id
        mtu          = 8700
        portGroupKey = "mgmt-domain-cl01-vds01-pg-vmotion"
        activeUplinks = [
          "uplink0"
        ]
        teamingPolicy           = "loadbalance_loadbased"
        ipAddressVersion        = "IPv4"
        standbyUplinks          = []
      },
      {
        networkType = "VSAN"
        subnet      = module.subnets.vsan_subnet_cidr
        gateway     = module.subnets.vsan_subnet_cidr != null ? cidrhost(module.subnets.vsan_subnet_cidr, 1) : null
        includeIpAddressRanges = [
          {
            startIpAddress = module.subnets.vsan_subnet_cidr != null ? cidrhost(module.subnets.vsan_subnet_cidr, 3) : null
            endIpAddress   = module.subnets.vsan_subnet_cidr != null ? cidrhost(module.subnets.vsan_subnet_cidr, 100) : null
          }
        ]
        vlanId       = var.vsan_vlan_id
        mtu          = 8700
        portGroupKey = "mgmt-domain-cl01-vds01-pg-vsan"
        activeUplinks = [
          "uplink0"
        ]
        teamingPolicy           = "loadbalance_loadbased"
        ipAddressVersion        = "IPv4"
        standbyUplinks          = []
      }
    ]

    sddcManagerSpec = {
      hostname              = "sddcm.${local.domain}"
      localUserPassword     = "<user_should_input_secret_manager_vcf-localuser-password>"
      useExistingDeployment = true
    }

    managementPoolName = "mgmt-domain-np01"

    datastoreSpec = {
      vsanSpec = {
        datastoreName      = "mgmt-domain-cl01-ds-vsan01"
        vsanDedup          = false
        failuresToTolerate = 1
        esaConfig = {
          enabled = true
        }
        encryptionConfig = {
          dataInTransitConfig = {
            enable = false
          }
        }
      }
    }

    vspClusterSpec = {
      ipv4Pool = {
        ipRange = {
          startIpAddress = local.vsp_start_ip
          endIpAddress   = local.vsp_end_ip
        }
      }
      platformFqdn            = "vsp01.${local.domain}"
      instanceFqdn            = "shared01.${local.domain}"
      fleetFqdn               = "fleetlcm.${local.domain}"
      size                    = "medium"
      name                    = "vmsp-01"
      internalClusterCidrIpv4 = "198.18.0.0/15"
    }

    fleetLcmSpec = {
      size     = "medium"
      hostname = "fleetlcm.${local.domain}"
    }

    sddcLcmSpec = {
      size     = "medium"
      hostname = "shared01.${local.domain}"
    }

    fleetDepotSpec = {
      size = "medium"
    }

    telemetryAcceptorSpec = {
      size = "small"
    }

    vidbSpec = {
      size     = "medium"
      hostname = "vidb.${local.domain}"
    }

    saltSpec = {
      size = "medium"
    }

    saltRaasSpec = {
      size = "medium"
    }

    vcfOperationsSpec = {
      nodes = [
        {
          hostname         = "ops01.${local.domain}"
          rootUserPassword = "Default123!Default123!"
          type             = "master"
        },
        {
          hostname         = "ops02.${local.domain}"
          rootUserPassword = "Default123!Default123!"
          type             = "replica"
        },
        {
          hostname         = "ops03.${local.domain}"
          rootUserPassword = "Default123!Default123!"
          type             = "data"
        }
      ]
      applianceSize         = "medium"
      loadBalancerFqdn      = ""
      useExistingDeployment = false
    }

    vcfOperationsCollectorSpec = {
      applianceSize         = "standard"
      hostname              = "collector.${local.domain}"
      useExistingDeployment = false
    }

    licenseServerSpec = {
      hostname = "license.${local.domain}"
    }
  }
  description = "Management domain deployment input configuration schema and values required for VCF Cloud Foundation deployment"
}
