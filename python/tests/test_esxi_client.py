"""Unit tests for clients/esxi_client.py module."""

import unittest
from unittest import mock

from clients import esxi_client
import constants
import models


class TestESXiClient(unittest.TestCase):
  """Tests for ESXiClient pyVmomi and SSH wrapper operations."""

  def setUp(self):
    super().setUp()
    self.client = esxi_client.ESXiClient(
        host_ip="10.0.0.5", user="root", password="DefaultSecret1!"
    )

  @mock.patch("clients.esxi_client.connect")
  def test_connect_pyvmomi_smart_connect_no_ssl_success(self, mock_connect):
    """Verifies pyVmomi connection using SmartConnectNoSSL."""
    mock_si = mock.MagicMock()
    mock_connect.SmartConnectNoSSL.return_value = mock_si

    si = self.client.connect_pyvmomi()
    self.assertEqual(si, mock_si)
    mock_connect.SmartConnectNoSSL.assert_called_once_with(
        host="10.0.0.5", user="root", pwd="DefaultSecret1!", port=443
    )

    # Calling again returns cached instance without re-connecting
    si_cached = self.client.connect_pyvmomi()
    self.assertEqual(si_cached, mock_si)
    self.assertEqual(mock_connect.SmartConnectNoSSL.call_count, 1)

  @mock.patch("clients.esxi_client.connect")
  @mock.patch("ssl._create_unverified_context")
  def test_connect_pyvmomi_fallback_smart_connect_success(
      self, mock_ssl_ctx, mock_connect
  ):
    """Verifies fallback to SmartConnect when SmartConnectNoSSL is missing."""
    del mock_connect.SmartConnectNoSSL  # Remove attribute to test fallback
    mock_si = mock.MagicMock()
    mock_connect.SmartConnect.return_value = mock_si
    fake_ctx = mock.MagicMock()
    mock_ssl_ctx.return_value = fake_ctx

    si = self.client.connect_pyvmomi()
    self.assertEqual(si, mock_si)
    mock_connect.SmartConnect.assert_called_once_with(
        host="10.0.0.5",
        user="root",
        pwd="DefaultSecret1!",
        port=443,
        sslContext=fake_ctx,
    )

  @mock.patch("clients.esxi_client.connect")
  def test_connect_pyvmomi_authentication_error_raises_non_retryable(
      self, mock_connect
  ):
    """Verifies NonRetryableError when ESXi authentication fails (401/Cannot authenticate)."""
    mock_connect.SmartConnectNoSSL.side_effect = Exception(
        "Cannot authenticate user root"
    )
    with self.assertRaises(models.NonRetryableError) as ctx:
      self.client.connect_pyvmomi()
    self.assertIn("Authentication failed on ESXi host", str(ctx.exception))

  @mock.patch("clients.esxi_client.connect")
  def test_connect_pyvmomi_fallback_on_auth_failure_success(
      self, mock_connect
  ):
    """Verifies fallback password authentication succeeds when primary password fails."""
    client = esxi_client.ESXiClient(
        host_ip="10.0.0.5",
        user="root",
        password="OldPassword1!",
        fallback_password="NewPassword1!",
    )
    mock_si = mock.MagicMock()
    mock_connect.SmartConnectNoSSL.side_effect = [
        Exception("Cannot authenticate user root"),
        mock_si,
    ]

    si = client.connect_pyvmomi()
    self.assertEqual(si, mock_si)
    self.assertEqual(client.password, "NewPassword1!")
    self.assertEqual(mock_connect.SmartConnectNoSSL.call_count, 2)
    mock_connect.SmartConnectNoSSL.assert_has_calls([
        mock.call(
            host="10.0.0.5", user="root", pwd="OldPassword1!", port=443
        ),
        mock.call(
            host="10.0.0.5", user="root", pwd="NewPassword1!", port=443
        ),
    ])

  @mock.patch("clients.esxi_client.connect")
  def test_connect_pyvmomi_fallback_on_auth_failure_both_fail(
      self, mock_connect
  ):
    """Verifies NonRetryableError when both primary and fallback passwords fail."""
    client = esxi_client.ESXiClient(
        host_ip="10.0.0.5",
        user="root",
        password="OldPassword1!",
        fallback_password="NewPassword1!",
    )
    mock_connect.SmartConnectNoSSL.side_effect = [
        Exception("Cannot authenticate user root"),
        Exception("401 Unauthorized"),
    ]

    with self.assertRaises(models.NonRetryableError) as ctx:
      client.connect_pyvmomi()
    self.assertIn("with both primary and fallback passwords", str(ctx.exception))

  @mock.patch("clients.esxi_client.connect")
  def test_connect_pyvmomi_network_error_raises_retryable(self, mock_connect):
    """Verifies RetryableError on transient socket connection error."""
    mock_connect.SmartConnectNoSSL.side_effect = TimeoutError(
        "Socket connection timed out"
    )
    with self.assertRaises(models.RetryableError) as ctx:
      self.client.connect_pyvmomi()
    self.assertIn("Failed to connect to ESXi pyVmomi API", str(ctx.exception))

  @mock.patch.object(esxi_client.ESXiClient, "execute_ssh_command")
  def test_execute_esxcli(self, mock_exec_ssh):
    """Verifies building and executing esxcli command string."""
    mock_exec_ssh.return_value = "Enabled: true"
    res = self.client.execute_esxcli(["vsan", "cluster", "get"])
    self.assertEqual(res, "Enabled: true")
    mock_exec_ssh.assert_called_once_with("esxcli vsan cluster get")

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_success(self, mock_paramiko):
    """Verifies successful SSH command execution and output decoding."""
    mock_ssh = mock.MagicMock()
    mock_paramiko.SSHClient.return_value = mock_ssh
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value = b"command output"
    mock_stderr.read.return_value = b""
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_ssh.exec_command.return_value = (None, mock_stdout, mock_stderr)

    out = self.client.execute_ssh_command("uname -a")
    self.assertEqual(out, "command output")
    mock_ssh.connect.assert_called_once_with(
        hostname="10.0.0.5",
        port=22,
        username="root",
        password="DefaultSecret1!",
        allow_agent=False,
        look_for_keys=False,
        timeout=constants.NetworkingDefaults.SSH_TIMEOUT_SECONDS,
    )
    mock_ssh.close.assert_called_once()

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_fallback_on_auth_failure_success(
      self, mock_paramiko
  ):
    """Verifies SSH fallback password authentication succeeds when primary fails."""
    client = esxi_client.ESXiClient(
        host_ip="10.0.0.5",
        user="root",
        password="OldPassword1!",
        fallback_password="NewPassword1!",
    )
    mock_ssh_1 = mock.MagicMock()
    mock_ssh_1.connect.side_effect = Exception("Authentication failed.")
    mock_ssh_2 = mock.MagicMock()
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value = b"success"
    mock_stderr.read.return_value = b""
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_ssh_2.exec_command.return_value = (None, mock_stdout, mock_stderr)

    mock_paramiko.SSHClient.side_effect = [mock_ssh_1, mock_ssh_2]

    out = client.execute_ssh_command("uname -a")
    self.assertEqual(out, "success")
    self.assertEqual(client.password, "NewPassword1!")
    mock_ssh_1.connect.assert_called_once_with(
        hostname="10.0.0.5",
        port=22,
        username="root",
        password="OldPassword1!",
        allow_agent=False,
        look_for_keys=False,
        timeout=constants.NetworkingDefaults.SSH_TIMEOUT_SECONDS,
    )
    mock_ssh_2.connect.assert_called_once_with(
        hostname="10.0.0.5",
        port=22,
        username="root",
        password="NewPassword1!",
        allow_agent=False,
        look_for_keys=False,
        timeout=constants.NetworkingDefaults.SSH_TIMEOUT_SECONDS,
    )

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_fallback_on_auth_failure_both_fail(
      self, mock_paramiko
  ):
    """Verifies NonRetryableError when both primary and fallback SSH passwords fail."""
    client = esxi_client.ESXiClient(
        host_ip="10.0.0.5",
        user="root",
        password="OldPassword1!",
        fallback_password="NewPassword1!",
    )
    mock_ssh = mock.MagicMock()
    mock_ssh.connect.side_effect = Exception("Authentication failed.")
    mock_paramiko.SSHClient.return_value = mock_ssh

    with self.assertRaises(models.NonRetryableError) as ctx:
      client.execute_ssh_command("uname -a")
    self.assertIn("SSH authentication failed on ESXi host", str(ctx.exception))

  @mock.patch("clients.esxi_client.paramiko", None)
  def test_execute_ssh_command_missing_paramiko_raises_non_retryable(self):
    """Verifies NonRetryableError when paramiko library is missing."""
    with self.assertRaises(models.NonRetryableError) as ctx:
      self.client.execute_ssh_command("uname -a")
    self.assertIn("paramiko package is not installed", str(ctx.exception))

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_non_zero_exit_raises_non_retryable(
      self, mock_paramiko
  ):
    """Verifies NonRetryableError when command fails with non-zero exit status."""
    mock_ssh = mock.MagicMock()
    mock_paramiko.SSHClient.return_value = mock_ssh
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value = b""
    mock_stderr.read.return_value = b"Command not found"
    mock_stdout.channel.recv_exit_status.return_value = 127
    mock_ssh.exec_command.return_value = (None, mock_stdout, mock_stderr)

    with self.assertRaises(models.NonRetryableError) as ctx:
      self.client.execute_ssh_command("invalid_cmd")
    self.assertIn("failed with exit code 127", str(ctx.exception))

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_vsan_cluster_get_non_zero_allowed(
      self, mock_paramiko
  ):
    """Verifies non-zero exit code is allowed for 'vsan cluster get' when vSAN is disabled."""
    mock_ssh = mock.MagicMock()
    mock_paramiko.SSHClient.return_value = mock_ssh
    mock_stdout = mock.MagicMock()
    mock_stderr = mock.MagicMock()
    mock_stdout.read.return_value = b"VSAN is not enabled"
    mock_stderr.read.return_value = b""
    mock_stdout.channel.recv_exit_status.return_value = 1
    mock_ssh.exec_command.return_value = (None, mock_stdout, mock_stderr)

    out = self.client.execute_ssh_command("esxcli vsan cluster get")
    self.assertEqual(out, "VSAN is not enabled")

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_connection_error_raises_retryable(
      self, mock_paramiko
  ):
    """Verifies RetryableError on SSH socket failure or timeout."""
    mock_ssh = mock.MagicMock()
    mock_paramiko.SSHClient.return_value = mock_ssh
    mock_ssh.connect.side_effect = TimeoutError("SSH Connection timed out")

    with self.assertRaises(models.RetryableError) as ctx:
      self.client.execute_ssh_command("uname -a")
    self.assertIn("Failed to connect via SSH to ESXi host", str(ctx.exception))

  @mock.patch("clients.esxi_client.paramiko")
  def test_execute_ssh_command_execution_error_raises_retryable(
      self, mock_paramiko
  ):
    """Verifies RetryableError on SSH command execution timeout or failure."""
    mock_ssh = mock.MagicMock()
    mock_paramiko.SSHClient.return_value = mock_ssh
    mock_ssh.exec_command.side_effect = TimeoutError("Command timed out")

    with self.assertRaises(models.RetryableError) as ctx:
      self.client.execute_ssh_command("uname -a")
    self.assertIn("SSH execution failure on host", str(ctx.exception))

  @mock.patch("clients.esxi_client.vim")
  @mock.patch.object(esxi_client.ESXiClient, "connect_pyvmomi")
  def test_get_host_system_success(self, mock_connect, mock_vim):
    """Verifies retrieving HostSystem object reference."""
    mock_vim.HostSystem = "HostSystem"
    mock_si = mock.MagicMock()
    mock_connect.return_value = mock_si
    mock_host_sys = mock.MagicMock()
    mock_container = mock.MagicMock()
    mock_container.view = [mock_host_sys]
    mock_si.RetrieveContent.return_value.viewManager.CreateContainerView.return_value = (
        mock_container
    )

    host = self.client.get_host_system()
    self.assertEqual(host, mock_host_sys)
    mock_container.Destroy.assert_called_once()

    # Cached host system returned on subsequent call
    host_cached = self.client.get_host_system()
    self.assertEqual(host_cached, mock_host_sys)

  @mock.patch("clients.esxi_client.vim")
  @mock.patch.object(esxi_client.ESXiClient, "connect_pyvmomi")
  def test_get_host_system_empty_inventory_raises_non_retryable(
      self, mock_connect, mock_vim
  ):
    """Verifies NonRetryableError when no HostSystem exists in inventory."""
    mock_vim.HostSystem = "HostSystem"
    mock_si = mock.MagicMock()
    mock_connect.return_value = mock_si
    mock_container = mock.MagicMock()
    mock_container.view = []
    mock_si.RetrieveContent.return_value.viewManager.CreateContainerView.return_value = (
        mock_container
    )

    with self.assertRaises(models.NonRetryableError) as ctx:
      self.client.get_host_system()
    self.assertIn("No HostSystem found in ESXi inventory", str(ctx.exception))
    mock_container.Destroy.assert_called_once()

  @mock.patch.object(esxi_client.ESXiClient, "get_host_system")
  def test_get_network_system_success(self, mock_get_host):
    """Verifies retrieving HostNetworkSystem reference."""
    mock_host = mock.MagicMock()
    mock_net_sys = mock.MagicMock()
    mock_host.configManager.networkSystem = mock_net_sys
    mock_get_host.return_value = mock_host

    net_sys = self.client.get_network_system()
    self.assertEqual(net_sys, mock_net_sys)

  @mock.patch.object(esxi_client.ESXiClient, "get_host_system")
  def test_get_network_system_missing_raises_non_retryable(self, mock_get_host):
    """Verifies NonRetryableError when networkSystem is None."""
    mock_host = mock.MagicMock()
    mock_host.configManager.networkSystem = None
    mock_get_host.return_value = mock_host

    with self.assertRaises(models.NonRetryableError) as ctx:
      self.client.get_network_system()
    self.assertIn("HostNetworkSystem not accessible", str(ctx.exception))

  @mock.patch.object(esxi_client.ESXiClient, "get_host_system")
  def test_get_account_manager_success(self, mock_get_host):
    """Verifies retrieving HostLocalAccountManager reference."""
    mock_host = mock.MagicMock()
    mock_account_mgr = mock.MagicMock()
    mock_host.configManager.accountManager = mock_account_mgr
    mock_get_host.return_value = mock_host

    account_mgr = self.client.get_account_manager()
    self.assertEqual(account_mgr, mock_account_mgr)

  @mock.patch.object(esxi_client.ESXiClient, "connect_pyvmomi")
  @mock.patch.object(esxi_client.ESXiClient, "get_host_system")
  def test_get_resource_pool_and_folder_success(
      self, mock_get_host, mock_connect
  ):
    """Verifies resolving resource pool and VM folder from rootFolder childEntity."""
    mock_host = mock.MagicMock()
    mock_pool = mock.MagicMock()
    mock_host.parent.resourcePool = mock_pool
    mock_get_host.return_value = mock_host

    mock_si = mock.MagicMock()
    mock_connect.return_value = mock_si
    mock_folder = mock.MagicMock()
    mock_child = mock.MagicMock()
    mock_child.vmFolder = mock_folder
    mock_si.RetrieveContent.return_value.rootFolder.childEntity = [mock_child]

    pool, folder = self.client.get_resource_pool_and_folder()
    self.assertEqual(pool, mock_pool)
    self.assertEqual(folder, mock_folder)

  @mock.patch("clients.esxi_client.connect")
  def test_disconnect_session(self, mock_connect):
    """Verifies clean session termination upon disconnect."""
    self.client._service_instance = mock.MagicMock()
    self.client.disconnect()
    mock_connect.Disconnect.assert_called_once()
    self.assertIsNone(self.client._service_instance)


if __name__ == "__main__":
  unittest.main()
