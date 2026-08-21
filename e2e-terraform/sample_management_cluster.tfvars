# ==============================================================================
# USE CASE 1: MANAGEMENT DOMAIN MANAGEMENT CLUSTER CONFIGURATION
# File: sample_management_cluster.tfvars
# Description: Fully documented sample input file for provisioning, expanding,
#              and managing a VMware Cloud Foundation (VCF) Management Cluster.
# ==============================================================================

# ==============================================================================
# 1. PROJECT & GEOGRAPHIC SCOPE
# ==============================================================================

# Target GCP Project ID. If null, Terraform uses the default provider project.
project_id = "vmwareengine-bm-autopush-10"

# Target GCP Region for infrastructure deployment (e.g., us-central1, us-east4).
region = "us-east4"

# Target GCP Zone for bare-metal ESXi compute nodes (e.g., us-east4-b).
zone = "us-east4-b"

# Unique prefix prepended to all resources created for this cluster.
resource_name_prefix = "vcf-mgmt-sample"

# ==============================================================================
# 2. VPC NETWORK, FIREWALLS & CLOUD DNS CONFIGURATION
# ==============================================================================

# VPC Network Configuration:
# - Set create_vpc = true to provision a new dedicated VPC network.
# - Set create_vpc = false to reference an existing VPC network (specified in vpc_network).
vpc_network  = "vcf-mgmt-sample-vpc"
create_vpc   = true
routing_mode = "GLOBAL"

# Security Firewall Configuration:
# - Set create_firewalls = true to create an allow-all ingress security rule on the VPC.
# - Set create_firewalls = false if appropriate firewall rules already exist on the VPC.
# NOTE: Firewall rules are VPC-wide and affect all clusters residing in this VPC network.
create_firewalls = true

# Cloud DNS Configuration:
# - create_dns_records: Master switch to register DNS A (forward) and PTR (reverse) records.
# - create_dns_zones: Set to true to create private forward and reverse Cloud DNS zones.
#   If false and create_dns_records = true, provide existing zone names in forward_zone_name and reverse_zone_name.
# - reverse_domain_name: Required when create_dns_zones = true (e.g., "10.in-addr.arpa.").
# - dns_policy_name: Name of Cloud DNS inbound forwarding policy. Set to null if policy is not required or already exists.
create_dns_records  = true
create_dns_zones    = true
reverse_domain_name = "200.10.in-addr.arpa."
dns_policy_name     = "vcf-mgmt-sample-dns-policy"

# Optional explicit zone names (if create_dns_zones = false, provide existing GCP zone names):
forward_zone_name = null # Defaults to "${resource_name_prefix}-forward-zone" when create_dns_zones = true
reverse_zone_name = null # Defaults to "${resource_name_prefix}-reverse-zone" when create_dns_zones = true

# ==============================================================================
# 3. L2 BROADCAST SUBNETS & ZONAL NEGs CONFIGURATION
# ==============================================================================

# - Set create_subnets_and_negs = true to provision new L2 broadcast learning subnets and NEGs.
# - Set create_subnets_and_negs = false to reference existing subnets and NEGs in GCP.
# PREREQUISITE: Existing subnets/NEGs must NOT be attached to, linked to, or hosting other ESXi nodes.
create_subnets_and_negs = true

# Primary Untagged Management L2 Subnet & NEG (VLAN Untagged)
mgmt_subnet_name = "vcf-mgmt-sample-subnet"
mgmt_subnet_cidr = "10.200.0.0/24" # Required when create_subnets_and_negs = true
mgmt_neg_name    = "vcf-mgmt-sample-neg"

# vSAN Storage L2 Subnet (VLAN Tagged)
vsan_subnet_name = "vcf-mgmt-sample-vsan-subnet"
vsan_subnet_cidr = "10.200.1.0/24" # Required when create_subnets_and_negs = true

# vMotion Live Migration L2 Subnet (VLAN Tagged)
vmotion_subnet_name = "vcf-mgmt-sample-vmotion-subnet"
vmotion_subnet_cidr = "10.200.2.0/24" # Required when create_subnets_and_negs = true

# NSX Geneve Overlay TEP L2 Subnet & NEG (VLAN Tagged)
nsx_tep_subnet_name = "vcf-mgmt-sample-nsx-tep-subnet"
nsx_tep_subnet_cidr = "10.200.3.0/24" # Required when create_subnets_and_negs = true
nsx_neg_name        = "vcf-mgmt-sample-nsx-neg"

# Additional Dynamic Workload L2 Subnets (Optional)
additional_dynamic_subnets = [
  {
    subnet_name = "vcf-mgmt-sample-workload-subnet-1"
    subnet_cidr = "10.200.4.0/24"
  }
]

# ==============================================================================
# 4. BARE-METAL ESXI COMPUTE HOSTS MODULE CONFIGURATION
# ==============================================================================

# Total number of bare-metal ESXi compute nodes (Management cluster minimum: 4 nodes).
number_of_nodes = 4

# Bare-metal machine type (z3-highmem-192-highlssd-metal or z3-highmem-192-metal).
machine_type = "z3-highmem-192-highlssd-metal"

# Source boot image URI for VMware ESXi.
esxi_image = "projects/gcve-bcom-vvol-project/global/images/vmware-esxi-9-1-0-dm-v20260513"

# Domain name appended to node_names to generate FQDN hostnames and forward DNS records.
# REQUIRED: Must match the forward DNS domain name.
domain_name = "gcve-vcf.test.gve."

# List of node instance names. If null, auto-generated as "${resource_name_prefix}-node-N".
node_names = [
  "vcf-mgmt-sample-node-1",
  "vcf-mgmt-sample-node-2",
  "vcf-mgmt-sample-node-3",
  "vcf-mgmt-sample-node-4"
]

# Protect bare-metal instances from accidental deletion via Terraform.
deletion_protection = true

# Placement Policy Configuration:
# - Set create_placement_policy = true to create a new Compute placement policy.
# - Set create_placement_policy = false to reference an existing placement policy in GCP (must not be in use by other ESXi hosts).
create_placement_policy = true
placement_policy_name   = "vcf-mgmt-sample-placement-policy"
availability_count      = 6
availability_domains    = [1, 2, 3, 4] # Explicit or round-robin availability domain mapping

# ------------------------------------------------------------------------------
# Network Interface IP Allocations & VLAN Tags
# Supported IP modes: "reserved_custom", "reserved_ephemeral", "ephemeral_custom", "ephemeral_automatic"
# ------------------------------------------------------------------------------

# Management NIC (nic0, Untagged)
mgmt_nic_ip_address_type = "reserved_custom"
mgmt_nic_ip_values       = ["10.200.0.2", "10.200.0.3", "10.200.0.4", "10.200.0.5"]

# vSAN NIC (VLAN Tagged)
vsan_vlan_id         = 100
vsan_ip_address_type = "reserved_custom"
vsan_ip_values       = ["10.200.1.2", "10.200.1.3", "10.200.1.4", "10.200.1.5"]

# vMotion NIC (VLAN Tagged)
vmotion_vlan_id         = 200
vmotion_ip_address_type = "reserved_custom"
vmotion_ip_values       = ["10.200.2.2", "10.200.2.3", "10.200.2.4", "10.200.2.5"]

# NSX TEP NIC (VLAN Tagged)
nsx_tep_vlan_id         = 250
nsx_tep_ip_address_type = "reserved_custom"
nsx_tep_ip_values       = ["10.200.3.2", "10.200.3.3", "10.200.3.4", "10.200.3.5"]

# Additional Dynamic NICs (Optional)
additional_dynamic_nics = [
  {
    name            = "workload-nic-1"
    subnet_name     = "vcf-mgmt-sample-workload-subnet-1"
    vlan_id         = 210
    ip_address_type = "reserved_custom"
    ip_values       = ["10.200.4.2", "10.200.4.3", "10.200.4.4", "10.200.4.5"]
  }
]

# ==============================================================================
# 5. REGIONAL INTERNAL LOAD BALANCERS & APPLIANCES CONFIGURATION
# ==============================================================================

# Management Appliances IP Allocation Mode & Static IP Mappings
mgmt_ip_address_type = "reserved_custom"
mgmt_ip_values = {
  # VCF Control Plane Core Services
  "vcf"                 = "10.200.0.9"  # VCF Bringup / Installer VIP
  "sddc-manager"        = "10.200.0.10" # SDDC Manager Virtual Appliance
  "vcenter"             = "10.200.0.11" # Management vCenter Server Appliance (VCSA)
  "vcf-license"         = "10.200.0.16" # VCF License Manager Service
  "vcf-instance"        = "10.200.0.17" # VCF Instance Service Manager
  "identity-broker"     = "10.200.0.18" # VMware Workspace ONE Access / Identity Broker
  "vcf-service-runtime" = "10.200.0.19" # VCF Service Runtime Platform

  # VMware Aria Suite Operations & Automation Services
  "vcfops-p"      = "10.200.0.12" # VMware Aria Operations Primary Node
  "vcffleet"      = "10.200.0.13" # VMware Aria Operations Fleet Management Service
  "vcfautomation" = "10.200.0.20" # VMware Aria Automation Core Appliance
  "vcfruntime"    = "10.200.0.21" # VMware Aria Automation Orchestrator Runtime
  "vcfops-r"      = "10.200.0.24" # VMware Aria Operations Replica Node
  "vcfops-d"      = "10.200.0.25" # VMware Aria Operations Data Analytics Node

  # NSX Management Cluster & Management Interfaces
  "nsx"       = "10.200.0.14" # NSX Management Cluster Floating Virtual IP (VIP)
  "nsx-0"     = "10.200.0.15" # NSX Manager Node 1 Management IP
  "nsx-1"     = "10.200.0.22" # NSX Manager Node 2 Management IP
  "nsx-2"     = "10.200.0.23" # NSX Manager Node 3 Management IP
  "nsx-edge1" = "10.200.0.26" # NSX Edge Node 1 Management Interface
  "nsx-edge2" = "10.200.0.27" # NSX Edge Node 2 Management Interface
}

# NSX Datapath & Edge Node IP Allocation Mode & Static IP Mappings
nsx_ip_address_type = "reserved_custom"
nsx_ip_values = {
  "uplink-vip-ip"         = "10.200.3.10" # NSX Edge Cluster Uplink Virtual Floating IP
  "edge-node-1-uplink-ip" = "10.200.3.11" # NSX Edge Node 1 External BGP/Uplink IP
  "edge-node-1-tep-ip"    = "10.200.3.12" # NSX Edge Node 1 Geneve Overlay Tunnel Endpoint (TEP)
  "edge-node-2-uplink-ip" = "10.200.3.13" # NSX Edge Node 2 External BGP/Uplink IP
  "edge-node-2-tep-ip"    = "10.200.3.14" # NSX Edge Node 2 Geneve Overlay Tunnel Endpoint (TEP)
}
