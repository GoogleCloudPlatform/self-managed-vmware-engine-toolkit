# ==============================================================================
# USE CASE 1: MANAGEMENT CLUSTER CONFIGURATION
# File: sample_management_cluster.tfvars
# Description: Fully documented sample input file for Day-0/Day-1 provisioning and Day-2
#              lifecycle operations (Node Expansion and Appliance Addition) for a
#              VMware Cloud Foundation (VCF) Management Cluster.
# ==============================================================================
# LIFECYCLE & OPERATIONS INSTRUCTIONS:
# ------------------------------------------------------------------------------
# 1. Day-0 / Day-1 Initial Cluster Provisioning:
#    - Set `deployment_mode = "cluster_creation"`.
#    - Fill in Project & Geographic Scope, VPC Network, Subnets, DNS, Bare-Metal Hosts,
#      and Appliance configurations in this file.
#    - Run `terraform init` and `terraform apply`.
#    - Terraform automatically provisions VPC infrastructure, L2 subnets, zonal NEGs,
#      bare-metal ESXi host instances, attaches node interfaces to NEGs, and provisions
#      appliance load balancers and DNS records.
#
# 2. Day-2 Node Addition (Cluster Scale-Out / Expansion):
#    - Set `deployment_mode = "node_addition"`.
#    - Update `number_of_nodes` to the new total node count (e.g., increment from 3 to 4, or 4 to 5).
#    - Update list-type fields ONLY if explicit values were previously specified for them:
#        * If `node_names` was explicitly specified as a list, append the new node name(s) (e.g., "vcf-mgmt-sample-node-4").
#          NOTE: If `node_names` was not specified (left null/unspecified), it should NOT be changed during Day-2 operations.
#        * If `availability_domains` was explicitly specified as a list, append the availability domain assignment for the new node(s) (e.g., 5).
#          NOTE: If `availability_domains` was not specified (left null/unspecified), it should NOT be changed during Day-2 operations.
#        * For network interfaces using custom IP modes ("reserved_custom" or "ephemeral_custom"), append the IP address(es) for the new node(s) to `mgmt_nic_ip_values`, `vsan_ip_values`, `vmotion_ip_values`, `nsx_tep_ip_values`, and dynamic NIC `ip_values`.
#          NOTE: If automatic IP modes ("ephemeral_automatic" or "reserved_automatic") were used and IP values lists were left empty/unspecified, they should NOT be changed during Day-2 operations.
#    - Run `terraform apply`.
#    - After Terraform apply finishes, execute the generated `gcloud` NEG attachment commands printed in the Terraform outputs (`neg_attachment_commands`) to attach the new node interfaces to their zonal NEGs.
#
# 3. Day-2 Appliance Addition:
#    - Set `deployment_mode = "appliance_addition"`.
#    - In Section 5, add the new appliance name(s) and static IP address(es) to `mgmt_ip_values` (for Management ILB forwarding rules) and/or `nsx_ip_values` (for NSX Datapath ILB forwarding rules). Example: `"vcf-one-more-appliance" = "10.200.0.28"` OR `"vcf-one-more-appliance" = ""` if your address type is ephemeral/reserved automatic.
#    - Run `terraform apply`. Terraform will provision the new ILB forwarding rules, IP reservations, and Cloud DNS A/PTR records without modifying existing compute nodes.
# ==============================================================================

# ==============================================================================
# 1. Project & Geographic Scope
# ==============================================================================

# Description: Target GCP Project ID where all infrastructure resources will be provisioned.
# Valid Values: Valid GCP project ID string (e.g., "my-gcp-project-id").
# Default Value: null (Required)
project_id = "vmwareengine-bm-autopush-10"

# Description: Target GCP Region for infrastructure provisioning (e.g., VPC, subnets, load balancers, placement policy).
# Valid Values: Valid GCP region name string (e.g., "us-east4", "us-central1").
# Default Value: None (Required)
region = "us-east4"

# Description: Target GCP Zone for bare-metal ESXi host deployment and zonal Network Endpoint Groups (NEGs).
# Valid Values: Valid GCP zone name string within the target region (e.g., "us-east4-c", "us-east4-b").
# Default Value: None (Required)
zone = "us-east4-c"

# Description: Global prefix prepended to all auto-generated GCP resource names (VPC, subnets, NEGs, DNS zones, placement policies, instances) when explicit names are null or omitted. If resource names are explicitly specified, this prefix is left unused for those resources.
# Valid Values: Lowercase alphanumeric string with hyphens (e.g., "vcf-mgmt-sample", "myvcf").
# Default Value: "myvcf" (Optional)
resource_name_prefix = "vcf-mgmt-sample"

# Description: Execution deployment mode determining the provisioning lifecycle phase:
#   - "cluster_creation": Day-0/Day-1 initial cluster provisioning; creates infrastructure, bare-metal nodes, and attaches instances to NEGs via Terraform.
#   - "node_addition": Day-2 node addition / cluster expansion; provisions new ESXi nodes and generates manual gcloud commands for NEG attachment.
#   - "appliance_addition": Day-2 appliance provisioning; creates/updates ILB forwarding rules and DNS records for new appliances without modifying existing compute nodes.
# Valid Values: "cluster_creation", "node_addition", "appliance_addition"
# Default Value: "cluster_creation" (Optional)
deployment_mode = "cluster_creation"


# ==============================================================================
# 2. VPC Module Configuration (modules/vpc)
# ==============================================================================

# Description: VPC Network name. If create_vpc = true, this name is given to the new VPC (defaults to "<resource_name_prefix>-vpc" if null). If create_vpc = false, this existing VPC is referenced and must have Jumbo Frames MTU 8896 configured.
# Valid Values: Valid VPC network name string (e.g., "vcf-mgmt-sample-vpc"), or null.
# Default Value: null (Optional)
vpc_network = "vcf-mgmt-sample-vpc"

# Description: Flag determining whether Terraform provisions a new dedicated VPC network (true) or references an existing VPC network in GCP (false).
# Valid Values: true, false
# Default Value: false (Optional)
create_vpc = true

# Description: Dynamic BGP routing mode for the VPC network. "GLOBAL" enables dynamic routes across all GCP regions; "REGIONAL" confines routes to the local region.
# Valid Values: "GLOBAL", "REGIONAL"
# Default Value: "GLOBAL" (Optional)
routing_mode = "GLOBAL"

# Description: Whether to provision the VPC allow-all ingress security firewall rule (allows all internal protocols/ports across cluster subnets). The firewall name is always <resource_name_prefix>-firewall-rule.
# Valid Values: true, false
# Default Value: true (Optional)
create_firewalls = true


# ------------------------------------------------------------------------------
# 2.1 Cloud DNS Managed Zones, Records & Inbound Policy Creation
# ------------------------------------------------------------------------------

# Description: Master switch determining whether to create Cloud DNS forward (A) and reverse (PTR) records for bare-metal ESXi hosts and VCF/NSX appliances. If create_dns_records is set to false, the entire DNS-related section in the input (create_dns_zones, forward_zone_name, reverse_zone_name, reverse_domain_name, dns_ttl) can be skipped, except dns_policy_name.
# Valid Values: true, false
# Default Value: true (Optional)
create_dns_records = true

# Description: Whether to create new forward and reverse Cloud DNS private managed zones in GCP (true) or reference existing managed zones (false).
# Valid Values: true, false
# Default Value: true (Optional)
create_dns_zones = true

# Description: Resource name of the forward managed DNS zone. When create_dns_zones = true, defaults to "<resource_name_prefix>-forward-zone" if null. If create_dns_zones = false and create_dns_records = true, this must be the name of an existing forward zone in GCP.
# Valid Values: Valid Cloud DNS managed zone name string, or null.
# Default Value: null (Conditional - Required to be an existing zone when create_dns_records = true and create_dns_zones = false)
forward_zone_name = null

# Description: Resource name of the reverse managed DNS zone. When create_dns_zones = true, defaults to "<resource_name_prefix>-reverse-zone" if null. If create_dns_zones = false and create_dns_records = true, this must be the name of an existing reverse zone in GCP.
# Valid Values: Valid Cloud DNS managed zone name string, or null.
# Default Value: null (Conditional - Required to be an existing zone when create_dns_records = true and create_dns_zones = false)
reverse_zone_name = null

# Description: Reverse lookup domain name (in-addr.arpa.) for the reverse managed DNS zone and PTR records. Required when create_dns_zones = true.
# Valid Values: Valid in-addr.arpa domain string (e.g., "200.10.in-addr.arpa.", "10.in-addr.arpa.", "0.200.10.in-addr.arpa.").
# Default Value: null (Conditional - Required when create_dns_zones = true)
reverse_domain_name = "200.10.in-addr.arpa."

# Description: Time-to-live (TTL) in seconds for Cloud DNS record sets (A and PTR records).
# Valid Values: Positive integer in seconds (e.g., 60, 300, 3600).
# Default Value: 300 (Optional)
dns_ttl = 300

# Description: Resource name of the Cloud DNS inbound forwarding policy created on the VPC network. If null, no inbound DNS server policy is created.
# Valid Values: Valid DNS policy name string (e.g., "vcf-mgmt-sample-dns-policy"), or null.
# Default Value: null (Optional)
dns_policy_name = "vcf-mgmt-sample-dns-policy"


# ==============================================================================
# 3. Subnets & NEGs Module Configuration (modules/subnets)
# ==============================================================================

# Description: Single unified boolean determining whether Terraform creates all L2 broadcast learning subnets and zonal NEGs (true) or references existing ones in GCP (false). If false, all subnets and NEGs must pre-exist and must not be attached to other ESXi nodes.
# Valid Values: true, false
# Default Value: true (Optional)
create_subnets_and_negs = true

# ------------------------------------------------------------------------------
# 3.1 Management Network Subnet & NEG
# ------------------------------------------------------------------------------

# Description: Name of the Management L2 subnetwork (VLAN untagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-mgmt-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
mgmt_subnet_name = "vcf-mgmt-sample-subnet"

# Description: IPv4 CIDR range for the Management subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.0.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
mgmt_subnet_cidr = "10.200.0.0/24"

# Description: Resource name of the Management NIC Network Endpoint Group (NEG). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-mgmt-neg" if null), or referenced if false.
# Valid Values: Valid NEG resource name string, or null.
# Default Value: null (Optional)
mgmt_neg_name = "vcf-mgmt-sample-neg"

# ------------------------------------------------------------------------------
# 3.2 vSAN Storage Subnet
# ------------------------------------------------------------------------------

# Description: Name of the vSAN storage L2 subnetwork (VLAN tagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-vsan-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
vsan_subnet_name = "vcf-mgmt-sample-vsan-subnet"

# Description: IPv4 CIDR range for the vSAN storage subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.1.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
vsan_subnet_cidr = "10.200.1.0/24"

# ------------------------------------------------------------------------------
# 3.3 vMotion Migration Subnet
# ------------------------------------------------------------------------------

# Description: Name of the vMotion live migration L2 subnetwork (VLAN tagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-vmotion-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
vmotion_subnet_name = "vcf-mgmt-sample-vmotion-subnet"

# Description: IPv4 CIDR range for the vMotion live migration subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.2.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
vmotion_subnet_cidr = "10.200.2.0/24"

# ------------------------------------------------------------------------------
# 3.4 NSX TEP Overlay Subnet & NEG
# ------------------------------------------------------------------------------

# Description: Name of the NSX Geneve Overlay TEP encapsulation L2 subnetwork (VLAN tagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-nsx-tep-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
nsx_tep_subnet_name = "vcf-mgmt-sample-nsx-tep-subnet"

# Description: IPv4 CIDR range for the NSX TEP encapsulation subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.3.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
nsx_tep_subnet_cidr = "10.200.3.0/24"

# Description: Resource name of the NSX TEP NIC Network Endpoint Group (NEG). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-nsx-neg" if null), or referenced if false.
# Valid Values: Valid NEG resource name string, or null.
# Default Value: null (Optional)
nsx_neg_name = "vcf-mgmt-sample-nsx-neg"

# ------------------------------------------------------------------------------
# 3.5 Additional Dynamic Subnets
# ------------------------------------------------------------------------------

# Description: List of customer-defined dynamic L2 broadcast subnets to create or reference. Each element specifies subnet_name and optional subnet_cidr. Names must match additional_dynamic_nics.
# Valid Values: List of objects with subnet_name (string) and subnet_cidr (IPv4 CIDR string if create_subnets_and_negs = true or null if create_subnets_and_negs = false).
# Default Value: [] (Optional)
additional_dynamic_subnets = [
  {
    subnet_name = "vcf-mgmt-sample-additional-subnet-1"
    subnet_cidr = "10.200.4.0/24"
  }
]


# ==============================================================================
# 4. Bare-Metal ESXi Compute Hosts Module Configuration (modules/hosts)
# ==============================================================================

# Description: Total number of bare-metal ESXi compute nodes provisioned (Management cluster production VCF bringup requires 4 nodes).
# Valid Values: Integer between 1 and 32.
# Default Value: 4 (Optional)
number_of_nodes = 3

# Description: Bare-metal machine type for ESXi host instances.
# Valid Values:
#   - "z3-highmem-192-highlssd-metal": Bare-metal node with Local NVMe SSDs (required for vSAN storage).
#   - "z3-highmem-192-metal": Bare-metal node without Local SSDs (for external SAN/NFS/iSCSI storage).
# Default Value: "z3-highmem-192-highlssd-metal" (Optional)
machine_type = "z3-highmem-192-highlssd-metal"

# Description: Full resource URI of the ESXi OS boot disk image for bare-metal host instances.
# Valid Values: Valid full ESXi image URI matching projects/<project>/global/images/<image-name>.
# Default Value: None (Required)
esxi_image = "projects/gcve-bcom-vvol-project/global/images/vmware-esxi-9-1-0-virtchnl-v20260803" # TODO(tulippandey) Change this once public qualified images are available

# Description: Domain name appended to node_names to compute host FQDNs and used as the forward DNS zone domain.
# Valid Values: Non-empty domain string (e.g., "gcve-vcf.test.gve.", "vcf.corp.local.").
# Default Value: None (Required)
domain_name = "gcve-vcf.test.gve."

# Description: Explicit list of GCE node instance names. If null, names are auto-generated as ["<resource_name_prefix>-node-1", ...]. If specified, list length must match number_of_nodes. Note: If left null/unspecified during cluster creation, do not modify or specify during Day 2 node expansion.
# Valid Values: List of unique RFC 1035 compliant strings (e.g., ["vcf-mgmt-sample-node-1", "vcf-mgmt-sample-node-2", "vcf-mgmt-sample-node-3"]), or null.
# Default Value: null (Optional)
node_names = [
  "vcf-mgmt-sample-node-1",
  "vcf-mgmt-sample-node-2",
  "vcf-mgmt-sample-node-3"
]

# Description: Protects bare-metal host instances from accidental deletion via the GCE API or Terraform destroy operations.
# Valid Values: true, false
# Default Value: true (Optional)
deletion_protection = false

# Description: Flag to create a new Compute placement policy (true) or reference an existing placement policy in GCP (false).
# Valid Values: true, false
# Default Value: true (Optional)
create_placement_policy = true

# Description: Resource name of the Compute placement policy. Created if create_placement_policy = true (defaults to "<resource_name_prefix>-placement-policy" if null), or referenced if false.
# Valid Values: Valid placement policy resource name string, or null.
# Default Value: null (Optional)
placement_policy_name = "vcf-mgmt-sample-placement-policy"

# Description: Number of availability domains (ADs) configured in the placement policy.
# Valid Values: Integer between 5 and 8.
# Default Value: 6 (Optional)
availability_count = 6

# Description: Explicit list of availability domain IDs per host node (values 1 to availability_count). If null, hosts are automatically distributed round-robin across availability domains. Note: If left null/unspecified during cluster creation, do not modify or specify during Day 2 node expansion.
# Valid Values: List of integers (each between 1 and availability_count), or null (for automatic round-robin).
# Default Value: null (Optional)
availability_domains = [2, 3, 4]

# ------------------------------------------------------------------------------
# Network Interface IP Allocations & VLAN Tags
# Supported IP modes and required IP values:
#   1. "reserved_custom"   : Static GCP reserved IP addresses assigned with user-specified IP values.
#                            The corresponding `*_ip_values` list MUST contain exactly `number_of_nodes`
#                            valid non-conflicting IPv4 addresses within the subnetwork CIDR (e.g., ["10.200.0.3", "10.200.0.4", "10.200.0.5"]).
#   2. "reserved_automatic": Static GCP reserved IP addresses automatically allocated by GCP from the
#                            subnetwork CIDR range. The corresponding `*_ip_values` list should be left empty (`[]`).
#   3. "ephemeral_custom"  : Ephemeral IP addresses assigned with user-specified IP values.
#                            The corresponding `*_ip_values` list MUST contain exactly `number_of_nodes`
#                            valid non-conflicting IPv4 addresses within the subnetwork CIDR.
#   4. "ephemeral_automatic": Dynamic DHCP ephemeral IP addresses automatically assigned by GCP.
#                            The corresponding `*_ip_values` list should be left empty (`[]`).
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# 4.1 Management NIC Configuration
# ------------------------------------------------------------------------------

# Description: IP allocation mode for Management NIC (nic0, VLAN untagged).
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
mgmt_nic_ip_address_type = "reserved_custom"

# Description: List of explicit IP addresses for Management NICs. Required when mgmt_nic_ip_address_type is "reserved_custom" or "ephemeral_custom" (must contain number_of_nodes entries). Leave empty ([]) for "reserved_automatic" or "ephemeral_automatic".
# Valid Values: List of valid non-conflicting IPv4 address strings in mgmt_subnet_cidr (e.g., ["10.200.0.3", "10.200.0.4", "10.200.0.5"]).
# Default Value: [] (Conditional)
mgmt_nic_ip_values = ["10.200.0.3", "10.200.0.4", "10.200.0.5"]

# ------------------------------------------------------------------------------
# 4.2 vSAN NIC Configuration
# ------------------------------------------------------------------------------

# Description: VLAN ID tag assigned to the vSAN storage network interface.
# Valid Values: Integer between 2 and 255 (must be unique across all NICs on the host).
# Default Value: 3 (Optional)
vsan_vlan_id = 100

# Description: IP allocation mode for vSAN storage NIC.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
vsan_ip_address_type = "reserved_custom"

# Description: List of explicit IP addresses for vSAN NICs. Required when vsan_ip_address_type is "reserved_custom" or "ephemeral_custom" (must contain number_of_nodes entries). Leave empty ([]) for "reserved_automatic" or "ephemeral_automatic".
# Valid Values: List of valid non-conflicting IPv4 address strings in vsan_subnet_cidr.
# Default Value: [] (Conditional)
vsan_ip_values = ["10.200.1.3", "10.200.1.4", "10.200.1.5"]

# ------------------------------------------------------------------------------
# 4.3 vMotion NIC Configuration
# ------------------------------------------------------------------------------

# Description: VLAN ID tag assigned to the vMotion live migration network interface.
# Valid Values: Integer between 2 and 255 (must be unique across all NICs on the host).
# Default Value: 2 (Optional)
vmotion_vlan_id = 200

# Description: IP allocation mode for vMotion live migration NIC.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
vmotion_ip_address_type = "reserved_custom"

# Description: List of explicit IP addresses for vMotion NICs. Required when vmotion_ip_address_type is "reserved_custom" or "ephemeral_custom" (must contain number_of_nodes entries). Leave empty ([]) for "reserved_automatic" or "ephemeral_automatic".
# Valid Values: List of valid IPv4 address strings in vmotion_subnet_cidr.
# Default Value: [] (Conditional)
vmotion_ip_values = ["10.200.2.3", "10.200.2.4", "10.200.2.5"]

# ------------------------------------------------------------------------------
# 4.4 NSX TEP NIC Configuration
# ------------------------------------------------------------------------------

# Description: VLAN ID tag assigned to the NSX Geneve Overlay TEP network interface.
# Valid Values: Integer between 2 and 255 (must be unique across all NICs on the host).
# Default Value: 4 (Optional)
nsx_tep_vlan_id = 250

# Description: IP allocation mode for NSX TEP NIC.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
nsx_tep_ip_address_type = "reserved_custom"

# Description: List of explicit IP addresses for NSX TEP NICs. Required when nsx_tep_ip_address_type is "reserved_custom" or "ephemeral_custom" (must contain number_of_nodes entries). Leave empty ([]) for "reserved_automatic" or "ephemeral_automatic".
# Valid Values: List of valid IPv4 address strings in nsx_tep_subnet_cidr.
# Default Value: [] (Conditional)
nsx_tep_ip_values = ["10.200.3.3", "10.200.3.4", "10.200.3.5"]

# ------------------------------------------------------------------------------
# 4.5 Additional Dynamic NICs
# ------------------------------------------------------------------------------

# Description: List of customer-defined dynamic VLAN interfaces to attach to bare-metal compute instances.
# Valid Values: List of objects containing name (string), subnet_name (string), vlan_id (integer 2-255), ip_address_type (string), and ip_values (list of strings).
# Default Value: [] (Optional)
additional_dynamic_nics = [
  {
    name            = "additional-nic-1"
    subnet_name     = "vcf-mgmt-sample-additional-subnet-1"
    vlan_id         = 210
    ip_address_type = "reserved_custom"
    ip_values       = ["10.200.4.3", "10.200.4.4", "10.200.4.5"]
  }
]


# ==============================================================================
# 5. Internal Load Balancers & Appliances Module Configuration (modules/appliances)
# ==============================================================================
# Supported IP modes and required map structures for appliance inputs:
#   - For "reserved_custom" or "ephemeral_custom": Provide a map of appliance names mapped
#     to static IPv4 addresses within the subnetwork CIDR (e.g., { "vcenter" = "10.200.0.11", "cloudproxy" = "10.200.0.10" }).
#   - For "reserved_automatic" or "ephemeral_automatic": Provide a map of appliance names mapped
#     to empty string values "" (e.g., { "vcenter" = "", "cloudproxy" = "" }), allowing GCP
#     to automatically allocate IP addresses from the subnetwork CIDR while creating the required forwarding rules.
#   - If no appliances of that type are required, provide an empty map `{}`.
# ==============================================================================

# ------------------------------------------------------------------------------
# 5.1 Management Appliances Configuration
# ------------------------------------------------------------------------------

# Description: IP allocation mode for Management ILB Forwarding Rules and IP reservations for VCF control plane appliances.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
mgmt_ip_address_type = "reserved_custom"

# Description: Map of management appliance names to static IP addresses in mgmt_subnet_cidr (for custom modes) or empty strings "" (for automatic modes). Forwarding rules and DNS A/PTR records are created for each entry.
# Valid Values: Map of string appliance names to valid IPv4 address strings (or empty strings "") within mgmt_subnet_cidr.
# Default Value: {} (Optional)
mgmt_ip_values = {
  # VCF Control Plane Core Services
  "vcf"                 = "10.200.0.9"  # VCF Bringup / Installer VIP
  "cloudproxy"          = "10.200.0.10" # VMware Cloud Proxy Appliance
  "vcenter"             = "10.200.0.11" # Management vCenter Server Appliance (VCSA)
  "vcf-license"         = "10.200.0.16" # VCF License Manager Service
  "vcf-instance"        = "10.200.0.17" # VCF Instance Service Manager
  "identity-broker"     = "10.200.0.18" # VMware Workspace ONE Access / Identity Broker
  "vcf-service-runtime" = "10.200.0.19" # VCF Service Runtime Platform

  # VMware Aria Suite Operations & Automation Services
  "vcfops-p"      = "10.200.0.12" # VMware Aria Operations Primary Node
  "vcffleet"      = "10.200.0.13" # VMware Aria Operations Fleet Management Service
  "vcfautomation" = "10.200.0.20" # VMware Aria Automation Core Appliance (Required if and only if VCF Automation deployment is intended)
  "vcfruntime"    = "10.200.0.21" # VMware Aria Automation Orchestrator Runtime (Required if and only if VCF Automation deployment is intended)
  "vcfops-r"      = "10.200.0.24" # VMware Aria Operations Replica Node
  "vcfops-d"      = "10.200.0.25" # VMware Aria Operations Data Analytics Node

  # NSX Management Cluster & Management Interfaces
  "nsx"       = "10.200.0.14" # NSX Management Cluster Floating Virtual IP (VIP)
  "nsx-0"     = "10.200.0.15" # NSX Manager Node 1 Management IP
  "nsx-1"     = "10.200.0.22" # NSX Manager Node 2 Management IP
  "nsx-2"     = "10.200.0.23" # NSX Manager Node 3 Management IP
  "nsx-edge1" = "10.200.0.26" # NSX Edge Node 1 Management Interface (Required if and only if NSX Edge appliance is being deployed)
  "nsx-edge2" = "10.200.0.27" # NSX Edge Node 2 Management Interface (Required if and only if NSX Edge appliance is being deployed)
}

# ------------------------------------------------------------------------------
# 5.2 NSX Datapath Appliances Configuration
# ------------------------------------------------------------------------------

# Description: IP allocation mode for NSX Datapath & Edge ILB Forwarding Rules in nsx_tep_subnet_cidr.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
nsx_ip_address_type = "reserved_custom"

# Description: Map of NSX datapath & Edge appliance names to static IP addresses in nsx_tep_subnet_cidr (for custom modes) or empty strings "" (for automatic modes). Forwarding rules are created for each entry. All appliances in nsx_ip_values are required if and only if NSX Edge appliance is being deployed.
# Valid Values: Map of string appliance names to valid IPv4 address strings (or empty strings "") within nsx_tep_subnet_cidr.
# Default Value: {} (Optional)
nsx_ip_values = {
  # All appliances below are required if and only if NSX Edge appliance is being deployed
  "uplink-vip-ip"         = "10.200.3.10" # NSX Edge Cluster Uplink Virtual Floating IP (Required iff NSX Edge is deployed)
  "edge-node-1-uplink-ip" = "10.200.3.11" # NSX Edge Node 1 External BGP/Uplink IP (Required iff NSX Edge is deployed)
  "edge-node-1-tep-ip"    = "10.200.3.12" # NSX Edge Node 1 Geneve Overlay Tunnel Endpoint (TEP) (Required iff NSX Edge is deployed)
  "edge-node-2-uplink-ip" = "10.200.3.13" # NSX Edge Node 2 External BGP/Uplink IP (Required iff NSX Edge is deployed)
  "edge-node-2-tep-ip"    = "10.200.3.14" # NSX Edge Node 2 Geneve Overlay Tunnel Endpoint (TEP) (Required iff NSX Edge is deployed)
}