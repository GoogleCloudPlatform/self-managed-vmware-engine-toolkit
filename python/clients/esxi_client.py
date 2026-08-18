"""ESXi interaction helper module.

Provides unified connection management and command execution wrapping VMware
pyVmomi (vSphere automation over port 443) and SSH (Paramiko/Netmiko supporting
standard ASCII and PAM keyboard-interactive authentication challenges).
"""

# pylint: disable=unused-argument

import logging
import shlex
import ssl
from typing import Any, List, Optional, Tuple

import constants
import models

try:
  import paramiko
except ImportError:
  paramiko = None

try:
  from pyVim import connect
  from pyVmomi import vim
except ImportError:
  connect = None
  vim = None


logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class ESXiClient:
  """Unified client for standalone ESXi host interaction via pyVmomi and SSH."""

  def __init__(
      self,
      host_ip: str,
      user: str,
      password: str,
      fallback_password: Optional[str] = None,
  ) -> None:
    """Initializes ESXi connection target and credentials.

    Args:
        host_ip: Primary internal IP address or reachable hostname of the host.
        user: Account username (typically 'root').
        password: Active ASCII root password for authentication.
        fallback_password: Optional secondary password to attempt if primary
          authentication encounters invalid credentials (e.g. rotated root password).
    """
    self.host_ip = host_ip
    self.user = user
    self.password = password
    self.fallback_password = fallback_password
    self._service_instance = None
    self._host_system = None
    self._ssh_client = None
    logger.debug(
        "Initialized ESXiClient targeting host %s with user '%s' (fallback"
        " password provided: %s)",
        self.host_ip,
        self.user,
        bool(fallback_password),
    )

  def _is_auth_error(self, exc: Exception) -> bool:
    """Returns True if exception represents an authentication / credentials failure."""
    exc_str = str(exc)
    exc_type = type(exc).__name__
    auth_cls = getattr(paramiko, "AuthenticationException", None)
    if isinstance(auth_cls, type) and isinstance(exc, auth_cls):
      return True
    return (
        "Cannot authenticate" in exc_str
        or "401" in exc_str
        or "403" in exc_str
        or "InvalidLogin" in exc_str
        or "InvalidLogin" in exc_type
        or "AuthenticationException" in exc_type
        or "Authentication failed" in exc_str
    )

  def _smart_connect(self, password: str) -> Any:
    """Connects to pyVmomi using the designated password."""
    if hasattr(connect, "SmartConnectNoSSL"):
      return connect.SmartConnectNoSSL(
          host=self.host_ip,
          user=self.user,
          pwd=password,
          port=constants.NetworkingDefaults.HTTPS_PORT,
      )
    ssl_ctx = (
        ssl._create_unverified_context()
        if hasattr(ssl, "_create_unverified_context")
        else None
    )
    return connect.SmartConnect(
        host=self.host_ip,
        user=self.user,
        pwd=password,
        port=constants.NetworkingDefaults.HTTPS_PORT,
        sslContext=ssl_ctx,
    )

  def connect_pyvmomi(self) -> Any:
    """Establishes an authenticated pyVmomi connection to ESXi host port 443.

    Attempts connection with primary password. If authentication fails and a
    fallback password is provided, attempts fallback authentication.

    Returns:
        pyVim.connect ServiceInstance object.

    Raises:
        models.NonRetryableError: On 401/403 credential failure or missing pkg.
        models.RetryableError: On transient socket network error or timeout.
    """
    if self._service_instance:
      return self._service_instance

    logger.debug(
        "Connecting to pyVmomi API on https://%s:%d/sdk",
        self.host_ip,
        constants.NetworkingDefaults.HTTPS_PORT,
    )
    try:
      si = self._smart_connect(self.password)
      self._service_instance = si
      return si
    except Exception as exc:  # pylint: disable=broad-exception-caught
      if (
          self._is_auth_error(exc)
          and self.fallback_password
          and self.fallback_password != self.password
      ):
        logger.warning(
            "Primary password authentication failed on ESXi host '%s'."
            " Retrying with fallback password...",
            self.host_ip,
        )
        try:
          si = self._smart_connect(self.fallback_password)
          self._service_instance = si
          self.password = self.fallback_password
          return si
        except Exception as fb_exc:  # pylint: disable=broad-exception-caught
          if self._is_auth_error(fb_exc):
            raise models.NonRetryableError(
                f"Authentication failed on ESXi host '{self.host_ip}' with"
                " both primary and fallback passwords."
            ) from fb_exc
          raise models.RetryableError(
              "Failed to connect to ESXi pyVmomi API at"
              f" '{self.host_ip}' with fallback password."
          ) from fb_exc

      if self._is_auth_error(exc):
        raise models.NonRetryableError(
            f"Authentication failed on ESXi host '{self.host_ip}'."
        ) from exc
      raise models.RetryableError(
          f"Failed to connect to ESXi pyVmomi API at '{self.host_ip}'."
      ) from exc

  def execute_esxcli(self, args: List[str]) -> str:
    """Executes an esxcli command array on the target ESXi host.

    Args:
        args: List of command arguments (e.g. ['vsan', 'cluster', 'get']).

    Returns:
        Output string response from command execution.
    """
    command_str = "esxcli " + " ".join(shlex.quote(a) for a in args)
    logger.debug("Executing esxcli command on host: %s", command_str)
    return self.execute_ssh_command(command_str)

  def execute_ssh_command(
      self,
      command: str,
      timeout_seconds: int = constants.NetworkingDefaults.SSH_TIMEOUT_SECONDS,
  ) -> str:
    """Executes a command over SSH.

    Args:
        command: Shell command line string to execute on ESXi host.
        timeout_seconds: Max command duration before raising timeout error.

    Returns:
        Full stdout string decoded from the command execution.

    Raises:
        models.DeployerError: If command fails or SSH connection errors.
    """
    logger.debug(
        "Executing SSH command on %s: %s",
        self.host_ip,
        command,
    )
    if not paramiko:
      raise models.NonRetryableError(
          "paramiko package is not installed in interpreter."
      )

    passwords_to_try = [self.password]
    if self.fallback_password and self.fallback_password not in passwords_to_try:
      passwords_to_try.append(self.fallback_password)

    last_auth_error = None
    ssh = None

    for pwd in passwords_to_try:
      client = paramiko.SSHClient()
      client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
      try:
        client.connect(
            hostname=self.host_ip,
            port=constants.NetworkingDefaults.SSH_PORT,
            username=self.user,
            password=pwd,
            allow_agent=False,
            look_for_keys=False,
            timeout=timeout_seconds,
        )
        ssh = client
        self.password = pwd
        break
      except Exception as exc:  # pylint: disable=broad-exception-caught
        if self._is_auth_error(exc):
          last_auth_error = exc
          if (
              self.fallback_password
              and pwd != self.fallback_password
          ):
            logger.warning(
                "SSH authentication failed on '%s' with primary password."
                " Retrying with fallback password...",
                self.host_ip,
            )
          continue
        raise models.RetryableError(
            f"Failed to connect via SSH to ESXi host '{self.host_ip}': {exc}"
        ) from exc

    if not ssh:
      raise models.NonRetryableError(
          f"SSH authentication failed on ESXi host '{self.host_ip}'."
      ) from last_auth_error

    try:
      _, stdout, stderr = ssh.exec_command(command, timeout=timeout_seconds)
      out = stdout.read().decode("utf-8", errors="replace")
      err = stderr.read().decode("utf-8", errors="replace")
      exit_code = stdout.channel.recv_exit_status()
      if exit_code != 0 and "vsan cluster get" not in command:
        logger.error(
            "SSH command '%s' failed on %s (exit %d): %s",
            command,
            self.host_ip,
            exit_code,
            err,
        )
        raise models.NonRetryableError(
            f"SSH command '{command}' failed with exit code {exit_code}:"
            f" {err or out}"
        )
      return out
    except Exception as exc:  # pylint: disable=broad-exception-caught
      if isinstance(exc, (models.ValidationError, models.NonRetryableError)):
        raise exc
      raise models.RetryableError(
          f"SSH execution failure on host '{self.host_ip}': {exc}"
      ) from exc
    finally:
      try:
        ssh.close()
      except Exception:  # pylint: disable=broad-exception-caught
        pass

  def get_host_system(self) -> Any:
    """Retrieves the root HostSystem managed object reference via pyVmomi."""
    if self._host_system:
      return self._host_system
    si = self.connect_pyvmomi()
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True
    )
    try:
      hosts = container.view
      if not hosts:
        raise models.NonRetryableError(
            f"No HostSystem found in ESXi inventory for {self.host_ip}"
        )
      self._host_system = hosts[0]
      return self._host_system
    finally:
      container.Destroy()

  def get_network_system(self) -> Any:
    """Retrieves HostNetworkSystem (networkSystem) for port group control."""
    host = self.get_host_system()
    network_system = getattr(host.configManager, "networkSystem", None)
    if not network_system:
      raise models.NonRetryableError(
          f"HostNetworkSystem not accessible on ESXi host {self.host_ip}"
      )
    return network_system

  def get_account_manager(self) -> Any:
    """Retrieves HostLocalAccountManager (accountManager) for authentication."""
    host = self.get_host_system()
    account_mgr = getattr(host.configManager, "accountManager", None)
    if not account_mgr:
      raise models.NonRetryableError(
          f"HostLocalAccountManager not accessible on ESXi host {self.host_ip}"
      )
    return account_mgr

  def get_resource_pool_and_folder(self) -> Tuple[Any, Any]:
    """Resolves standalone root resource pool and VM folder.

    Returns:
        Tuple of (ResourcePool, Folder) managed object references.
    """
    host = self.get_host_system()
    resource_pool = getattr(host.parent, "resourcePool", None)

    si = self.connect_pyvmomi()
    content = si.RetrieveContent()
    folder = None

    for child in getattr(content.rootFolder, "childEntity", []) or []:
      if hasattr(child, "vmFolder"):
        folder = child.vmFolder
        break

    if not folder:
      parent = getattr(host, "parent", None)
      grandparent = getattr(parent, "parent", None) if parent else None
      if grandparent and hasattr(grandparent, "vmFolder"):
        folder = grandparent.vmFolder

    if not resource_pool or not folder:
      raise models.NonRetryableError(
          "Failed to resolve ResourcePool or VM Folder on ESXi host"
          f" '{self.host_ip}' (pool: {resource_pool}, folder: {folder})."
      )

    return resource_pool, folder

  def disconnect(self) -> None:
    """Terminates active pyVmomi connections cleanly."""
    if self._service_instance and connect and hasattr(connect, "Disconnect"):
      try:
        logger.debug(
            "Disconnecting ESXiClient pyVmomi session for host %s", self.host_ip
        )
        connect.Disconnect(self._service_instance)
      except Exception:  # pylint: disable=broad-exception-caught
        pass
      self._service_instance = None
      self._host_system = None
