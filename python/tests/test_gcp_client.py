"""Unit tests for clients/gcp_client.py module."""

import unittest
from unittest import mock

from clients import gcp_client
import models


class TestGCPClient(unittest.TestCase):
  """Tests for GCPClient Secret Manager, Compute Engine, and GCS integrations."""

  def setUp(self):
    super().setUp()
    self.client = gcp_client.GCPClient()

  def test_parse_instance_resource_valid_six_parts(self):
    """Verifies parsing of 6-part full IAM instance resource URI."""
    proj, zone, name = self.client._parse_instance_resource(
        "projects/my-proj/zones/us-central1-a/instances/esxi-1"
    )
    self.assertEqual(proj, "my-proj")
    self.assertEqual(zone, "us-central1-a")
    self.assertEqual(name, "esxi-1")

  def test_parse_instance_resource_five_parts_raises_validation_error(self):
    """Verifies ValidationError on 5-part instance resource path (only 6-part full path accepted)."""
    with self.assertRaises(models.ValidationError):
      self.client._parse_instance_resource(
          "projects/my-proj/us-central1-a/instances/esxi-1"
      )

  def test_parse_instance_resource_invalid(self):
    """Verifies ValidationError on malformed instance resource strings."""
    with self.assertRaises(models.ValidationError):
      self.client._parse_instance_resource("single_name")

    with self.assertRaises(models.ValidationError):
      self.client._parse_instance_resource("invalid/format/path")

  def test_parse_subnetwork_uri_valid(self):
    """Verifies parsing of subnetwork resource URI."""
    proj, reg, name = self.client._parse_subnetwork_uri(
        "projects/my-proj/regions/us-central1/subnetworks/sub-1"
    )
    self.assertEqual(proj, "my-proj")
    self.assertEqual(reg, "us-central1")
    self.assertEqual(name, "sub-1")

  def test_parse_subnetwork_uri_invalid(self):
    """Verifies ValidationError on malformed subnetwork resource URIs."""
    with self.assertRaises(models.ValidationError):
      self.client._parse_subnetwork_uri("invalid/subnetwork/uri")

  def test_handle_gcp_exception_http_403_raises_non_retryable(self):
    """Verifies NonRetryableError when GCP API returns 403 Forbidden."""
    if not gcp_client.gcp_exceptions:
      self.skipTest("google.api_core not installed")
    fake_exc = gcp_client.gcp_exceptions.GoogleAPICallError("Forbidden")
    fake_exc.code = 403
    fake_exc.message = "Access denied"

    with self.assertRaises(models.NonRetryableError) as ctx:
      self.client._handle_gcp_exception("test_op", "test_target", fake_exc)
    self.assertIn("GCP Terminal Error [403]", str(ctx.exception))

  def test_handle_gcp_exception_generic_exception(self):
    """Verifies RetryableError on generic unknown Exception."""
    generic_exc = RuntimeError("Socket reset by peer")
    with self.assertRaises(models.RetryableError) as ctx:
      self.client._handle_gcp_exception("test_op", "test_target", generic_exc)
    self.assertIn("Unexpected operational fault", str(ctx.exception))

  def test_handle_gcp_exception_custom_mock_google_api_call_error(self):
    """Verifies handling GoogleAPICallError status codes with mock exception class."""

    class FakeGoogleAPICallError(Exception):

      def __init__(self, code, message):
        self.code = code
        self.message = message

    with mock.patch("clients.gcp_client.gcp_exceptions") as mock_gcp_exc:
      mock_gcp_exc.GoogleAPICallError = FakeGoogleAPICallError

      # Test 401 Unauthorized -> NonRetryableError
      with self.assertRaises(models.NonRetryableError):
        self.client._handle_gcp_exception(
            "op", "tgt", FakeGoogleAPICallError(401, "Unauthorized")
        )

      # Test 404 Not Found -> NonRetryableError
      with self.assertRaises(models.NonRetryableError):
        self.client._handle_gcp_exception(
            "op", "tgt", FakeGoogleAPICallError(404, "Not Found")
        )

      # Test 500 Internal Error -> RetryableError
      with self.assertRaises(models.RetryableError):
        self.client._handle_gcp_exception(
            "op", "tgt", FakeGoogleAPICallError(500, "Internal Error")
        )

      # Test 429 Rate Limit -> RetryableError
      with self.assertRaises(models.RetryableError):
        self.client._handle_gcp_exception(
            "op", "tgt", FakeGoogleAPICallError(429, "Too Many Requests")
        )

  @mock.patch("clients.gcp_client.compute_v1")
  def test_get_instance_details_missing_primary_ip_raises_validation_error(
      self, mock_compute
  ):
    """Verifies ValidationError when nic0 has no IPv4 assigned."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst
    mock_inst = mock.MagicMock()
    mock_nic = mock.MagicMock()
    mock_nic.network_i_p = None
    mock_inst.network_interfaces = [mock_nic]
    mock_compute_inst.get.return_value = mock_inst

    with self.assertRaises(models.ValidationError) as ctx:
      self.client.get_instance_details("projects/p/zones/z/instances/esxi-1")
    self.assertIn("has no internal IPv4 assigned", str(ctx.exception))

  @mock.patch("clients.gcp_client.secretmanager")
  def test_get_secret_payload_success(self, mock_sm):
    """Verifies reading secret payload from Secret Manager."""
    mock_sm_inst = mock.MagicMock()
    mock_sm.SecretManagerServiceClient.return_value = mock_sm_inst
    mock_response = mock.MagicMock()
    mock_response.payload.data = b"MySecretPayload123!\n"
    mock_sm_inst.access_secret_version.return_value = mock_response

    payload = self.client.get_secret_payload("secrets/esxi-pwd")
    self.assertEqual(payload, "MySecretPayload123!")
    mock_sm_inst.access_secret_version.assert_called_once_with(
        request={"name": "secrets/esxi-pwd/versions/latest"}
    )

  @mock.patch("clients.gcp_client.secretmanager")
  def test_get_secret_payload_empty_raises_validation_error(self, mock_sm):
    """Verifies ValidationError when secret payload is empty."""
    mock_sm_inst = mock.MagicMock()
    mock_sm.SecretManagerServiceClient.return_value = mock_sm_inst
    mock_response = mock.MagicMock()
    mock_response.payload.data = b""
    mock_sm_inst.access_secret_version.return_value = mock_response

    with self.assertRaises(models.ValidationError) as ctx:
      self.client.get_secret_payload("secrets/empty-pwd/versions/1")
    self.assertIn("Secret Manager payload at", str(ctx.exception))

  @mock.patch("clients.gcp_client.compute_v1")
  def test_get_instance_details_success(self, mock_compute):
    """Verifies single-pass inspection resolving IP, subnets, tags, labels, and boot image."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst

    mock_inst = mock.MagicMock()
    mock_inst.name = "esxi-1"
    mock_nic0 = mock.MagicMock()
    mock_nic0.network_i_p = "10.0.0.5"
    mock_nic0.subnetwork = "projects/p/regions/r/subnetworks/sub-primary"
    mock_nic0.network = "projects/p/global/networks/vpc-1"
    mock_nic0.name = "nic0"

    mock_nic1 = mock.MagicMock()
    mock_nic1.parent_nic_name = "nic0"
    mock_nic1.vlan = 100
    mock_nic1.subnetwork = "projects/p/regions/r/subnetworks/sub-dynamic"
    mock_nic1.network = "projects/p/global/networks/vpc-1"

    mock_inst.network_interfaces = [mock_nic0, mock_nic1]
    mock_inst.tags.items = ["vcf-host", "env-prod"]
    mock_inst.tags.fingerprint = "fingerprint_123"
    mock_inst.labels = {"owner": "carrot"}
    mock_inst.label_fingerprint = "lbl_fingerprint_456"

    mock_boot_disk = mock.MagicMock()
    mock_boot_disk.boot = True
    mock_boot_disk.initialize_params.source_image = (
        "projects/p/global/images/esxi-5-1-1-12345"
    )
    mock_inst.disks = [mock_boot_disk]

    mock_compute_inst.get.return_value = mock_inst

    details = self.client.get_instance_details(
        "projects/p/zones/z/instances/esxi-1"
    )

    self.assertEqual(details.short_name, "esxi-1")
    self.assertEqual(details.primary_ip, "10.0.0.5")
    self.assertEqual(details.boot_image_name, "esxi-5-1-1-12345")
    self.assertEqual(len(details.subnetworks), 2)
    self.assertEqual(details.subnetworks[0].vlan_id, 0)
    self.assertEqual(details.subnetworks[1].vlan_id, 100)
    self.assertIn("vcf-host", details.tags)
    self.assertEqual(details.labels.get("owner"), "carrot")

  @mock.patch("clients.gcp_client.compute_v1")
  def test_get_instance_details_missing_nics_raises_validation_error(
      self, mock_compute
  ):
    """Verifies ValidationError when instance has no network interfaces."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst
    mock_inst = mock.MagicMock()
    mock_inst.network_interfaces = []
    mock_compute_inst.get.return_value = mock_inst

    with self.assertRaises(models.ValidationError) as ctx:
      self.client.get_instance_details("projects/p/zones/z/instances/esxi-1")
    self.assertIn("has no network interfaces", str(ctx.exception))

  @mock.patch("clients.gcp_client.compute_v1")
  def test_fetch_subnetwork_cidr_success(self, mock_compute):
    """Verifies fetching subnetwork IP CIDR range."""
    mock_sub_client = mock.MagicMock()
    mock_compute.SubnetworksClient.return_value = mock_sub_client
    mock_resp = mock.MagicMock()
    mock_resp.ip_cidr_range = "10.0.0.0/24"
    mock_sub_client.get.return_value = mock_resp

    cidr = self.client.fetch_subnetwork_cidr(
        "projects/p/regions/r/subnetworks/sub-1"
    )
    self.assertEqual(cidr, "10.0.0.0/24")

  @mock.patch("clients.gcp_client.compute_v1")
  def test_set_instance_tags_success(self, mock_compute):
    """Verifies patching compute instance tags with optimistic locking fingerprint."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst
    mock_op = mock.MagicMock()
    mock_compute_inst.set_tags.return_value = mock_op

    self.client.set_instance_tags(
        project="p",
        zone="z",
        instance_name="esxi-1",
        new_tags=["vcf-host"],
        fingerprint="fp123",
    )
    mock_compute_inst.set_tags.assert_called_once()
    mock_op.result.assert_called_once_with(timeout=60)

  @mock.patch("clients.gcp_client.compute_v1")
  def test_set_instance_labels_success(self, mock_compute):
    """Verifies patching compute instance labels."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst
    mock_op = mock.MagicMock()
    mock_compute_inst.set_labels.return_value = mock_op

    self.client.set_instance_labels(
        project="p",
        zone="z",
        instance_name="esxi-1",
        new_labels={"env": "prod"},
        label_fingerprint="lbl123",
    )
    mock_compute_inst.set_labels.assert_called_once()
    mock_op.result.assert_called_once_with(timeout=60)

  @mock.patch("clients.gcp_client.compute_v1")
  def test_get_forwarding_rule_ip_direct(self, mock_compute):
    """Verifies resolving IP directly from Forwarding Rule resource."""
    mock_fw_client = mock.MagicMock()
    mock_compute.ForwardingRulesClient.return_value = mock_fw_client
    mock_rule = mock.MagicMock()
    mock_rule.I_p_address = "10.0.0.50"
    mock_fw_client.get.return_value = mock_rule

    ip = self.client.get_forwarding_rule_ip("p", "r", "fr-1")
    self.assertEqual(ip, "10.0.0.50")

  @mock.patch("clients.gcp_client.compute_v1")
  def test_get_reserved_address_ip_success(self, mock_compute):
    """Verifies resolving IP from Reserved Address resource."""
    mock_addr_client = mock.MagicMock()
    mock_compute.AddressesClient.return_value = mock_addr_client
    mock_addr = mock.MagicMock()
    mock_addr.address = "10.0.0.50"
    mock_addr_client.get.return_value = mock_addr

    ip = self.client.get_reserved_address_ip("p", "r", "addr-1")
    self.assertEqual(ip, "10.0.0.50")

  @mock.patch.object(gcp_client.GCPClient, "get_reserved_address_ip")
  def test_get_forwarding_rule_ip_address_reference(self, mock_get_addr_ip):
    """Verifies forwarding rule referencing a reserved Address URI resolves via get_reserved_address_ip."""
    mock_fw_client = mock.MagicMock()
    self.client._fw_rules_client = mock_fw_client
    mock_rule = mock.MagicMock()
    mock_rule.I_p_address = "projects/p/regions/r/addresses/vcf-reserved-addr"
    mock_fw_client.get.return_value = mock_rule
    mock_get_addr_ip.return_value = "10.0.0.99"

    ip = self.client.get_forwarding_rule_ip("p", "r", "fr-1")
    self.assertEqual(ip, "10.0.0.99")
    mock_get_addr_ip.assert_called_once_with("p", "r", "vcf-reserved-addr")

  def test_get_forwarding_rule_ip_empty_raises_validation_error(self):
    """Verifies ValidationError when forwarding rule returns empty IP."""
    mock_fw_client = mock.MagicMock()
    self.client._fw_rules_client = mock_fw_client
    mock_rule = mock.MagicMock()
    mock_rule.I_p_address = None
    mock_rule.ip_address = None
    mock_fw_client.get.return_value = mock_rule

    with self.assertRaises(models.ValidationError) as ctx:
      self.client.get_forwarding_rule_ip("p", "r", "fr-1")
    self.assertIn("has no IP address assigned", str(ctx.exception))

  def test_get_reserved_address_ip_empty_raises_validation_error(self):
    """Verifies ValidationError when reserved address returns empty IP."""
    mock_addr_client = mock.MagicMock()
    self.client._addresses_client = mock_addr_client
    mock_addr = mock.MagicMock()
    mock_addr.address = ""
    mock_addr_client.get.return_value = mock_addr

    with self.assertRaises(models.ValidationError) as ctx:
      self.client.get_reserved_address_ip("p", "r", "addr-1")
    self.assertIn("is empty", str(ctx.exception))

  def test_resolve_ip_source_empty_raises_validation_error(self):
    """Verifies ValidationError when ip_source_input is empty."""
    with self.assertRaises(models.ValidationError) as ctx:
      self.client.resolve_ip_source(None)
    self.assertIn("IP source is required", str(ctx.exception))

  def test_resolve_ip_source_dict_invalid_keys_raises_validation_error(self):
    """Verifies ValidationError when dict input lacks required keys."""
    with self.assertRaises(models.ValidationError) as ctx:
      self.client.resolve_ip_source({"invalid_key": "val"})
    self.assertIn(
        "must contain 'forwarding_rule' or 'reserved_address'",
        str(ctx.exception),
    )

  @mock.patch.object(gcp_client.GCPClient, "get_forwarding_rule_ip")
  def test_resolve_ip_source_dict_forwarding_rule(self, mock_get_fr_ip):
    """Verifies resolving IP source from forwarding_rule dict."""
    mock_get_fr_ip.return_value = "10.0.0.50"
    ip = self.client.resolve_ip_source(
        {"forwarding_rule": "projects/p/regions/r/forwardingRules/fr-1"}
    )
    self.assertEqual(ip, "10.0.0.50")

  @mock.patch.object(gcp_client.GCPClient, "get_forwarding_rule_ip")
  def test_resolve_ip_source_string_forwarding_rule_uri(
      self, mock_get_fr_ip
  ):
    """Verifies resolving IP source from full forwarding rule URI string."""
    mock_get_fr_ip.return_value = "10.0.0.50"
    ip = self.client.resolve_ip_source(
        "projects/p/regions/r/forwardingRules/fr-1"
    )
    self.assertEqual(ip, "10.0.0.50")
    mock_get_fr_ip.assert_called_once_with("p", "r", "fr-1")

  @mock.patch.object(gcp_client.GCPClient, "get_reserved_address_ip")
  def test_resolve_ip_source_string_reserved_address_uri(
      self, mock_get_addr_ip
  ):
    """Verifies resolving IP source from full address URI string."""
    mock_get_addr_ip.return_value = "10.0.0.50"
    ip = self.client.resolve_ip_source(
        "projects/p/regions/r/addresses/addr-1"
    )
    self.assertEqual(ip, "10.0.0.50")
    mock_get_addr_ip.assert_called_once_with("p", "r", "addr-1")

  def test_resolve_ip_source_string_short_name_raises_validation_error(self):
    """Verifies ValidationError when string input is not a full URI."""
    with self.assertRaises(models.ValidationError) as ctx:
      self.client.resolve_ip_source(
          "short-name", default_project="p", default_region="r"
      )
    self.assertIn("must be a full forwarding rule URI", str(ctx.exception))

  @mock.patch.object(gcp_client.GCPClient, "get_reserved_address_ip")
  def test_resolve_ip_source_short_name_reserved_address(
      self, mock_get_addr_ip
  ):
    """Verifies resolving IP source from short address name using default_project and default_region."""
    mock_get_addr_ip.return_value = "10.0.0.50"
    ip = self.client.resolve_ip_source(
        {"reserved_address": "vcf-installer-test-address"},
        default_project="proj-1",
        default_region="us-east4",
    )
    self.assertEqual(ip, "10.0.0.50")
    mock_get_addr_ip.assert_called_once_with(
        "proj-1", "us-east4", "vcf-installer-test-address"
    )

  @mock.patch("clients.gcp_client.compute_v1")
  def test_resolve_boot_image_fallback_to_disks_client(self, mock_compute):
    """Verifies resolving boot image by querying DisksClient when initialize_params is absent."""
    mock_disks_client = mock.MagicMock()
    mock_compute.DisksClient.return_value = mock_disks_client
    mock_disk_obj = mock.MagicMock()
    mock_disk_obj.source_image = "projects/p/global/images/esxi-5-2-0-999"
    mock_disks_client.get.return_value = mock_disk_obj

    mock_inst = mock.MagicMock()
    mock_inst.name = "esxi-1"
    mock_disk = mock.MagicMock()
    mock_disk.boot = True
    mock_disk.initialize_params = None
    mock_disk.source = "projects/p/zones/z/disks/esxi-1-boot"
    mock_inst.disks = [mock_disk]

    img = self.client._resolve_boot_image_name("p", "z", mock_inst)
    self.assertEqual(img, "esxi-5-2-0-999")

  def test_resolve_boot_image_missing_disk_raises_validation_error(self):
    """Verifies ValidationError when instance has no disks."""
    mock_inst = mock.MagicMock()
    mock_inst.name = "esxi-1"
    mock_inst.disks = []

    with self.assertRaises(models.ValidationError) as ctx:
      self.client._resolve_boot_image_name("p", "z", mock_inst)
    self.assertIn("missing boot disk definition", str(ctx.exception))

  def test_fetch_subnetwork_cidr_empty_raises_validation_error(self):
    """Verifies ValidationError when subnetwork returns empty ip_cidr_range."""
    mock_sub_client = mock.MagicMock()
    self.client._subnets_client = mock_sub_client
    mock_resp = mock.MagicMock()
    mock_resp.ip_cidr_range = ""
    mock_sub_client.get.return_value = mock_resp

    with self.assertRaises(models.ValidationError) as ctx:
      self.client.fetch_subnetwork_cidr(
          "projects/p/regions/r/subnetworks/sub-1"
      )
    self.assertIn("returned empty ip_cidr_range", str(ctx.exception))

  def test_lazy_init_missing_packages_raise_non_retryable(self):
    """Verifies NonRetryableError when initializing clients with missing GCP packages."""
    with mock.patch("clients.gcp_client.secretmanager", None):
      with self.assertRaises(models.NonRetryableError):
        self.client._init_sm_client()

    with mock.patch("clients.gcp_client.compute_v1", None):
      with self.assertRaises(models.NonRetryableError):
        self.client._init_compute_client()
      with self.assertRaises(models.NonRetryableError):
        self.client._init_disks_client()
      with self.assertRaises(models.NonRetryableError):
        self.client._init_subnets_client()
      with self.assertRaises(models.NonRetryableError):
        self.client._init_fw_rules_client()
      with self.assertRaises(models.NonRetryableError):
        self.client._init_addresses_client()


  def test_verify_explicit_credentials_rejects_non_user_credentials(self):
    """Verifies ValidationError when credentials are not UserCredentials (e.g.

    Service Account Key or GCE Metadata Server).
    """
    mock_google = mock.MagicMock()
    mock_user_creds = mock.MagicMock()

    class FakeUserCredentials:
      pass

    class FakeServiceAccountCredentials:
      pass

    mock_user_creds.Credentials = FakeUserCredentials
    mock_google.auth.default.return_value = (
        FakeServiceAccountCredentials(),
        "proj-123",
    )

    with (
        mock.patch("clients.gcp_client.google", mock_google),
        mock.patch(
            "clients.gcp_client.google_user_credentials", mock_user_creds
        ),
    ):
      with self.assertRaises(models.ValidationError) as ctx:
        gcp_client.GCPClient(require_explicit_auth=True)
      self.assertIn(
          "Execution using Service Account keys or GCE VM attached identity is"
          " disabled",
          str(ctx.exception),
      )

  def test_verify_explicit_credentials_warns_when_credential_type_undetermined(
      self,
  ):
    """Verifies warning is logged when credential type cannot be determined."""
    mock_google = mock.MagicMock()
    mock_google.auth.default.return_value = (mock.MagicMock(), "proj-123")

    with (
        mock.patch("clients.gcp_client.google", mock_google),
        mock.patch("clients.gcp_client.google_user_credentials", None),
        mock.patch.object(gcp_client.logger, "warning") as mock_warning,
    ):
      client = gcp_client.GCPClient(require_explicit_auth=True)
      self.assertIsNotNone(client)
      mock_warning.assert_called_with(
          "Credential type couldn't be determined."
      )

  @mock.patch("clients.gcp_client.compute_v1")
  def test_list_instances_filtered_by_prefix_and_subnet(self, mock_compute):
    """Verifies listing and filtering GCE instances by prefix and subnet."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst

    inst1 = mock.MagicMock()
    inst1.name = "esxi-node-0"
    nic1 = mock.MagicMock()
    nic1.subnetwork = "projects/p/regions/r/subnetworks/subnet-a"
    inst1.network_interfaces = [nic1]

    inst2 = mock.MagicMock()
    inst2.name = "esxi-node-1"
    nic2 = mock.MagicMock()
    nic2.subnetwork = "projects/p/regions/r/subnetworks/subnet-b"
    inst2.network_interfaces = [nic2]

    inst3 = mock.MagicMock()
    inst3.name = "jumpbox-vm"
    nic3 = mock.MagicMock()
    nic3.subnetwork = "projects/p/regions/r/subnetworks/subnet-a"
    inst3.network_interfaces = [nic3]

    mock_compute_inst.list.return_value = [inst1, inst2, inst3]

    # Test prefix only
    res_prefix = self.client.list_instances("p", "z", prefix="esxi-")
    self.assertEqual(res_prefix, ["esxi-node-0", "esxi-node-1"])

    # Test subnet only
    res_subnet = self.client.list_instances("p", "z", subnet="subnet-a")
    self.assertEqual(res_subnet, ["esxi-node-0", "jumpbox-vm"])

    # Test prefix and subnet
    res_both = self.client.list_instances(
        "p", "z", prefix="esxi-", subnet="subnet-a"
    )
    self.assertEqual(res_both, ["esxi-node-0"])

    # Test full subnet URI
    res_uri = self.client.list_instances(
        "p", "z", subnet="projects/p/regions/r/subnetworks/subnet-b"
    )
    self.assertEqual(res_uri, ["esxi-node-1"])

    # Test no filters
    res_all = self.client.list_instances("p", "z")
    self.assertEqual(res_all, ["esxi-node-0", "esxi-node-1", "jumpbox-vm"])

  @mock.patch("clients.gcp_client.compute_v1")
  def test_list_instances_handles_gcp_exception(self, mock_compute):
    """Verifies list_instances translates GCP exceptions."""
    mock_compute_inst = mock.MagicMock()
    mock_compute.InstancesClient.return_value = mock_compute_inst
    mock_compute_inst.list.side_effect = RuntimeError("API unavailable")

    with self.assertRaises(models.RetryableError) as ctx:
      self.client.list_instances("p", "z")
    self.assertIn("Unexpected operational fault", str(ctx.exception))

  def test_resolve_gce_instances_list(self):
    """Verifies resolving instances from explicit list input."""
    res = self.client.resolve_gce_instances(["esxi-0", "esxi-1"], "p", "z")
    self.assertEqual(res, ["esxi-0", "esxi-1"])

  @mock.patch.object(gcp_client.GCPClient, "list_instances")
  def test_resolve_gce_instances_dict_prefix(self, mock_list):
    """Verifies resolving instances from dict containing prefix."""
    mock_list.return_value = ["esxi-0", "esxi-1"]
    res = self.client.resolve_gce_instances({"prefix": "esxi-"}, "p", "z")
    self.assertEqual(res, ["esxi-0", "esxi-1"])
    mock_list.assert_called_once_with(
        project="p", zone="z", prefix="esxi-", subnet=None
    )

  @mock.patch.object(gcp_client.GCPClient, "list_instances")
  def test_resolve_gce_instances_dict_subnet(self, mock_list):
    """Verifies resolving instances from dict containing subnet."""
    mock_list.return_value = ["esxi-0"]
    res = self.client.resolve_gce_instances({"subnet": "my-subnet"}, "p", "z")
    self.assertEqual(res, ["esxi-0"])
    mock_list.assert_called_once_with(
        project="p", zone="z", prefix=None, subnet="my-subnet"
    )

  @mock.patch.object(gcp_client.GCPClient, "list_instances")
  def test_resolve_gce_instances_dict_both_prefix_and_subnet(self, mock_list):
    """Verifies resolving instances when dict contains both prefix and subnet."""
    mock_list.return_value = ["esxi-0"]
    res = self.client.resolve_gce_instances(
        {"prefix": "esxi-", "subnet": "my-subnet"}, "p", "z"
    )
    self.assertEqual(res, ["esxi-0"])
    mock_list.assert_called_once_with(
        project="p", zone="z", prefix="esxi-", subnet="my-subnet"
    )

  def test_resolve_gce_instances_dict_invalid_keys_raises_validation_error(self):
    """Verifies ValidationError when dict contains neither prefix nor subnet."""
    with self.assertRaises(models.ValidationError) as ctx:
      self.client.resolve_gce_instances({"invalid_key": "val"}, "p", "z")
    self.assertIn("must contain 'prefix' and/or 'subnet'", str(ctx.exception))

  def test_resolve_gce_instances_empty_raises_validation_error(self):
    """Verifies ValidationError when instances input is empty."""
    with self.assertRaises(models.ValidationError) as ctx:
      self.client.resolve_gce_instances(None, "p", "z")
    self.assertIn("gce_instances in configuration profile is empty", str(ctx.exception))

  @mock.patch.object(gcp_client.GCPClient, "list_instances")
  def test_resolve_gce_instances_no_matches_raises_validation_error(
      self, mock_list
  ):
    """Verifies ValidationError when filter returns no matching instances."""
    mock_list.return_value = []
    with self.assertRaises(models.ValidationError) as ctx:
      self.client.resolve_gce_instances({"prefix": "non-existent-"}, "p", "z")
    self.assertIn("No GCE instances found matching filter", str(ctx.exception))

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_compute_api_version_custom_enabled(self):
    """Verifies that COMPUTE_API_VERSION sets custom version string."""
    client = gcp_client.GCPClient()
    self.assertEqual(client._compute_api_version, "staging_v1")

  @mock.patch.dict("os.environ", {}, clear=True)
  def test_compute_api_version_default_disabled(self):
    """Verifies that default environment does not enable version rewriter."""
    client = gcp_client.GCPClient()
    self.assertIsNone(client._compute_api_version)

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_install_api_version_rewriter_authorized_session(self):
    """Verifies that _install_api_version_rewriter rewrites AuthorizedSession requests."""
    mock_auth_module = mock.MagicMock()
    mock_auth_sess_class = mock.MagicMock()
    mock_auth_module.AuthorizedSession = mock_auth_sess_class
    orig_mock = mock.MagicMock(return_value="auth_resp")
    mock_auth_sess_class.request = orig_mock

    mock_google = mock.MagicMock()
    mock_auth = mock.MagicMock()
    mock_transport = mock.MagicMock()
    mock_transport.requests = mock_auth_module

    with mock.patch("clients.gcp_client.google", mock_google):
      with mock.patch.dict(
          "sys.modules",
          {
              "google": mock_google,
              "google.auth": mock_auth,
              "google.auth.transport": mock_transport,
              "google.auth.transport.requests": mock_auth_module,
          },
      ):
        client = gcp_client.GCPClient()
        client._install_api_version_rewriter()

        # Test hooked AuthorizedSession.request
        hooked_func = mock_auth_sess_class.request
        mock_instance = mock.MagicMock()
        res = hooked_func(
            mock_instance,
            "GET",
            "https://compute.googleapis.com/compute/v1/projects/p/zones/z/instances",
            params={"maxResults": 50},
        )
        self.assertEqual(res, "auth_resp")
        orig_mock.assert_called_once_with(
            mock_instance,
            "GET",
            "https://compute.googleapis.com/compute/staging_v1/projects/p/zones/z/instances",
            params={"maxResults": 50},
        )

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_install_api_version_rewriter_requests_session(self):
    """Verifies that _install_api_version_rewriter rewrites requests.Session requests."""
    mock_requests_module = mock.MagicMock()
    mock_session_class = mock.MagicMock()
    mock_requests_module.Session = mock_session_class
    orig_mock = mock.MagicMock(return_value="session_resp")
    mock_session_class.request = orig_mock

    with mock.patch("clients.gcp_client.google", None):
      with mock.patch.dict("sys.modules", {"requests": mock_requests_module}):
        client = gcp_client.GCPClient()
        client._install_api_version_rewriter()

        hooked_func = mock_session_class.request
        mock_instance = mock.MagicMock()
        res = hooked_func(
            mock_instance,
            "GET",
            "https://compute.googleapis.com/compute/v1/projects/p/zones/z/operations/op-123",
        )
        self.assertEqual(res, "session_resp")
        orig_mock.assert_called_once_with(
            mock_instance,
            "GET",
            "https://compute.googleapis.com/compute/staging_v1/projects/p/zones/z/operations/op-123",
        )

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_install_api_version_rewriter_handles_hooking_exception(self):
    """Verifies that _install_api_version_rewriter raises NonRetryableError on hooking error."""
    mock_auth_module = mock.MagicMock()
    type(mock_auth_module).AuthorizedSession = mock.PropertyMock(side_effect=RuntimeError("Hooking crash"))

    mock_google = mock.MagicMock()
    mock_auth = mock.MagicMock()
    mock_transport = mock.MagicMock()
    mock_transport.requests = mock_auth_module

    with mock.patch("clients.gcp_client.google", mock_google):
      with mock.patch.dict(
          "sys.modules",
          {
              "google": mock_google,
              "google.auth": mock_auth,
              "google.auth.transport": mock_transport,
              "google.auth.transport.requests": mock_auth_module,
          },
      ):
        with self.assertRaises(models.NonRetryableError) as ctx:
          gcp_client.GCPClient()
        self.assertIn("Failed to hook AuthorizedSession", str(ctx.exception))

  def test_create_offline_depot_subnetwork_exists(self):
    """Verifies create_offline_depot_subnetwork returns existing subnet link when already present."""
    mock_subnets = mock.MagicMock()
    mock_sub = mock.MagicMock()
    mock_sub.self_link = "projects/p/regions/r/subnetworks/sub-1"
    mock_subnets.get.return_value = mock_sub
    self.client._subnets_client = mock_subnets

    res = self.client.create_offline_depot_subnetwork("p", "r", "sub-1", "net-1", "10.0.100.0/29")
    self.assertEqual(res, "projects/p/regions/r/subnetworks/sub-1")
    mock_subnets.get.assert_called_once_with(project="p", region="r", subnetwork="sub-1")
    mock_subnets.insert.assert_not_called()

  def test_create_offline_depot_subnetwork_creates_when_missing(self):
    """Verifies create_offline_depot_subnetwork calls insert when subnet does not exist."""
    mock_subnets = mock.MagicMock()
    mock_subnets.get.side_effect = Exception("404 Not Found")
    mock_op = mock.MagicMock()
    mock_subnets.insert.return_value = mock_op
    self.client._subnets_client = mock_subnets

    res = self.client.create_offline_depot_subnetwork("p", "r", "sub-1", "net-1", "10.0.100.0/29")
    self.assertEqual(res, "projects/p/regions/r/subnetworks/sub-1")
    mock_subnets.insert.assert_called_once()
    mock_op.result.assert_called_once()

  def test_reserve_psc_internal_ip_exists(self):
    """Verifies reserve_psc_internal_ip returns existing address when found."""
    mock_addresses = mock.MagicMock()
    mock_addr = mock.MagicMock()
    mock_addr.self_link = "projects/p/regions/r/addresses/addr-1"
    mock_addr.address = "10.0.100.2"
    mock_addresses.get.return_value = mock_addr
    self.client._addresses_client = mock_addresses

    link, ip = self.client.reserve_psc_internal_ip("p", "r", "addr-1", "sub-uri")
    self.assertEqual(link, "projects/p/regions/r/addresses/addr-1")
    self.assertEqual(ip, "10.0.100.2")
    mock_addresses.insert.assert_not_called()

  def test_reserve_psc_internal_ip_creates_when_missing(self):
    """Verifies reserve_psc_internal_ip calls insert when address does not exist."""
    mock_addresses = mock.MagicMock()
    mock_addr = mock.MagicMock()
    mock_addr.self_link = "projects/p/regions/r/addresses/addr-1"
    mock_addr.address = "10.0.100.2"
    mock_addresses.get.side_effect = [Exception("404 Not Found"), mock_addr]
    mock_op = mock.MagicMock()
    mock_addresses.insert.return_value = mock_op
    self.client._addresses_client = mock_addresses

    link, ip = self.client.reserve_psc_internal_ip("p", "r", "addr-1", "sub-uri")
    self.assertEqual(link, "projects/p/regions/r/addresses/addr-1")
    self.assertEqual(ip, "10.0.100.2")
    mock_addresses.insert.assert_called_once()
    mock_op.result.assert_called_once()

  def test_create_offline_depot_forwarding_rule_exists(self):
    """Verifies create_offline_depot_forwarding_rule returns existing rule self_link."""
    mock_fw = mock.MagicMock()
    mock_rule = mock.MagicMock()
    mock_rule.self_link = "projects/p/regions/r/forwardingRules/ep-1"
    mock_fw.get.return_value = mock_rule
    self.client._fw_rules_client = mock_fw

    res = self.client.create_offline_depot_forwarding_rule(
        "p", "r", "ep-1", "net-1", "sub-uri", "addr-link", "svc-uri"
    )
    self.assertEqual(res, "projects/p/regions/r/forwardingRules/ep-1")
    mock_fw.insert.assert_not_called()

  def test_create_offline_depot_forwarding_rule_creates_when_missing(self):
    """Verifies create_offline_depot_forwarding_rule calls insert when forwarding rule does not exist."""
    mock_fw = mock.MagicMock()
    mock_fw.get.side_effect = Exception("404 Not Found")
    mock_op = mock.MagicMock()
    mock_fw.insert.return_value = mock_op
    self.client._fw_rules_client = mock_fw

    res = self.client.create_offline_depot_forwarding_rule(
        "p", "r", "ep-1", "net-1", "sub-uri", "addr-link", "svc-uri"
    )
    self.assertEqual(res, "projects/p/regions/r/forwardingRules/ep-1")
    mock_fw.insert.assert_called_once()
    mock_op.result.assert_called_once()

  @mock.patch("google.auth.default")
  @mock.patch("google.auth.transport.requests.AuthorizedSession")
  def test_create_offline_depot_private_dns_zone_and_record_creates_zone_and_record(
      self, mock_auth_session_cls, mock_auth_default
  ):
    """Verifies creating a new private DNS zone and adding an A record."""
    mock_auth_default.return_value = (mock.MagicMock(), "project")
    mock_session = mock.MagicMock()
    mock_auth_session_cls.return_value = mock_session

    # Zone GET returns 404 (needs creation)
    mock_zone_get_resp = mock.MagicMock()
    mock_zone_get_resp.status_code = 404
    mock_zone_get_resp.ok = False

    # Zone POST returns 201
    mock_zone_post_resp = mock.MagicMock()
    mock_zone_post_resp.status_code = 201
    mock_zone_post_resp.ok = True

    # RRset GET returns empty
    mock_rr_get_resp = mock.MagicMock()
    mock_rr_get_resp.ok = True
    mock_rr_get_resp.json.return_value = {"rrsets": []}

    # Change POST returns 200
    mock_change_resp = mock.MagicMock()
    mock_change_resp.ok = True

    mock_session.get.side_effect = [mock_zone_get_resp, mock_rr_get_resp]
    mock_session.post.side_effect = [mock_zone_post_resp, mock_change_resp]

    self.client.create_offline_depot_private_dns_zone_and_record(
        project="my-p",
        zone_name="depot-zone",
        dns_name="us-central1.selfmanagedvmwareengine.goog.",
        network_uri="projects/my-p/global/networks/my-vpc",
        a_record_fqdn="offline-depot.us-central1.selfmanagedvmwareengine.goog.",
        target_ip="10.0.100.5",
    )

    self.assertEqual(mock_session.post.call_count, 2)
    create_zone_payload = mock_session.post.call_args_list[0][1]["json"]
    self.assertEqual(create_zone_payload["name"], "depot-zone")
    self.assertEqual(create_zone_payload["visibility"], "private")

    change_payload = mock_session.post.call_args_list[1][1]["json"]
    self.assertEqual(
        change_payload["additions"][0]["name"],
        "offline-depot.us-central1.selfmanagedvmwareengine.goog.",
    )
    self.assertEqual(change_payload["additions"][0]["rrdatas"], ["10.0.100.5"])

  def test_dns_api_version_prod_default(self):
    """Verifies default environment uses dns.googleapis.com, v1 for DNS, and v1 for network URL."""
    client = gcp_client.GCPClient()
    self.assertEqual(client.get_dns_host(), "dns.googleapis.com")
    self.assertEqual(client.get_dns_api_version(), "v1")
    self.assertEqual(client.get_dns_compute_network_version(), "v1")

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "alpha"})
  def test_dns_api_version_prod_alpha(self):
    """Verifies prod alpha compute version still uses dns.googleapis.com and v1 for DNS and network URL."""
    client = gcp_client.GCPClient()
    self.assertEqual(client.get_dns_host(), "dns.googleapis.com")
    self.assertEqual(client.get_dns_api_version(), "v1")
    self.assertEqual(client.get_dns_compute_network_version(), "v1")

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "beta"})
  def test_dns_api_version_prod_beta(self):
    """Verifies prod beta compute version still uses dns.googleapis.com and v1 for DNS and network URL."""
    client = gcp_client.GCPClient()
    self.assertEqual(client.get_dns_host(), "dns.googleapis.com")
    self.assertEqual(client.get_dns_api_version(), "v1")
    self.assertEqual(client.get_dns_compute_network_version(), "v1")

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_dns_api_version_staging_v1(self):
    """Verifies staging_v1 compute version uses staging-dns.sandbox.googleapis.com, v1 for DNS, and staging_v1 for network URL."""
    client = gcp_client.GCPClient()
    self.assertEqual(client.get_dns_host(), "staging-dns.sandbox.googleapis.com")
    self.assertEqual(client.get_dns_api_version(), "v1")
    self.assertEqual(client.get_dns_compute_network_version(), "staging_v1")

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_alpha"})
  def test_dns_api_version_staging_alpha(self):
    """Verifies staging_alpha compute version uses staging-dns.sandbox.googleapis.com, v1 for DNS, and staging_v1 for network URL."""
    client = gcp_client.GCPClient()
    self.assertEqual(client.get_dns_host(), "staging-dns.sandbox.googleapis.com")
    self.assertEqual(client.get_dns_api_version(), "v1")
    self.assertEqual(client.get_dns_compute_network_version(), "staging_v1")

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "staging"}, clear=True)
  def test_dns_api_version_offline_depot_env_ignored(self):
    """Verifies that OFFLINE_DEPOT_ENV is ignored and DNS API versions rely strictly on compute API version."""
    client = gcp_client.GCPClient()
    self.assertEqual(client.get_dns_host(), "dns.googleapis.com")
    self.assertEqual(client.get_dns_api_version(), "v1")
    self.assertEqual(client.get_dns_compute_network_version(), "v1")

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_create_offline_depot_private_dns_zone_and_record_staging(self):
    """Verifies creating DNS zone and record in staging uses staging DNS host and staging_v1 compute URLs."""
    mock_google = mock.MagicMock()
    mock_auth = mock.MagicMock()
    mock_auth.default.return_value = (mock.MagicMock(), "project")
    mock_auth_module = mock.MagicMock()
    mock_session = mock.MagicMock()
    mock_auth_module.AuthorizedSession.return_value = mock_session
    mock_transport = mock.MagicMock()
    mock_transport.requests = mock_auth_module
    mock_google.auth = mock_auth

    mock_zone_get_resp = mock.MagicMock()
    mock_zone_get_resp.status_code = 404
    mock_zone_get_resp.ok = False

    mock_zone_post_resp = mock.MagicMock()
    mock_zone_post_resp.status_code = 201
    mock_zone_post_resp.ok = True

    mock_rr_get_resp = mock.MagicMock()
    mock_rr_get_resp.ok = True
    mock_rr_get_resp.json.return_value = {"rrsets": []}

    mock_change_resp = mock.MagicMock()
    mock_change_resp.ok = True

    mock_session.get.side_effect = [mock_zone_get_resp, mock_rr_get_resp]
    mock_session.post.side_effect = [mock_zone_post_resp, mock_change_resp]

    with mock.patch("clients.gcp_client.google", mock_google):
      with mock.patch.dict(
          "sys.modules",
          {
              "google": mock_google,
              "google.auth": mock_auth,
              "google.auth.transport": mock_transport,
              "google.auth.transport.requests": mock_auth_module,
          },
      ):
        client = gcp_client.GCPClient()
        client.create_offline_depot_private_dns_zone_and_record(
            project="my-p",
            zone_name="depot-zone",
            dns_name="us-central1.staging.smve-vcf.internal.",
            network_uri="projects/my-p/global/networks/my-vpc",
            a_record_fqdn="offline-depot.us-central1.staging.smve-vcf.internal.",
            target_ip="10.0.100.5",
        )

        get_zone_url = mock_session.get.call_args_list[0][0][0]
        self.assertIn("staging-dns.sandbox.googleapis.com/dns/v1/", get_zone_url)

        create_zone_call = mock_session.post.call_args_list[0]
        self.assertIn("staging-dns.sandbox.googleapis.com/dns/v1/", create_zone_call[0][0])
        create_payload = create_zone_call[1]["json"]
        self.assertEqual(
            create_payload["privateVisibilityConfig"]["networks"][0]["networkUrl"],
            "https://www.googleapis.com/compute/staging_v1/projects/my-p/global/networks/my-vpc",
        )

  @mock.patch.dict("os.environ", {"COMPUTE_API_VERSION": "staging_v1"})
  def test_install_api_version_rewriter_dns_staging(self):
    """Verifies that _install_api_version_rewriter redirects dns.googleapis.com to staging host."""
    mock_auth_module = mock.MagicMock()
    mock_auth_sess_class = mock.MagicMock()
    mock_auth_module.AuthorizedSession = mock_auth_sess_class
    orig_mock = mock.MagicMock(return_value="auth_resp")
    mock_auth_sess_class.request = orig_mock

    mock_google = mock.MagicMock()
    mock_auth = mock.MagicMock()
    mock_transport = mock.MagicMock()
    mock_transport.requests = mock_auth_module

    with mock.patch("clients.gcp_client.google", mock_google):
      with mock.patch.dict(
          "sys.modules",
          {
              "google": mock_google,
              "google.auth": mock_auth,
              "google.auth.transport": mock_transport,
              "google.auth.transport.requests": mock_auth_module,
          },
      ):
        client = gcp_client.GCPClient()
        client._install_api_version_rewriter()

        hooked_func = mock_auth_sess_class.request
        mock_instance = mock.MagicMock()
        res = hooked_func(
            mock_instance,
            "GET",
            "https://dns.googleapis.com/dns/v1/projects/p/managedZones",
        )
        self.assertEqual(res, "auth_resp")
        orig_mock.assert_called_once_with(
            mock_instance,
            "GET",
            "https://staging-dns.sandbox.googleapis.com/dns/v1/projects/p/managedZones",
        )


if __name__ == "__main__":
  unittest.main()
