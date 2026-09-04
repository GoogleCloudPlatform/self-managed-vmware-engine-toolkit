"""VCF Installer VM Deployment and Bootstrap Orchestrator module.

Combines VCF installer VirtualMachine lifecycle operations across Phase 2c
(streaming OVA direct URL NFC lease pulling), Phase 2d (vCenter-less OVF
extraConfig environment injection via ReconfigVM_Task), and Phase 2e
(idempotent power activation and guest networking telemetry polling).
"""

import logging
import ssl
import tarfile
import time
from typing import Any, Optional, Tuple
import urllib.request
import paramiko

from clients import esxi_client as esxi_client_mod
import constants
import models

try:
  from pyVmomi import vim
except ImportError:
  vim = None


logger = logging.getLogger(constants.DeployerDefaults.LOGGER_NAME)


class VMDeployer:
  """Unified lifecycle manager for VCF Installer VM import and bootstrapping."""

  def __init__(self, esxi: esxi_client_mod.ESXiClient) -> None:
    """Initializes VMDeployer with target ESXiClient wrapper.

    Args:
        esxi: Initialized ESXiClient connected to target hypervisor.
    """
    self.esxi = esxi

  # ============================================================================
  # Phase 2c: VCF Installer OVA Deployment
  # ============================================================================

  def deploy_ova(
      self,
      vcf_installer_ova_url: str,
      ssl_thumbprint: Optional[str],
      port_group_name: str,
      vcf_vm_name: str,
  ) -> Any:
    """Executes Phase 2c OVA deployment onto ESXi vSAN storage inventory.

    Step A: Resource Resolution - Acquires root resource pool ('ha-root-pool'),
            root VM folder ('ha-folder-vm'), target port group, and datastore.
    Step B: Idempotency Check - Queries viewManager for existing VirtualMachine
            matching vcf_vm_name. If present, logs notice and returns reference.
    Step C: Streaming OVF Descriptor Parsing - Connects via HTTP stream to
            extract OVA archive headers on-the-fly, reading the .ovf XML
            descriptor in memory without downloading .vmdk image files locally.
    Step D: Direct URL NFC Lease Pull - Invokes HttpNfcLeasePullFromUrls_Task
            instructing ESXi to pull .vmdk blocks directly from remote server.

    Args:
        vcf_installer_ova_url: Remote HTTP/GCS path to VCF installer OVA file.
        ssl_thumbprint: Captured SHA-256 SSL thumbprint of remote GCS depot.
        port_group_name: Standardized virtual port group label ("vlan-<ID>").
        vcf_vm_name: Deduplicated virtual machine appliance label.

    Returns:
        Managed object reference to the deployed or existing VirtualMachine.

    Raises:
        models.DeployerError: On lease pull error, missing storage, or OVF fail.
    """
    logger.info(
        "Phase 2c: Starting deployment of VM '%s' from %s...",
        vcf_vm_name,
        vcf_installer_ova_url,
    )
    self.esxi.connect_pyvmomi()

    # Step A: Resource Resolution
    res_pool, vm_folder, datastore, network = self._resolve_host_resources(
        port_group_name
    )

    # Step B: Idempotency Check
    existing_vm = self._check_vm_exists(vcf_vm_name)
    if existing_vm:
      logger.info(
          "Virtual Machine '%s' already exists in inventory; skipping OVA"
          " import.",
          vcf_vm_name,
      )
      return existing_vm

    # Step C: Streaming OVF Descriptor Parsing
    logger.info("Streaming OVA HTTP headers to extract .ovf XML descriptor...")
    ovf_xml = self._fetch_and_parse_ovf_descriptor(vcf_installer_ova_url)

    # Step D: Direct URL NFC Lease Pull
    logger.info("Initiating direct URL NFC lease pull to remote storage...")
    deployed_vm = self._execute_lease_pull(
        ovf_descriptor=ovf_xml,
        resource_pool=res_pool,
        vm_folder=vm_folder,
        datastore=datastore,
        network=network,
        ova_url=vcf_installer_ova_url,
        ssl_thumbprint=ssl_thumbprint,
        vcf_vm_name=vcf_vm_name,
    )

    logger.info(
        "Successfully deployed VM '%s' via streaming direct-URL NFC pull.",
        vcf_vm_name,
    )
    return deployed_vm

  def _resolve_host_resources(
      self, port_group_name: str
  ) -> Tuple[Any, Any, Any, Any]:
    """Resolves root pool, root VM folder, vSAN datastore, and port group network."""
    host = self.esxi.get_host_system()
    res_pool, vm_folder = self.esxi.get_resource_pool_and_folder()

    datastore = None
    for ds in getattr(host, "datastore", []) or []:
      if (
          getattr(ds, "name", "")
          == constants.VMDeployerDefaults.DEFAULT_DATASTORE_NAME
      ):
        datastore = ds
        break
    if not datastore and getattr(host, "datastore", None):
      datastore = host.datastore[0]

    if not datastore:
      raise models.ValidationError(
          f"vsanDatastore not located on ESXi host {self.esxi.host_ip}."
      )

    network = None
    for net in getattr(host, "network", []) or []:
      if getattr(net, "name", "") == port_group_name:
        network = net
        break

    if not network:
      raise models.ValidationError(
          f"Port group '{port_group_name}' not found in ESXi host network"
          " inventory."
      )

    return res_pool, vm_folder, datastore, network

  def _check_vm_exists(self, vcf_vm_name: str) -> Optional[Any]:
    """Queries container view for VirtualMachine instances matching vcf_vm_name."""
    si = self.esxi.connect_pyvmomi()
    content = si.RetrieveContent()
    if not vim:
      return None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.VirtualMachine], True
    )
    try:
      for vm_ref in container.view:
        if getattr(vm_ref, "name", "") == vcf_vm_name:
          return vm_ref
      return None
    finally:
      container.Destroy()

  def _fetch_and_parse_ovf_descriptor(self, ova_url: str) -> str:
    """Opens streaming HTTP connection to parse TAR headers and extract OVF XML."""
    try:
      headers = {"User-Agent": constants.VMDeployerDefaults.HTTP_USER_AGENT}
      req = urllib.request.Request(ova_url, headers=headers)
      ssl_ctx = (
          ssl._create_unverified_context()
          if hasattr(ssl, "_create_unverified_context")
          else None
      )
      with urllib.request.urlopen(
          req,
          context=ssl_ctx,
          timeout=constants.NetworkingDefaults.HTTP_TIMEOUT_SECONDS,
      ) as resp:
        if resp.status != 200:
          raise models.NonRetryableError(
              f"HTTP fetch failed for OVF descriptor from '{ova_url}': status"
              f" {resp.status}"
          )
        with tarfile.open(fileobj=resp, mode="r|*") as tar:
          for member in tar:
            if member.isfile() and member.name.endswith(".ovf"):
              ovf_file = tar.extractfile(member)
              if ovf_file:
                return ovf_file.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pylint: disable=broad-exception-caught
      if isinstance(exc, (models.ValidationError, models.NonRetryableError)):
        raise exc
      raise models.RetryableError(
          f"Failed to stream and parse .ovf descriptor from '{ova_url}': {exc}"
      ) from exc

    raise models.NonRetryableError(
        f"No .ovf descriptor file located in OVA archive at '{ova_url}'."
    )

  def _execute_lease_pull(
      self,
      ovf_descriptor: str,
      resource_pool: Any,
      vm_folder: Any,
      datastore: Any,
      network: Any,
      ova_url: str,
      ssl_thumbprint: Optional[str],
      vcf_vm_name: str,
  ) -> Any:
    """Creates vApp import spec, starts NFC lease, and invokes HttpNfcLeasePull."""
    if not vim:
      raise models.NonRetryableError("pyVmomi package is not installed.")

    si = self.esxi.connect_pyvmomi()
    ovf_mgr = si.RetrieveContent().ovfManager

    # Dynamically inspect OVF descriptor to extract logical network names from <NetworkSection>
    pdp = vim.OvfManager.ParseDescriptorParams()
    desc_result = ovf_mgr.ParseDescriptor(ovf_descriptor, pdp)
    if getattr(desc_result, "error", None):
      logger.warning(
          "ParseDescriptor encountered warnings/errors inspecting OVF"
          " descriptor: %s",
          desc_result.error,
      )

    raw_networks = getattr(desc_result, "network", None)
    if not raw_networks or not isinstance(raw_networks, (list, tuple)):
      error_msg = (
          f"No logical networks found in OVF descriptor for VM '{vcf_vm_name}'."
      )
      if getattr(desc_result, "error", None):
        error_msg += f" Parse errors: {desc_result.error}"
      raise models.NonRetryableError(error_msg)

    logical_networks: List[str] = [
        item.name
        for item in raw_networks
        if hasattr(item, "name") and item.name
    ]

    logger.info(
        "Configuring OVF network mapping for %d logical network(s): %s",
        len(logical_networks),
        logical_networks,
    )
    network_mappings = []
    for net_name in logical_networks:
      net_map = vim.OvfManager.NetworkMapping()
      net_map.name = net_name
      net_map.network = network
      network_mappings.append(net_map)

    params = vim.OvfManager.CreateImportSpecParams()
    params.entityName = vcf_vm_name
    params.diskProvisioning = (
        constants.VMDeployerDefaults.DISK_PROVISIONING_THIN
    )
    params.networkMapping = network_mappings

    import_spec = ovf_mgr.CreateImportSpec(
        ovf_descriptor, resource_pool, datastore, params
    )
    if getattr(import_spec, "error", None):
      raise models.NonRetryableError(
          f"Failed to create import spec for VM '{vcf_vm_name}':"
          f" {import_spec.error}"
      )

    lease = resource_pool.ImportVApp(
        spec=import_spec.importSpec, folder=vm_folder
    )

    # Wait for lease to become ready
    self._wait_for_nfc_lease_ready(lease)

    # Prepare file pull specifications
    file_items = getattr(import_spec, "fileItem", []) or []
    updated_files = []
    for item in file_items:
      src_file = vim.HttpNfcLease.SourceFile()
      src_file.targetDeviceId = item.deviceId
      src_file.url = ova_url
      src_file.sslThumbprint = ssl_thumbprint or ""
      src_file.memberName = item.path
      src_file.create = False
      updated_files.append(src_file)

    try:
      task = lease.HttpNfcLeasePullFromUrls_Task(files=updated_files)
      self._wait_for_task(task)
      # Capture VM entity reference before completing/destroying the lease
      vm_entity = getattr(getattr(lease, "info", None), "entity", None)
      lease.HttpNfcLeaseComplete()
    except Exception as exc:  # pylint: disable=broad-exception-caught
      try:
        lease.HttpNfcLeaseAbort()
      except Exception:  # pylint: disable=broad-exception-caught
        pass
      raise models.DeployerError(
          f"NFC lease pull task failed for VM '{vcf_vm_name}': {exc}"
      ) from exc

    if not vm_entity:
      vm_entity = self._check_vm_exists(vcf_vm_name)

    if not vm_entity:
      raise models.DeployerError(
          "Failed to resolve created VirtualMachine reference for"
          f" '{vcf_vm_name}'."
      )

    return vm_entity

  def _wait_for_nfc_lease_ready(
      self,
      lease: Any,
      timeout_seconds: int = (
          constants.VMDeployerDefaults.NFC_LEASE_TIMEOUT_SECONDS
      ),
  ) -> None:
    """Polls NFC lease state until ready or error."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
      state = getattr(lease, "state", None)
      if vim and state == vim.HttpNfcLease.State.ready:
        return
      if vim and state == vim.HttpNfcLease.State.error:
        err_msg = getattr(
            getattr(lease, "error", None), "localizedMessage", "Lease Error"
        )
        raise models.DeployerError(f"NFC lease failed: {err_msg}")
      time.sleep(
          constants.VMDeployerDefaults.NFC_LEASE_POLL_INTERVAL_SECONDS
      )
    raise models.RetryableError(
        "Timed out waiting for NFC lease to reach ready state."
    )

  def _wait_for_task(
      self,
      task: Any,
      timeout_seconds: int = constants.VMDeployerDefaults.TASK_TIMEOUT_SECONDS,
  ) -> None:
    """Polls pyVmomi Task object until completion."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
      info = getattr(task, "info", None)
      if info:
        if info.state == "success":
          return
        if info.state == "error":
          err_obj = getattr(info, "error", None)
          err_msg = (
              getattr(err_obj, "localizedMessage", None)
              or getattr(err_obj, "msg", None)
              or str(err_obj)
              or "Task Failed"
          )
          logger.error(
              "Task error details: %s (error object: %r)", err_msg, err_obj
          )
          raise models.DeployerError(f"Task failed: {err_msg}")
      time.sleep(constants.VMDeployerDefaults.TASK_POLL_INTERVAL_SECONDS)
    raise models.RetryableError("Timed out waiting for task completion.")

  # ============================================================================
  # Phase 2d: OVF Environment Configuration
  # ============================================================================

  def configure_ovf_environment(
      self,
      vm_reference: Any,
      sddc_manager_ip: str,
      gateway: str,
      netmask: str,
      root_pwd: str,
      local_pwd: str,
      fqdn: str,
      domain: str,
      searchpath: str,
      dns_server: Optional[str] = None,
  ) -> None:
    """Executes Phase 2d OVF environment configuration injection for deployed VM."""
    logger.info(
        "Phase 2d: Configuring OVF properties for appliance '%s' (%s)...",
        fqdn,
        sddc_manager_ip,
    )
    self.esxi.connect_pyvmomi()

    effective_dns_server = (
        dns_server
        if dns_server
        else constants.NetworkingDefaults.DEFAULT_METADATA_SERVER
    )

    clean_domain = domain.rstrip(".") if domain else domain
    effective_ntp_server = (
        f"ntp.{clean_domain}"
        if clean_domain
        else constants.NetworkingDefaults.DEFAULT_METADATA_SERVER
    )

    xml_payload = self._marshal_ovf_properties(
        sddc_manager_ip=sddc_manager_ip,
        gateway=gateway,
        netmask=netmask,
        root_pwd=root_pwd,
        local_pwd=local_pwd,
        fqdn=fqdn,
        domain=domain,
        searchpath=searchpath,
        ntp_server=effective_ntp_server,
        dns_server=effective_dns_server,
    )

    self._inject_guestinfo(vm_reference, xml_payload)
    logger.info("Successfully configured and injected OVF environment into VM.")

  def _marshal_ovf_properties(
      self,
      sddc_manager_ip: str,
      gateway: str,
      netmask: str,
      root_pwd: str,
      local_pwd: str,
      fqdn: str,
      domain: str,
      searchpath: str,
      ntp_server: Optional[str] = None,
      dns_server: str = constants.NetworkingDefaults.DEFAULT_METADATA_SERVER,
  ) -> str:
    """Constructs OVF environment XML string with network and auth properties."""
    clean_domain = domain.rstrip(".") if domain else domain
    effective_ntp_server = (
        ntp_server
        if ntp_server
        else (
            f"ntp.{clean_domain}"
            if clean_domain
            else constants.NetworkingDefaults.DEFAULT_METADATA_SERVER
        )
    )
    env_props = [
        (constants.OVFPropertyKeys.ROOT_PASSWORD, root_pwd),
        (constants.OVFPropertyKeys.LOCAL_USER_PASSWORD, local_pwd),
        (constants.OVFPropertyKeys.VAMI_HOSTNAME, fqdn),
        (constants.OVFPropertyKeys.GUESTINFO_NTP, effective_ntp_server),
        (constants.OVFPropertyKeys.VAMI_IP0_SDDC_MANAGER, sddc_manager_ip),
        (constants.OVFPropertyKeys.VAMI_NETMASK0_SDDC_MANAGER, netmask),
        (constants.OVFPropertyKeys.VAMI_GATEWAY_SDDC_MANAGER, gateway),
        (constants.OVFPropertyKeys.VAMI_DOMAIN_SDDC_MANAGER, domain),
        (constants.OVFPropertyKeys.VAMI_SEARCHPATH_SDDC_MANAGER, searchpath),
        (constants.OVFPropertyKeys.VAMI_DNS_SDDC_MANAGER, dns_server),
    ]
    props_xml = "".join(
        f'<Property oe:key="{key}" oe:value="{val}"/>' for key, val in env_props
    )
    xml_str = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Environment xmlns="http://schemas.dmtf.org/ovf/environment/1"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:oe="http://schemas.dmtf.org/ovf/environment/1"'
        ' xmlns:ve="http://www.vmware.com/schema/ovfenv"'
        f' oe:id="" ve:esxId="{fqdn}">'
        f"<PropertySection>{props_xml}</PropertySection>"
        "</Environment>"
    )
    return xml_str

  def _inject_guestinfo(self, vm_reference: Any, xml_payload: str) -> None:
    """Appends 'guestinfo.ovfEnv' and 'guestinfo.ovfEnv/len' via ReconfigVM_Task."""
    if not vim:
      raise models.NonRetryableError("pyVmomi package is not installed.")

    payload_len = str(len(xml_payload.encode("utf-8")))
    logger.debug(
        "Injecting guestinfo.ovfEnv (length: %s bytes) via ReconfigVM_Task...",
        payload_len,
    )

    opt_env = vim.option.OptionValue()
    opt_env.key = constants.VMDeployerDefaults.GUESTINFO_OVF_ENV
    opt_env.value = xml_payload

    opt_len = vim.option.OptionValue()
    opt_len.key = constants.VMDeployerDefaults.GUESTINFO_OVF_ENV_LEN
    opt_len.value = payload_len

    spec = vim.vm.ConfigSpec()
    spec.extraConfig = [opt_env, opt_len]

    task = vm_reference.ReconfigVM_Task(spec=spec)
    self._wait_for_task(task)

  # ============================================================================
  # Phase 2e: VM Power On & IP Acquisition Monitoring
  # ============================================================================

  def power_on_and_wait_for_ip(
      self,
      vm_reference: Any,
      target_ip: str,
      poll_interval_seconds: int = (
          constants.DeployerDefaults.POWER_ON_POLL_INTERVAL_SECONDS
      ),
      timeout_seconds: int = (
          constants.DeployerDefaults.POWER_ON_TIMEOUT_SECONDS
      ),
  ) -> None:
    """Executes Phase 2e VM power-on initialization and IP address readiness check."""
    logger.info(
        "Phase 2e: Initiating power management and IP check for %s...",
        target_ip,
    )
    self.esxi.connect_pyvmomi()

    self._power_on_vm(vm_reference)
    self._poll_for_guest_ip(
        vm_reference=vm_reference,
        target_ip=target_ip,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    logger.info(
        "VM successfully initialized and verified accessible at IP %s.",
        target_ip,
    )

  def _power_on_vm(self, vm_reference: Any) -> None:
    """Inspects runtime power state and invokes PowerOnVM_Task if VM is off."""
    state = getattr(getattr(vm_reference, "runtime", None), "powerState", None)
    if vim and state == vim.VirtualMachinePowerState.poweredOn:
      logger.info("VM is already powered on.")
      return

    logger.info("Powering on VM via PowerOnVM_Task...")
    task = vm_reference.PowerOnVM_Task()
    self._wait_for_task(task)

  def _poll_for_guest_ip(
      self,
      vm_reference: Any,
      target_ip: str,
      poll_interval_seconds: int,
      timeout_seconds: int,
  ) -> None:
    """Loops monitoring guest networking telemetry until matching IP appears."""
    logger.info(
        "Polling VMware tools telemetry for IPv4 '%s' (Max timeout: %d s)...",
        target_ip,
        timeout_seconds,
    )
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
      guest = getattr(vm_reference, "guest", None)
      if guest:
        ip_addr = getattr(guest, "ipAddress", None)
        if ip_addr:
          logger.info("Guest tools reported IP address: %s", ip_addr)
          if not target_ip or ip_addr == target_ip:
            return
        # Inspect guest interfaces array
        for net_if in getattr(guest, "net", []) or []:
          for ip_obj in getattr(net_if, "ipAddress", []) or []:
            if ip_obj == target_ip:
              logger.info("Target IP %s matched on guest interface.", target_ip)
              return
      time.sleep(poll_interval_seconds)

    raise models.RetryableError(
        f"Timed out after {timeout_seconds}s waiting for guest to acquire IP"
        f" '{target_ip}'."
    )

  def bypass_vcf_hcl_disk_validation(
    vcf_ip: str,
    root_password: str,
    timeout_seconds: int = 180,
    poll_interval_seconds: int = 5,
  ) -> None:
    """Injects bypass properties into VCF Cloud Builder and restarts vcf-bringup.
    Bypasses the 'All disks claimed by vSAN' / HCL eligibility error on Node 0.
    Args:
        vcf_ip: SDDC Manager / Cloud Builder appliance IP.
        root_password: Root password for the VCF appliance.
        timeout_seconds: Max seconds to wait for SSH connectivity.
        poll_interval_seconds: Polling interval between SSH attempts.
    """
    logger.info("Connecting to VCF appliance at %s to inject HCL bypass...", vcf_ip)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # 1. Wait for SSH daemon to become ready on Cloud Builder
    start_time = time.time()
    connected = False
    while time.time() - start_time < timeout_seconds:
      try:
        client.connect(
            hostname=vcf_ip,
            username="root",
            password=root_password,
            timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )
        connected = True
        logger.info("SSH connection established to %s.", vcf_ip)
        break
      except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug("Waiting for VCF SSH daemon (%s)...", exc)
        time.sleep(poll_interval_seconds)
    if not connected:
      raise TimeoutError(
          f"Timed out after {timeout_seconds}s waiting for SSH on VCF appliance {vcf_ip}."
      )
    try:
      # 2. Append bypass properties to Cloud Builder configuration
      properties_to_add = [
          "vsan.esa.sddc.managed.disk.claim=true",
          "sos.hcl.validation=false",
      ]
      target_files = [
          "/opt/vmware/bringup/web/conf/application-prod.properties",
          "/etc/vmware/vcf/bringup/conf/application.properties",
      ]
      for conf_path in target_files:
        for prop in properties_to_add:
          # Idempotently append property only if not already present
          cmd = (
              f"test -f {conf_path} && "
              f"! grep -q '^{prop.split('=')[0]}' {conf_path} && "
              f"echo '{prop}' >> {conf_path} || true"
          )
          _, stdout, stderr = client.exec_command(cmd)
          stdout.channel.recv_exit_status()
      logger.info("Bypass properties injected. Restarting vcf-bringup service...")
      # 3. Restart the bringup service to pick up the updated properties
      restart_cmd = "systemctl restart vcf-bringup"
      _, stdout, stderr = client.exec_command(restart_cmd)
      exit_status = stdout.channel.recv_exit_status()
      if exit_status != 0:
        err = stderr.read().decode("utf-8")
        raise RuntimeError(f"Failed to restart vcf-bringup: {err}")
      logger.info("vcf-bringup restarted successfully with HCL bypass enabled.")
    finally:
      client.close()
