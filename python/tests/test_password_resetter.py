"""Unit tests for vcf_deployer/password_resetter.py module."""

import unittest
from unittest import mock

import models
from vcf_deployer import password_resetter


class TestPasswordResetter(unittest.TestCase):
  """Tests for Phase 3 PasswordResetter inventory root password rotation."""

  def setUp(self):
    super().setUp()
    self.pwd_resetter = password_resetter.PasswordResetter()

  @mock.patch("vcf_deployer.password_resetter.esxi_client_mod.ESXiClient")
  def test_reset_password_already_set_returns_early(
      self, mock_esxi_client_cls
  ):
    """Verifies that if new password authentication succeeds, reset is skipped."""
    mock_client_inst = mock.MagicMock()
    mock_esxi_client_cls.return_value = mock_client_inst
    mock_si = mock.MagicMock()
    mock_client_inst.connect_pyvmomi.return_value = mock_si

    self.pwd_resetter.reset_password(
        "10.0.0.5", "Google1!Google1!", "NewRootP@ssword123!"
    )

    mock_esxi_client_cls.assert_called_once_with(
        host_ip="10.0.0.5", user="root", password="NewRootP@ssword123!"
    )
    mock_client_inst.disconnect.assert_called_once()

  @mock.patch("vcf_deployer.password_resetter.esxi_client_mod.ESXiClient")
  @mock.patch("vcf_deployer.password_resetter.vim")
  def test_reset_password_rotation_when_new_password_fails(
      self, mock_vim, mock_esxi_client_cls
  ):
    """Verifies fallback to old password and UpdateUser when new password login fails."""
    mock_client_new = mock.MagicMock()
    mock_client_new.connect_pyvmomi.side_effect = models.NonRetryableError(
        "Auth failure: Invalid credentials"
    )

    mock_client_old = mock.MagicMock()
    mock_si = mock.MagicMock()
    mock_client_old.connect_pyvmomi.return_value = mock_si
    mock_account_mgr = mock.MagicMock()
    mock_si.content.accountManager = mock_account_mgr

    mock_user_spec = mock.MagicMock()
    mock_vim.host.HostAccountSpec.return_value = mock_user_spec

    mock_esxi_client_cls.side_effect = [mock_client_new, mock_client_old]

    self.pwd_resetter.reset_password(
        "10.0.0.5", "Google1!Google1!", "NewRootP@ssword123!"
    )

    self.assertEqual(mock_esxi_client_cls.call_count, 2)
    mock_esxi_client_cls.assert_has_calls([
        mock.call(
            host_ip="10.0.0.5", user="root", password="NewRootP@ssword123!"
        ),
        mock.call(
            host_ip="10.0.0.5", user="root", password="Google1!Google1!"
        ),
    ])
    mock_account_mgr.UpdateUser.assert_called_once_with(mock_user_spec)
    self.assertEqual(mock_user_spec.id, "root")
    self.assertEqual(mock_user_spec.password, "NewRootP@ssword123!")
    mock_client_new.disconnect.assert_called_once()
    mock_client_old.disconnect.assert_called_once()

  @mock.patch("vcf_deployer.password_resetter.esxi_client_mod.ESXiClient")
  def test_reset_password_connection_error_raises_deployer_error(
      self, mock_esxi_client_cls
  ):
    """Verifies DeployerError on connection or password update failure with old password."""
    mock_client_inst = mock.MagicMock()
    mock_esxi_client_cls.return_value = mock_client_inst
    mock_client_inst.connect_pyvmomi.side_effect = Exception(
        "Auth failure: Invalid credentials"
    )

    with self.assertRaises(models.DeployerError) as ctx:
      self.pwd_resetter.reset_password(
          "10.0.0.5", "Google1!Google1!", "NewRootP@ssword123!"
      )
    self.assertIn(
        "Failed to reset root password on host '10.0.0.5'", str(ctx.exception)
    )
    self.assertEqual(mock_client_inst.disconnect.call_count, 2)

  def test_reset_esxi_inventory_passwords_empty_context(self):
    """Verifies skipping password reset gracefully when ValidationContext has no hosts."""
    ctx = models.ValidationContext(
        esxi_nodes={},
        new_esxi_root_password="NewP@ssword123!",
    )
    # Should not raise exception
    self.pwd_resetter.reset_esxi_inventory_passwords(ctx)

  @mock.patch.object(password_resetter.PasswordResetter, "reset_password")
  def test_reset_esxi_inventory_passwords_parallel_batches(
      self, mock_reset_single
  ):
    """Verifies parallel batch execution across inventory hosts."""
    details_1 = models.GCEInstanceDetails(
        instance_resource_string="p/z/instances/esxi-1",
        short_name="esxi-1",
        project="p",
        zone="z",
        primary_ip="10.0.0.1",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )
    details_2 = models.GCEInstanceDetails(
        instance_resource_string="p/z/instances/esxi-2",
        short_name="esxi-2",
        project="p",
        zone="z",
        primary_ip="10.0.0.2",
        boot_image_name="esxi-5-1-1-12345",
        subnetworks=[],
        tags=[],
        tags_fingerprint="",
    )
    ctx = models.ValidationContext(
        esxi_nodes={"esxi-1": details_1, "esxi-2": details_2},
        new_esxi_root_password="NewRootP@ss123!",
    )

    self.pwd_resetter.reset_esxi_inventory_passwords(ctx, batch_size=2)

    self.assertEqual(mock_reset_single.call_count, 2)
    mock_reset_single.assert_has_calls(
        [
            mock.call("10.0.0.1", "google1!", "NewRootP@ss123!"),
            mock.call("10.0.0.2", "google1!", "NewRootP@ss123!"),
        ],
        any_order=True,
    )


if __name__ == "__main__":
  unittest.main()
