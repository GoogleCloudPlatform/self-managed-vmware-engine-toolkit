"""Unit tests for utils/string_utils.py module."""

import unittest
from unittest import mock

import models
from utils import string_utils


class TestStringUtils(unittest.TestCase):
  """Tests for string parsing, password auditing, and FQDN helper routines."""

  def test_clean_gcp_uri(self):
    """Verifies stripping of Google API domain prefixes."""
    full_uri = "https://www.googleapis.com/compute/v1/projects/my-proj/zones/us-central1-a/instances/inst-1"
    self.assertEqual(
        string_utils.clean_gcp_uri(full_uri),
        "projects/my-proj/zones/us-central1-a/instances/inst-1",
    )
    self.assertEqual(
        string_utils.clean_gcp_uri("projects/my-proj/instances/inst-1"),
        "projects/my-proj/instances/inst-1",
    )
    self.assertEqual(string_utils.clean_gcp_uri(""), "")

  def test_parse_forwarding_rule_path_valid(self):
    """Verifies parsing of valid GCP forwarding rule resource paths."""
    path = "projects/my-proj/regions/us-east4/forwardingRules/vcf-fr"
    project, region, name = string_utils.parse_forwarding_rule_path(path)
    self.assertEqual(project, "my-proj")
    self.assertEqual(region, "us-east4")
    self.assertEqual(name, "vcf-fr")

  def test_parse_forwarding_rule_path_invalid(self):
    """Verifies ValidationError on malformed forwarding rule paths."""
    with self.assertRaises(models.ValidationError):
      string_utils.parse_forwarding_rule_path("invalid/path/format")

  def test_parse_address_path_valid(self):
    """Verifies parsing of valid GCP reserved address resource paths."""
    path = "projects/my-proj/regions/us-central1/addresses/vcf-addr"
    project, region, name = string_utils.parse_address_path(path)
    self.assertEqual(project, "my-proj")
    self.assertEqual(region, "us-central1")
    self.assertEqual(name, "vcf-addr")

  def test_parse_address_path_invalid(self):
    """Verifies ValidationError on malformed address resource paths."""
    with self.assertRaises(models.ValidationError):
      string_utils.parse_address_path("projects/proj/addresses/missing_region")

  def test_audit_password_success(self):
    """Verifies password audit passes for compliant password strings."""
    # ESXi root: min 7, max 39, min 3 classes
    string_utils.audit_password(
        "esxi_root", "ValidP@ssw0rd!", min_len=7, max_len=39, min_classes=3
    )
    # VCF root: min 15, max 0, min 4 classes
    string_utils.audit_password(
        "vcf_root",
        "Complex!VCF_R00t_P@ssword2026",
        min_len=15,
        max_len=0,
        min_classes=4,
    )

  def test_audit_password_length_failure(self):
    """Verifies ValidationError when password length is out of bounds."""
    with self.assertRaises(models.ValidationError) as ctx:
      string_utils.audit_password(
          "short_pwd", "Short1!", min_len=15, max_len=0, min_classes=3
      )
    self.assertIn("fails length verification", str(ctx.exception))

    with self.assertRaises(models.ValidationError) as ctx:
      string_utils.audit_password(
          "long_pwd", "A" * 40, min_len=7, max_len=39, min_classes=1
      )
    self.assertIn("fails length verification", str(ctx.exception))

  def test_audit_password_complexity_failure(self):
    """Verifies ValidationError when password lacks required character classes."""
    # Only lowercase and digits (2 classes, min required 4)
    with self.assertRaises(models.ValidationError) as ctx:
      string_utils.audit_password(
          "low_complexity",
          "alllowercaseanddigits12345",
          min_len=12,
          max_len=0,
          min_classes=4,
      )
    self.assertIn("fails complexity verification", str(ctx.exception))

  def test_audit_password_contains_username_failure(self):
    """Verifies ValidationError when password contains default root username."""
    # Complies with length (>= 7) and classes (4 classes), but contains 'root'
    invalid_passwords = [
        "ValidP@ssw0rd_root",   # lower at end
        "root_ValidP@ssw0rd!",  # lower at start
        "ValidRootP@ssw0rd1!",  # TitleCase
        "VALID_ROOT_P@SSW0RD1", # UPPERCASE
    ]
    for pwd in invalid_passwords:
      with self.subTest(pwd=pwd):
        with self.assertRaises(models.ValidationError) as ctx:
          string_utils.audit_password(
              "esxi_root", pwd, min_len=7, max_len=39, min_classes=3
          )
        self.assertIn("must not contain", str(ctx.exception))
        # Explicitly verify it didn't throw complexity error (guards against message swapping)
        self.assertNotIn("fails complexity verification", str(ctx.exception))

  def test_parse_vcf_version_from_image_valid(self):
    """Verifies semantic version parsing from standard ESXi boot image names."""
    self.assertEqual(
        string_utils.parse_vcf_version_from_image("esxi-5-1-1-23395914"),
        "5.1.1",
    )
    self.assertEqual(
        string_utils.parse_vcf_version_from_image(
            "projects/p/global/images/vmware-esxi-5-2-0-123456"
        ),
        "5.2.0",
    )

  def test_parse_vcf_version_from_image_invalid(self):
    """Verifies ValidationError when boot image name format is invalid."""
    with self.assertRaises(models.ValidationError) as ctx:
      string_utils.parse_vcf_version_from_image("custom-ubuntu-image-2004")
    self.assertIn("must match format", str(ctx.exception))

  def test_deconstruct_fqdn_valid(self):
    """Verifies deconstruction of valid FQDN into VM Name, Domain, and Searchpath."""
    vm_name, domain, searchpath = string_utils.deconstruct_fqdn(
        "sddc-manager.vcf.internal"
    )
    self.assertEqual(vm_name, "sddc-manager")
    self.assertEqual(domain, "vcf.internal")
    self.assertEqual(searchpath, "vcf.internal")

  def test_deconstruct_fqdn_with_trailing_dot(self):
    """Verifies that trailing dot in FQDN is stripped cleanly without raising error."""
    vm_name, domain, searchpath = string_utils.deconstruct_fqdn(
        "sddc-manager.vcf.internal."
    )
    self.assertEqual(vm_name, "sddc-manager")
    self.assertEqual(domain, "vcf.internal")
    self.assertEqual(searchpath, "vcf.internal")

  def test_deconstruct_fqdn_invalid_structure(self):
    """Verifies ValidationError on non-FQDN single label strings."""
    with self.assertRaises(models.ValidationError):
      string_utils.deconstruct_fqdn("singlelabel")

  def test_deconstruct_fqdn_invalid_rfc1123(self):
    """Verifies ValidationError when label violates RFC 1123 rules."""
    with self.assertRaises(models.ValidationError) as ctx:
      string_utils.deconstruct_fqdn("invalid_vm_name!.domain.com")
    self.assertIn("fails RFC 1123 conformance", str(ctx.exception))

  def test_extract_region_from_zone(self):
    """Verifies region extraction from GCP zone strings and URIs."""
    self.assertEqual(
        string_utils.extract_region_from_zone("us-central1-a"), "us-central1"
    )
    self.assertEqual(
        string_utils.extract_region_from_zone(
            "projects/p/zones/europe-west3-c"
        ),
        "europe-west3",
    )

  def test_select_optimal_ova_object_highest_build(self):
    """Verifies selecting the OVA artifact with the highest build number."""
    object_list = [
        "VCF-SDDC-Manager-Appliance-5.1.1.200.ova",
        "VCF-SDDC-Manager-Appliance-5.1.1.450.ova",
        "VCF-SDDC-Manager-Appliance-5.1.1.300.ova",
        "some_other_file.iso",
    ]
    optimal = string_utils.select_optimal_ova_object(
        object_list, "test-bucket", "VCF-SDDC-Manager-Appliance-5.1.1"
    )
    self.assertEqual(optimal, "VCF-SDDC-Manager-Appliance-5.1.1.450.ova")

  def test_select_optimal_ova_object_no_match(self):
    """Verifies ValidationError when no matching OVA objects are present."""
    with self.assertRaises(models.ValidationError):
      string_utils.select_optimal_ova_object(
          ["file1.txt", "file2.iso"], "test-bucket", "prefix"
      )

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "staging"})
  def test_get_depot_host_template_from_offline_depot_env(self):
    """Verifies get_depot_host_template reads OFFLINE_DEPOT_ENV."""
    self.assertEqual(
        string_utils.get_depot_host_template(),
        "offline-depot.{region}.staging.smve-vcf.internal",
    )

  @mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "autopush"})
  def test_get_depot_host_template_from_autopush_env(self):
    """Verifies get_depot_host_template reads OFFLINE_DEPOT_ENV=autopush."""
    self.assertEqual(
        string_utils.get_depot_host_template(),
        "offline-depot.{region}.autopush.smve-vcf.internal",
    )

  @mock.patch.dict("os.environ", {}, clear=True)
  def test_get_depot_host_template_default_prod(self):
    """Verifies get_depot_host_template defaults to prod when env is unset."""
    self.assertEqual(
        string_utils.get_depot_host_template(),
        "offline-depot.{region}.selfmanagedvmwareengine.goog",
    )

  def test_offline_depot_domain_helpers(self):
    """Verifies offline depot domain and URI helper functions across environments."""
    # Test Prod defaults (no env var)
    with mock.patch.dict("os.environ", {}, clear=True):
      self.assertEqual(string_utils.get_active_env(), "prod")
      self.assertEqual(
          string_utils.get_base_domain("us-central1"),
          "us-central1.selfmanagedvmwareengine.goog.",
      )
      self.assertEqual(
          string_utils.get_host_fqdn("us-central1"),
          "offline-depot.us-central1.selfmanagedvmwareengine.goog.",
      )
      self.assertEqual(
          string_utils.get_service_attachment_uri("us-central1"),
          "projects/smve-prod-offline-depot/regions/us-central1/serviceAttachments/offline-depot-service-attachment-us-central1",
      )
      self.assertEqual(
          string_utils.get_dns_zone_name("us-central1"),
          "offline-depot-us-central1-prod-zone",
      )

    # Test Autopush environment
    with mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "autopush"}):
      self.assertEqual(string_utils.get_active_env(), "autopush")
      self.assertEqual(
          string_utils.get_base_domain("us-central1"),
          "us-central1.autopush.smve-vcf.internal.",
      )
      self.assertEqual(
          string_utils.get_host_fqdn("us-central1"),
          "offline-depot.us-central1.autopush.smve-vcf.internal.",
      )
      self.assertEqual(
          string_utils.get_service_attachment_uri("us-central1"),
          "projects/smve-autopush-offline-depot/regions/us-central1/serviceAttachments/offline-depot-service-attachment-us-central1",
      )
      self.assertEqual(
          string_utils.get_dns_zone_name("us-central1"),
          "offline-depot-us-central1-autopush-zone",
      )

    # Test Staging environment
    with mock.patch.dict("os.environ", {"OFFLINE_DEPOT_ENV": "staging"}):
      self.assertEqual(string_utils.get_active_env(), "staging")
      self.assertEqual(
          string_utils.get_base_domain("us-central1"),
          "us-central1.staging.smve-vcf.internal.",
      )
      self.assertEqual(
          string_utils.get_host_fqdn("us-central1"),
          "offline-depot.us-central1.staging.smve-vcf.internal.",
      )
      self.assertEqual(
          string_utils.get_service_attachment_uri("us-central1"),
          "projects/smve-staging-offline-depot/regions/us-central1/serviceAttachments/offline-depot-service-attachment-us-central1",
      )
      self.assertEqual(
          string_utils.get_dns_zone_name("us-central1"),
          "offline-depot-us-central1-staging-zone",
      )


if __name__ == "__main__":
  unittest.main()

