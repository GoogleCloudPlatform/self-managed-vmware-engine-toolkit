# ==============================================================================
# USE CASE 2: WORKLOAD DOMAIN DATA CLUSTER CONFIGURATION
# File: sample_data_cluster.tfvars
# Description: Fully documented sample input file for provisioning, expanding,
#              and managing a dedicated VCF Workload Domain Data Cluster.
# ==============================================================================

# ==============================================================================
# 1. PROJECT & GEOGRAPHIC SCOPE
# ==============================================================================

project_id           = "vmwareengine-bm-autopush-10"
region               = "us-east4"
zone                 = "us-east4-b"
resource_name_prefix = "vcf-data01-sample"
deployment_mode      = "cluster_creation"

# ==============================================================================
# 2. VPC NETWORK, FIREWALLS & SHARED CLOUD DNS CONFIGURATION
# ==============================================================================

# VPC Network: Reference the existing VPC hosting the Management Domain
vpc_network  = "vcf-mgmt-sample-vpc"
create_vpc   = false
routing_mode = "GLOBAL"

# Firewalls: Set to false as the VPC firewall rule was established with the Mgmt Cluster.
create_firewalls = false

# Cloud DNS:
# - create_dns_zones = false: NEVER create new DNS zones for a data cluster.
# - dns_policy_name = null: NEVER create a new inbound DNS policy for a data cluster.
# - create_dns_records = true: Register ESXi host DNS records in the existing shared DNS zones.
# - forward_zone_name & reverse_zone_name: Point to the existing Management Domain DNS zones.
create_dns_records  = true
create_dns_zones    = false
forward_zone_name   = "vcf-mgmt-sample-forward-zone"
reverse_zone_name   = "vcf-mgmt-sample-reverse-zone"
reverse_domain_name = "200.10.in-addr.arpa."
dns_policy_name     = null

# ==============================================================================
# 3. L2 BROADCAST SUBNETS & ZONAL NEGs CONFIGURATION
# ==============================================================================

# Set create_subnets_and_negs = true to create dedicated subnets/NEGs for this Data Cluster,
# OR set to false and provide existing subnet/NEG names (must not be attached to or hosting other ESXi nodes).
create_subnets_and_negs = true

# Management L2 Subnet & NEG (VLAN Untagged)
mgmt_subnet_name = "vcf-data01-sample-mgmt-subnet"
mgmt_subnet_cidr = "10.200.11.0/24"
mgmt_neg_name    = "vcf-data01-sample-mgmt-neg"

# vSAN Storage L2 Subnet (VLAN Tagged)
vsan_subnet_name = "vcf-data01-sample-vsan-subnet"
vsan_subnet_cidr = "10.200.12.0/24"

# vMotion Live Migration L2 Subnet (VLAN Tagged)
vmotion_subnet_name = "vcf-data01-sample-vmotion-subnet"
vmotion_subnet_cidr = "10.200.13.0/24"

# NSX Geneve Overlay TEP L2 Subnet & NEG (VLAN Tagged)
nsx_tep_subnet_name = "vcf-data01-sample-nsx-tep-subnet"
nsx_tep_subnet_cidr = "10.200.14.0/24"
nsx_neg_name        = "vcf-data01-sample-nsx-neg"

# Additional Dynamic Workload L2 Subnets (Optional)
additional_dynamic_subnets = []

# ==============================================================================
# 4. BARE-METAL ESXI COMPUTE HOSTS MODULE CONFIGURATION
# ==============================================================================

number_of_nodes = 3 # Workload data cluster size (3 nodes)
machine_type    = "z3-highmem-192-highlssd-metal"
esxi_image      = "projects/gcve-bcom-vvol-project/global/images/vmware-esxi-9-1-0-dm-v20260513"

# Domain name must match the existing VCF Domain for consistent FQDN resolution
domain_name = "gcve-vcf.test.gve."

node_names = [
  "vcf-data01-sample-node-1",
  "vcf-data01-sample-node-2",
  "vcf-data01-sample-node-3"
]

deletion_protection     = true
create_placement_policy = true
placement_policy_name   = "vcf-data01-sample-placement-policy"
availability_count      = 6
availability_domains    = [1, 2, 3]

# ------------------------------------------------------------------------------
# Network Interface IP Allocations & VLAN Tags
# ------------------------------------------------------------------------------

# Management NIC (nic0, Untagged)
mgmt_nic_ip_address_type = "reserved_custom"
mgmt_nic_ip_values       = ["10.200.11.2", "10.200.11.3", "10.200.11.4"]

# vSAN NIC (VLAN Tagged)
vsan_vlan_id         = 100
vsan_ip_address_type = "reserved_custom"
vsan_ip_values       = ["10.200.12.2", "10.200.12.3", "10.200.12.4"]

# vMotion NIC (VLAN Tagged)
vmotion_vlan_id         = 200
vmotion_ip_address_type = "reserved_custom"
vmotion_ip_values       = ["10.200.13.2", "10.200.13.3", "10.200.13.4"]

# NSX TEP NIC (VLAN Tagged)
nsx_tep_vlan_id         = 250
nsx_tep_ip_address_type = "reserved_custom"
nsx_tep_ip_values       = ["10.200.14.2", "10.200.14.3", "10.200.14.4"]

additional_dynamic_nics = []

# ==============================================================================
# 5. REGIONAL INTERNAL LOAD BALANCERS & APPLIANCES CONFIGURATION
# ==============================================================================

# Data clusters do NOT host VCF control plane appliances.
# Leave maps and appliance DNS lists empty.
mgmt_ip_address_type = "reserved_custom"
mgmt_ip_values       = {}

nsx_ip_address_type = "reserved_custom"
nsx_ip_values       = {}
