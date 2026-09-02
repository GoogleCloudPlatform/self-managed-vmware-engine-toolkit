# ==============================================================================
# USE CASE 2: DATA CLUSTER CONFIGURATION
# File: sample_data_cluster.tfvars
# Description: Fully documented sample input file for Day-0/Day-1 provisioning and Day-2
#              lifecycle operations (Node Expansion and Workload Appliance Addition)
#              for a dedicated VMware Cloud Foundation (VCF) Data Cluster.
# ==============================================================================
# LIFECYCLE & OPERATIONS INSTRUCTIONS:
# ------------------------------------------------------------------------------
# 1. Day-0 / Day-1 Initial Cluster Provisioning:
#    - Set `deployment_mode = "cluster_creation"`.
#    - Fill in Project & Geographic Scope, Subnets, Bare-Metal Hosts, and Dynamic NICs
#      configurations in this file (reference the existing Management Cluster VPC, GCP subnet & DNS zones).
#    - Run `terraform init` and `terraform apply`.
#    - Terraform automatically provisions L2 subnets, zonal NEGs, bare-metal ESXi host
#      instances, attaches node interfaces to NEGs, and registers host DNS records in the shared zone.
#
# 2. Day-2 Node Addition (Data Cluster Scale-Out / Expansion):
#    - Set `deployment_mode = "node_addition"`.
#    - Update `number_of_nodes` to the new total node count (e.g., increment from 3 to 4, or 4 to 5).
#    - Update list-type fields ONLY if explicit values were previously specified for them:
#        * If `node_names` was explicitly specified as a list, append the new node name(s) (e.g., "vcf-data01-sample-node-4").
#          NOTE: If `node_names` was not specified (left null/unspecified), it should NOT be changed during Day-2 operations.
#        * If `availability_domains` was explicitly specified as a list, append the availability domain assignment for the new node(s) (e.g., 4).
#          NOTE: If `availability_domains` was not specified (left null/unspecified), it should NOT be changed during Day-2 operations.
#        * For network interfaces using custom IP modes ("reserved_custom" or "ephemeral_custom"), append the IP address(es) for the new node(s) to `mgmt_nic_ip_values`, `vsan_ip_values`, `vmotion_ip_values`, `nsx_tep_ip_values`, and dynamic NIC `ip_values`.
#          NOTE: If automatic IP modes ("ephemeral_automatic" or "reserved_automatic") were used and IP values lists were left empty/unspecified, they should NOT be changed during Day-2 operations.
#    - Run `terraform apply`.
#    - After Terraform apply finishes, execute the generated `gcloud` NEG attachment commands printed in the Terraform outputs (`neg_attachment_commands`) to attach the new node interfaces to their zonal NEGs.
#
# 3. Day-2 Appliance Addition:
#    - Set `deployment_mode = "appliance_addition"`.
#    - In Section 5, add new workload appliance entries and static IP addresses to `mgmt_ip_values` and/or `nsx_ip_values`. Example: `"vcf-one-more-appliance" = "10.200.11.28"` OR `"vcf-one-more-appliance" = ""` if your address type is ephemeral/reserved automatic.
#    - Run `terraform apply`. Terraform will provision the new ILB forwarding rules without modifying existing compute nodes.
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
# Valid Values: Valid GCP zone name string within the target region (e.g., "us-east4-b", "us-east4-c").
# Default Value: None (Required)
zone = "us-east4-b"

# Description: Global prefix prepended to all auto-generated GCP resource names (subnets, NEGs, placement policies, instances) for this Data Cluster when explicit names are null or omitted. If resource names are explicitly specified, this prefix is left unused for those resources.
# Valid Values: Lowercase alphanumeric string with hyphens (e.g., "vcf-data01-sample", "vcf-data02").
# Default Value: "myvcf" (Optional)
resource_name_prefix = "vcf-data01-sample"

# Description: Execution deployment mode determining the provisioning lifecycle phase:
#   - "cluster_creation": Day-0/Day-1 initial data cluster provisioning; creates subnets, NEGs, bare-metal nodes, and attaches instances to NEGs via Terraform.
#   - "node_addition": Day-2 node addition / cluster expansion; provisions new ESXi nodes and generates manual gcloud commands for NEG attachment.
#   - "appliance_addition": Day-2 appliance provisioning; creates/updates ILB forwarding rules and DNS records for new appliances.
# Valid Values: "cluster_creation", "node_addition", "appliance_addition"
# Default Value: "cluster_creation" (Optional)
deployment_mode = "cluster_creation"


# ==============================================================================
# 2. VPC Module Configuration (modules/vpc)
# ==============================================================================

# Description: VPC Network name. For Data Clusters, reference the existing VPC hosting the Management Cluster (MTU 8896).
# Valid Values: Valid VPC network name string (e.g., "vcf-mgmt-sample-vpc"), or null.
# Default Value: null (Optional)
vpc_network = "vcf-mgmt-sample-vpc"

# Description: Flag determining whether Terraform provisions a new dedicated VPC network (true) or references an existing VPC network (false). MUST be false for Data Clusters sharing the Management Domain VPC.
# Valid Values: true, false
# Default Value: false (Optional)
create_vpc = false

# Description: Dynamic BGP routing mode for the VPC network.
# Valid Values: "GLOBAL", "REGIONAL"
# Default Value: "GLOBAL" (Optional)
routing_mode = "GLOBAL"

# Description: Whether to provision the VPC allow-all ingress security firewall rule. Set to false for Data Clusters as firewall rules were already created with the Management Cluster. The firewall name is always <resource_name_prefix>-firewall-rule.
# Valid Values: true, false
# Default Value: true (Optional)
create_firewalls = false


# ------------------------------------------------------------------------------
# 2.1 Cloud DNS Managed Zones, Records, GCP Subnet & Inbound Policy Creation
# ------------------------------------------------------------------------------

# Description: Master switch determining whether to set up Cloud DNS forward (A) and reverse (PTR) records for Data Cluster ESXi compute hosts. If setup_cloud_dns is set to false, the entire DNS-related section in the input (create_gcp_subnet, gcp_subnet_name, gcp_subnet_cidr, create_dns_zones, forward_zone_name, reverse_zone_name, reverse_domain_name, dns_ttl) can be skipped, and dns_server in python_scripts_input_config will be output as "<user_should_input>".
# Valid Values: true, false
# Default Value: true (Optional)
setup_cloud_dns = true

# Description: Whether to create a dedicated standard GCP subnetwork (without resolve_subnet_mask) for Cloud DNS inbound resolver IP reservation and Offline Depot PSC endpoint (true) or reference an existing subnetwork (false). For Data Clusters sharing the VPC, set to false and reference the existing management GCP subnet if needed.
# Valid Values: true, false
# Default Value: true (Optional)
create_gcp_subnet = false

# Description: Resource name of the GCP subnetwork for DNS resolution and offline depot. When create_gcp_subnet = false, this must be the name of an existing subnetwork in GCP.
# Valid Values: Valid GCP subnetwork name string, or null.
# Default Value: null (Optional)
gcp_subnet_name = "vcf-mgmt-sample-gcp-subnet"

# Description: IPv4 CIDR range for the dedicated GCP subnetwork used for Cloud DNS inbound resolution and Offline Depot PSC endpoint. Required when create_gcp_subnet = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.0.100.0/29").
# Default Value: null (Conditional - Required when create_gcp_subnet = true)
gcp_subnet_cidr = null

# Description: Whether to create new Cloud DNS private managed zones. Set to FALSE for Data Clusters to reuse existing shared DNS zones from the Management Cluster.
# Valid Values: true, false
# Default Value: true (Optional)
create_dns_zones = false

# Description: Resource name of the existing forward managed DNS zone in GCP where Data Cluster ESXi host A records will be registered.
# Valid Values: Valid Cloud DNS managed zone name string, or null.
# Default Value: null (Conditional - Required to be an existing zone when setup_cloud_dns = true and create_dns_zones = false)
forward_zone_name = "vcf-mgmt-sample-forward-zone"

# Description: Resource name of the existing reverse managed DNS zone in GCP where Data Cluster ESXi host PTR records will be registered.
# Valid Values: Valid Cloud DNS managed zone name string, or null.
# Default Value: null (Conditional - Required to be an existing zone when setup_cloud_dns = true and create_dns_zones = false)
reverse_zone_name = "vcf-mgmt-sample-reverse-zone"

# Description: Reverse lookup domain name (in-addr.arpa.) matching the reverse managed DNS zone.
# Valid Values: Valid in-addr.arpa domain string (e.g., "200.10.in-addr.arpa.", "10.in-addr.arpa.").
# Default Value: null (Optional)
reverse_domain_name = "200.10.in-addr.arpa."

# Description: Time-to-live (TTL) in seconds for Cloud DNS record sets (A and PTR records).
# Valid Values: Positive integer in seconds (e.g., 60, 300, 3600).
# Default Value: 300 (Optional)
dns_ttl = 300

# Description: Resource name of the Cloud DNS inbound forwarding policy. Set to null for Data Clusters since the policy is already active on the VPC.
# Valid Values: Valid DNS policy name string, or null.
# Default Value: null (Optional)
dns_policy_name = null


# ==============================================================================
# 3. Subnets & NEGs Module Configuration (modules/subnets)
# ==============================================================================

# Description: Single unified boolean determining whether Terraform creates dedicated L2 broadcast learning subnets and zonal NEGs for this Data Cluster (true) or references existing ones (false).
# Valid Values: true, false
# Default Value: true (Optional)
create_subnets_and_negs = true

# ------------------------------------------------------------------------------
# 3.1 Management Network Subnet & NEG
# ------------------------------------------------------------------------------

# Description: Name of the dedicated Management L2 subnetwork for this Data Cluster (VLAN untagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-mgmt-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
mgmt_subnet_name = "vcf-data01-sample-mgmt-subnet"

# Description: IPv4 CIDR range for the Management subnetwork. Required when create_subnets_and_negs = true (must not overlap with other subnets in VPC).
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.11.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
mgmt_subnet_cidr = "10.200.11.0/24"

# Description: Resource name of the Management NIC Network Endpoint Group (NEG) for this Data Cluster. Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-mgmt-neg" if null), or referenced if false.
# Valid Values: Valid NEG resource name string, or null.
# Default Value: null (Optional)
mgmt_neg_name = "vcf-data01-sample-mgmt-neg"

# ------------------------------------------------------------------------------
# 3.2 vSAN Storage Subnet
# ------------------------------------------------------------------------------

# Description: Name of the dedicated vSAN storage L2 subnetwork for this Data Cluster (VLAN tagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-vsan-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
vsan_subnet_name = "vcf-data01-sample-vsan-subnet"

# Description: IPv4 CIDR range for the vSAN storage subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.12.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
vsan_subnet_cidr = "10.200.12.0/24"

# ------------------------------------------------------------------------------
# 3.3 vMotion Migration Subnet
# ------------------------------------------------------------------------------

# Description: Name of the dedicated vMotion live migration L2 subnetwork for this Data Cluster (VLAN tagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-vmotion-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
vmotion_subnet_name = "vcf-data01-sample-vmotion-subnet"

# Description: IPv4 CIDR range for the vMotion live migration subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.13.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
vmotion_subnet_cidr = "10.200.13.0/24"

# ------------------------------------------------------------------------------
# 3.4 NSX TEP Overlay Subnet & NEG
# ------------------------------------------------------------------------------

# Description: Name of the dedicated NSX Geneve Overlay TEP encapsulation L2 subnetwork for this Data Cluster (VLAN tagged). Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-nsx-tep-subnet" if null), or referenced if false.
# Valid Values: Valid subnetwork name string, or null.
# Default Value: null (Optional)
nsx_tep_subnet_name = "vcf-data01-sample-nsx-tep-subnet"

# Description: IPv4 CIDR range for the NSX TEP encapsulation subnetwork. Required when create_subnets_and_negs = true.
# Valid Values: Valid IPv4 CIDR block string (e.g., "10.200.14.0/24").
# Default Value: null (Conditional - Required when create_subnets_and_negs = true)
nsx_tep_subnet_cidr = "10.200.14.0/24"

# Description: Resource name of the NSX TEP NIC Network Endpoint Group (NEG) for this Data Cluster. Created if create_subnets_and_negs = true (defaults to "<resource_name_prefix>-nsx-neg" if null), or referenced if false.
# Valid Values: Valid NEG resource name string, or null.
# Default Value: null (Optional)
nsx_neg_name = "vcf-data01-sample-nsx-neg"

# ------------------------------------------------------------------------------
# 3.5 Additional Dynamic Subnets
# ------------------------------------------------------------------------------

# Description: List of customer-defined dynamic L2 broadcast subnets to create or reference for this Data Cluster.
# Valid Values: List of objects with subnet_name (string) and subnet_cidr (IPv4 CIDR string if create_subnets_and_negs = true or null if create_subnets_and_negs = false).
# Default Value: [] (Optional)
additional_dynamic_subnets = [
  {
    subnet_name = "vcf-data01-sample-additional-subnet-1"
    subnet_cidr = "10.200.15.0/24"
  }
]


# ==============================================================================
# 4. Bare-Metal ESXi Compute Hosts Module Configuration (modules/hosts)
# ==============================================================================

# Description: Total number of bare-metal ESXi compute nodes provisioned for the Workload Domain Data Cluster (minimum 3 nodes).
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

# Description: Domain name matching the existing VCF Domain for consistent FQDN resolution and DNS record registration.
# Valid Values: Non-empty domain string (e.g., "gcve-vcf.test.gve.", "vcf.corp.local.").
# Default Value: None (Required)
domain_name = "gcve-vcf.test.gve."

# Description: Explicit list of GCE node instance names. If null, names are auto-generated as ["<resource_name_prefix>-node-1", ...]. If specified, list length must match number_of_nodes. Note: If left null/unspecified during cluster creation, do not modify or specify during Day 2 node expansion.
# Valid Values: List of unique RFC 1035 compliant strings (e.g., ["vcf-data01-sample-node-1", "vcf-data01-sample-node-2", "vcf-data01-sample-node-3"]), or null.
# Default Value: null (Optional)
node_names = [
  "vcf-data01-sample-node-1",
  "vcf-data01-sample-node-2",
  "vcf-data01-sample-node-3"
]

# Description: Protects bare-metal host instances from accidental deletion via the GCE API or Terraform destroy operations.
# Valid Values: true, false
# Default Value: true (Optional)
deletion_protection = true

# Description: Flag to create a new Compute placement policy (true) or reference an existing placement policy in GCP (false).
# Valid Values: true, false
# Default Value: true (Optional)
create_placement_policy = true

# Description: Resource name of the Compute placement policy for this Data Cluster. Created if create_placement_policy = true (defaults to "<resource_name_prefix>-placement-policy" if null), or referenced if false.
# Valid Values: Valid placement policy resource name string, or null.
# Default Value: null (Optional)
placement_policy_name = "vcf-data01-sample-placement-policy"

# Description: Number of availability domains (ADs) configured in the placement policy.
# Valid Values: Integer between 5 and 8.
# Default Value: 6 (Optional)
availability_count = 6

# Description: Explicit list of availability domain IDs per host node (values 1 to availability_count). If null, hosts are automatically distributed round-robin across availability domains. Note: If left null/unspecified during cluster creation, do not modify or specify during Day 2 node expansion.
# Valid Values: List of integers (each between 1 and availability_count), or null (for automatic round-robin).
# Default Value: null (Optional)
availability_domains = [1, 2, 3]

# ------------------------------------------------------------------------------
# Network Interface IP Allocations & VLAN Tags
# Supported IP modes and required IP values:
#   1. "reserved_custom"   : Static GCP reserved IP addresses assigned with user-specified IP values.
#                            The corresponding `*_ip_values` list MUST contain exactly `number_of_nodes`
#                            valid non-conflicting IPv4 addresses within the subnetwork CIDR (e.g., ["10.200.11.2", "10.200.11.3", "10.200.11.4"]).
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
# Valid Values: List of valid non-conflicting IPv4 address strings in mgmt_subnet_cidr (e.g., ["10.200.11.2", "10.200.11.3", "10.200.11.4"]).
# Default Value: [] (Conditional)
mgmt_nic_ip_values = ["10.200.11.2", "10.200.11.3", "10.200.11.4"]

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
vsan_ip_values = ["10.200.12.2", "10.200.12.3", "10.200.12.4"]

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
# Valid Values: List of valid non-conflicting IPv4 address strings in vmotion_subnet_cidr.
# Default Value: [] (Conditional)
vmotion_ip_values = ["10.200.13.2", "10.200.13.3", "10.200.13.4"]

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
nsx_tep_ip_values = ["10.200.14.2", "10.200.14.3", "10.200.14.4"]

# ------------------------------------------------------------------------------
# 4.5 Additional Dynamic NICs
# ------------------------------------------------------------------------------

# Description: List of customer-defined dynamic VLAN interfaces to attach to bare-metal compute instances.
# Valid Values: List of objects containing name (string), subnet_name (string), vlan_id (integer 2-255), ip_address_type (string), and ip_values (list of strings).
# Default Value: [] (Optional)
additional_dynamic_nics = [
  {
    name            = "additional-nic-1"
    subnet_name     = "vcf-data01-sample-additional-subnet-1"
    vlan_id         = 210
    ip_address_type = "reserved_custom"
    ip_values       = ["10.200.15.2", "10.200.15.3", "10.200.15.4"]
  }
]


# ==============================================================================
# 5. Internal Load Balancers & Appliances Module Configuration (modules/appliances)
# ==============================================================================
# Supported IP modes and required map structures for appliance inputs:
#   - For "reserved_custom" or "ephemeral_custom": Provide a map of appliance names mapped
#     to static IPv4 addresses within the subnetwork CIDR (e.g., { "vcenter" = "10.200.0.11" }).
#   - For "reserved_automatic" or "ephemeral_automatic": Provide a map of appliance names mapped
#     to empty string values "" (e.g., { "vcenter" = "" }), allowing GCP to automatically allocate
#     IP addresses from the subnetwork CIDR while creating the required forwarding rules.
#   - NOTE: Workload Domain Data Clusters do NOT host VCF control plane appliances
#     (vCenter, NSX Managers reside in the Management Domain Cluster).
#     Leave appliance maps empty ({}) for standard data clusters unless custom workload ILBs are required.
# ==============================================================================

# ------------------------------------------------------------------------------
# 5.1 Management Appliances Configuration
# ------------------------------------------------------------------------------

# Description: IP allocation mode for Management ILB Forwarding Rules.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
mgmt_ip_address_type = "reserved_custom"

# Description: Map of management appliance names to static IP addresses. Empty for Workload Domain Data Clusters.
# Valid Values: Map of string appliance names to valid IPv4 address strings within mgmt_subnet_cidr.
# Default Value: {} (Optional)
mgmt_ip_values = {}

# ------------------------------------------------------------------------------
# 5.2 NSX Datapath Appliances Configuration
# ------------------------------------------------------------------------------

# Description: IP allocation mode for NSX Datapath & Edge ILB Forwarding Rules.
# Valid Values: "reserved_custom", "reserved_automatic", "ephemeral_custom", "ephemeral_automatic"
# Default Value: "ephemeral_automatic" (Optional)
nsx_ip_address_type = "reserved_custom"

# Description: Map of NSX datapath & Edge appliance names to static IP addresses. Empty for Workload Domain Data Clusters.
# Valid Values: Map of string appliance names to valid IPv4 address strings within nsx_tep_subnet_cidr.
# Default Value: {} (Optional)
nsx_ip_values = {}
