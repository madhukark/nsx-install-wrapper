#!/usr/bin/env python
################################################################################
#
# Copyright 2020 VMware, Inc.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; # LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, # WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, # EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
################################################################################
################################################################################
#
# nsx-install.py
#
# Script to install NSX. Does the following
#   - Install NSX Manager clsuter (3 Nodes)
#   - Configures NSX Manager with vCenter Server
#   - Deploys Edges
#   - Creates T0 Gateway
#   - Creates Host Switch Profile
#   - Configures Host Transport Nodes
#   - Adds provided license and accepts EULA
#
# Usage:
#   usage: nsx-install.py [-h] [--start] [--reset-defaults] [--reset-config]
#                         [--manual]
#   
#   Install NSX
#   
#   optional arguments:
#     -h, --help        show this help message and exit
#     --start           Start the installation
#     --reset-defaults  Reset defaults to factory setting
#     --reset-config    Reset the config file
#     --manual          Manual install. Only generate the variables file
#
# Logs:
#   Default log file: nsx-install.log
#   All logs get appended. Log rotation not implemented.
################################################################################

import os
import sys
import json
import atexit
import logging
import argparse

from pyVmomi import vim, vmodl
from pyVim.connect import Disconnect, SmartConnectNoSSL, SmartConnect

#
# Global Variables
#

# Log file. Gets created if one doesnt exist.
# Note: All logs are appended. Log rotation is not implemented
g_logfile = "./nsx-install.log"

# Existing Defaults. Auto-generated based on hardcoded values
g_defaults = "./nsx-defaults.txt"

# User Configs. Generated based on user input
g_config = "./nsx-config.txt"

# Ansible folder
g_ans_root = "."

# Variables for Ansible run. Auto-generated
g_nsx_install_vars = g_ans_root + "/" + "nsx_pacific_vars.yml"

#
# Helper functions
#
def writeln(fd, key="", value="", comment="", example=""):
  fd.write ("\n# %s\n" % comment)
  if (example != ""):
    fd.write ("# Example: %s\n" % example)
  if (key == ""):
    return
  else:
    fd.write ("%s = \"%s\"\n" % (key, value))

def writeheader(fd, msg):
  fd.write ("\n#-------------------------------------------------------------------------------\n")
  fd.write ("# %s\n" % msg)
  fd.write ("#-------------------------------------------------------------------------------\n")


def run_playbook(playbook, wait=0):
  if (wait == 0):
    cmd = "ansible-playbook -vvvv %s >> %s 2>&1" % (playbook, g_logfile)
  else:
    cmd = "ansible-playbook -vvvv %s >> %s 2>&1 && sleep %s" % (playbook, g_logfile, wait)
  logging.debug ("Running command: %s" % cmd)
  ret = os.system (cmd)
  if (ret != 0):
    logging.error ("Could not run %s" % cmd)
    print ("Deployment exited with Error. Please check %s" % g_logfile)
    sys.exit (1)


def get_obj(content, vimtype, name):
    obj = None
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True
    )
    for c in container.view:
        if c.name == name:
            obj = c
            break
    return obj


def get_vds_uuid(vds_name, host, user, pwd):

  try:
    service_instance = SmartConnectNoSSL(host=host,
                                         user=user,
                                         pwd=pwd,
                                         port='443')
    atexit.register (Disconnect, service_instance)

    content = service_instance.RetrieveContent()

    # Get VDS object
    vds = get_obj (content, [vim.DistributedVirtualSwitch], vds_name)
    if vds is None:
      logging.error ("Distributed Switch: %s Not found in vCenter." % vds_name)
      print("ERROR: Distributed Switch: %s Not found in vCenter." % vds_name)
      sys.exit (2)

  except vmodl.MethodFault as error:
    logging.error ("Unable to connect to vCenter: Caught vmodl fault: {0}".format(error.msg))
    print ("Unable to connect to vCenter: Caught vmodl fault: {0}".format(error.msg))
    sys.exit (2)

  vds_uuid = vds.config.uuid
  logging.debug ("VDS %s has UUID: %s" % (vds_name, vds_uuid))

  return vds_uuid


#
# Reset the defaults to factory settings
#
def reset_defaults():
  logging.debug("Resetting Defaults")

  f = open (g_defaults, "w")
  writeln (f, comment = "Defaults\n")
  writeln (f, "nsx_username", "admin", "NSX Username")
  writeln (f, "validate_certs", "false", "Accept self-signed certs")
  writeln (f, "nsx_vcenter", "vSphere_NSX_deploy", "Display name of vCenter on which NSX will be deployed")
  writeln (f, "compute_manager_name", "vcenter", "Display Name on NSX Manager for the registered vCenter Server")
  writeln (f, "overlay_tz_name", "Overlay-TZ", "Overlay Transport Zone display name")
  writeln (f, "vlan_tz_name", "VLAN-TZ", "VLAN Transport Zone display name")
  writeln (f, "ip_pool_1_name", "Edge-TEP-IP-Pool", "IP Pool used by Edge Transport Nodes")
  writeln (f, "ip_pool_2_name", "Host-TEP-IP-Pool", "IP Pool used by Host Transport Nodes.")
  writeln (f, "edge_form_factor", "LARGE", "VM form factor for Edge Node deployments. Defaults to LARGE. Other choices are SMALL and MEDIUM")
  writeln (f, "edge1_host_switch_name", "nvds1", "Host Switch Name on Edge1")
  writeln (f, "edge1_display_name", "edge-01", "Display Name of Edge1 on NSX Manager")
  writeln (f, "edge2_host_switch_name", "nvds1", "Host Switch Name on Edge2")
  writeln (f, "edge2_display_name", "edge-02", "Display Name of Edge2 on NSX Manager")
  writeln (f, "edge_cluster_display_name", "Edge-Cluster", "Display name of the Edge Cluster")
  writeln (f, "edge_cluster_profile_binding", "nsx-default-edge-high-availability-profile", "Edge Cluster Profile Binding")
  writeln (f, "tier0_display_name", "vSphereK8sT0", "Tier0 display name")
  writeln (f, "host_switch_profile_name", "vSphereK8_uplink_profile", "Name of the Host Switch Uplink Profile")
  writeln (f, "host_switch_uplink1_name", "uplink-1", "Uplink1 Name used for Host switch teaming")
  writeln (f, "host_switch_uplink2_name", "uplink-2", "Uplink1 Name used for Host switch teaming")
  writeln (f, "host_switch_teaming_policy", "FAILOVER_ORDER", "Teaming policy. Choices are FAILOVER_ORDER, LOADBALANCE_SRCID or LOADBALANCE_SRC_MAC")
  writeln (f, "host_tnp_display_name", "vSphereK8_TNP", "Name of the Transport Node Profile configured on the Compute Clusters")
  writeln (f, "host_default_host_switch_profile", "nsx-default-uplink-hostswitch-profile", "Host Switch Profile used for Host Transport Node config")

  logging.debug("reset_defaults: Success")
  print ("Reseting defaults done.")
  

#
# Reset all User configs (erase all existing data)
#
def reset_config():
  logging.debug("reset_config: Started")
  
  f = open(g_config, "w")
  writeln (f, comment = "User Configuration\n")

  writeheader (f, "NSX OVA details")
  writeln (f, "nsx_ova_path", "", "Path where NSX OVA can be found on the local system", "/home/user/nsx_bits")
  writeln (f, "nsx_ova", "", "NSX OVA file name", "nsx-unified-appliance-3.0.ova")

  writeheader (f, "NSX Manager Cluster or Standalone deployment")
  writeln (f, "nsx_manager_cluster", "yes", "Deploy NSX Manager 3 node cluster. To deploy just 1 node, change to 'no'")

  writeheader (f, "Details applicable to all 3 NSX nodes")
  writeln (f, "nsx_password", "", "Password for admin and root accounts", "myPassword1!myPassword1!")
  writeln (f, "domain", "", "Domain name for NSX Manager cluster", "mylab.net")
  writeln (f, "netmask", "", "NSX Manager network netmask", "255.255.255.224")
  writeln (f, "gateway", "", "Gateway to be configured on NSX Manager", "192.168.1.1")
  writeln (f, "dns_server", "", "DNS Server to be configured on NSX Manager", "8.8.8.8")
  writeln (f, "ntp_server", "", "NTP Server to be configured on NSX Manager", "216.239. 35.0")
  writeln (f, "nsx_vcenter_fqdn", "", "vCenter where NSX Manager and Edges will be deployed", "10.10.10.2")
  writeln (f, "nsx_vcenter_username", "", "vCenter Username for NSX deployment", "administrator@vsphere.local")
  writeln (f, "nsx_vcenter_password", "", "vCenter Password for NSX deployment", "myPassword1!")

  writeheader (f, "First NSX Manager node deployment details")
  writeln (f, "node1_hostname", "", "FQDN of the first NSX Manager", "nsx1.mylab.net")
  writeln (f, "node1_mgmt_ip", "", "IP Address to be configured on the first NSX Manager", "192.168.1.10")
  writeln (f, "node1_datacenter", "", "vCenter Datacenter name where NSX Manager will be deployed", "Palo-Alto-Datacenter")
  writeln (f, "node1_cluster", "", "vCenter Cluster name where NSX Manager will be deployed", "Mgmt-Cluster")
  writeln (f, "node1_datastore", "", "vCenter Datastore where NSX Manager will be deployed", "datastore5")
  writeln (f, "node1_portgroup", "", "vCenter Network for the management interface of NSX Manager. This can be a standard portgroup or a distributed port group", "VM Network")

  writeheader (f, "Second NSX Manager deployment details")
  writeln (f, "node2_hostname", "", "FQDN of the second NSX Manager node", "nsx2.mylab.net")
  writeln (f, "node2_mgmt_ip", "", "Management IP Address to be configured on the second NSX Manager", "192.168.1.20")
  writeln (f, "node2_netmask_prefix", "", "Network prefix for the second NSX Manager", "24")
  writeln (f, "node2_datacenter", "", "vCenter Datacenter name where the second NSX Manager will be deployed", "Palo-Alto-Datacenter")
  writeln (f, "node2_cluster", "", "vCenter Cluster name where the second NSX Manager will be deployed", "Mgmt-Cluster")
  writeln (f, "node2_datastore", "", "vCenter Datastore where the second NSX Manager will be deployed", "datastore6")
  writeln (f, "node2_portgroup", "", "vCenter Network for the management interface of the second NSX Manager. This can be a standard portgroup or a distributed port group", "VM Network")

  writeheader (f, "Third NSX Manager deployment details")
  writeln (f, "node3_hostname", "", "FQDN of the third NSX Manager node", "nsx3.mylab.net")
  writeln (f, "node3_mgmt_ip", "", "Management IP Address to be configured on the third NSX Manager", "192.168.1.30")
  writeln (f, "node3_netmask_prefix", "", "Network prefix for the third NSX Manager", "24")
  writeln (f, "node3_datacenter", "", "vCenter Datacenter name where the third NSX Manager will be deployed", "Palo-Alto-Datacenter")
  writeln (f, "node3_cluster", "", "vCenter Cluster name where the third NSX Manager will be deployed", "Mgmt-Cluster")
  writeln (f, "node3_datastore", "", "vCenter Datastore where the third NSX Manager will be deployed", "datastore5")
  writeln (f, "node3_portgroup", "", "vCenter Network for the management interface of the third NSX Manager. This can be a standard portgroup or a distributed port group", "VM Network")

  writeheader (f, "vCenter to be registered as Compute Manager")
  writeln (f, "vcenter_fqdn", "", "FQDN or IP of the vCenter Server to be registered with NSX Manager", "vcenter.mylab.net")
  writeln (f, "vcenter_username", "", "vCenter username for authentication", "administrator@vsphere.local")
  writeln (f, "vcenter_password", "", "vCenter password for authentication", "myPassword1!")

  writeheader (f, "NSX License key")
  writeln (f, "nsx_license_key", "", "NSX License Key", "XXXX-YYYY-ZZZZ-1111-2222-3333-4444")

  writeheader (f, "TEP IP Pool for the Edge")
  writeln (f, "ip_pool_1_start", "", "Start address of the Edge TEP IP Pool range", "172.16.227.20")
  writeln (f, "ip_pool_1_end", "", "End address of the TEP IP Pool range", "172.16.226.29")
  writeln (f, "ip_pool_1_gateway", "", "Gateway for the TEP IP Pool", "172.16.227.1")
  writeln (f, "ip_pool_1_cidr", "", "TEP IP Pool Netmask in CIDR format", "172.16.227.0/27")

  writeheader (f, "TEP IP Pool for Host Nodes")
  writeln (f, "ip_pool_2_start", "", "Start address of the Host TEP IP Pool range", "172.16.227.20")
  writeln (f, "ip_pool_2_end", "", "End address of the Host TEP IP Pool range", "172.16.226.29")
  writeln (f, "ip_pool_2_gateway", "", "Gateway for the Host TEP IP Pool", "172.16.227.1")
  writeln (f, "ip_pool_2_cidr", "", "Host TEP IP Pool Netmask in CIDR format", "172.16.227.0/27")

  writeheader (f, "Edge 1 deployment details")
  writeln (f, "edge1_host_switch_profile_name", "","Host Switch Profile to be used on Edge1", "nsx-edge-single-nic-uplink-profile")
  writeln (f, "edge1_number_of_uplinks", "2", "Number of Uplinks on the Edge Node. Max: 2", "2")
  writeln (f, "edge1_cluster", "", "vCenter Cluster name where Edge1 will be deployed", "Management")
  writeln (f, "edge1_storage", "", "Datastore name where Edge1 will be deployed")
  writeln (f, "edge1_mgmt_network", "", "Port Group backing for the Management Cluster of Edge1", "VM Network")
  writeln (f, "edge1_mgmt_ip", "", "Management IP Address for Edge1", "192.168.1.50")
  writeln (f, "edge1_mgmt_netmask_prefix", "", "Network prefix on the Management Network", "24")
  writeln (f, "edge1_default_gateway", "", "Default Gateway to be configured on Edge1 Management Network", "192.168.1.1")
  writeln (f, "edge1_fqdn", "", "FQDN of Edge1", "edge1.mylab.net")
  writeln (f, "edge1_data_network", "", "Port Group backing for the data network on Edge1", "lab-dvpg")
  writeln (f, "edge1_system_password", "", "Edge1 CLI, root and audit user account passwords. The same password will be configured for all 3.", "myPassword1!myPassword1!")

  writeheader (f, "Edge 2 deployment details")
  writeln (f, "edge2_host_switch_profile_name", "","Host Switch Profile to be used on Edge2", "nsx-edge-single-nic-uplink-profile")
  writeln (f, "edge2_number_of_uplinks", "2", "Number of Uplinks on the Edge Node. Max: 2", "2")
  writeln (f, "edge2_cluster", "", "vCenter Cluster name where Edge2 will be deployed", "Management")
  writeln (f, "edge2_storage", "", "Datastore name where Edge2 will be deployed")
  writeln (f, "edge2_mgmt_network", "", "Port Group backing for the Management Cluster of Edge2", "VM Network")
  writeln (f, "edge2_mgmt_ip", "", "Management IP Address for Edge2", "192.168.1.50")
  writeln (f, "edge2_mgmt_netmask_prefix", "", "Network prefix on the Management Network", "24")
  writeln (f, "edge2_default_gateway", "", "Default Gateway to be configured on Edge2 Management Network", "192.168.1.1")
  writeln (f, "edge2_fqdn", "", "FQDN of Edge2", "edge1.mylab.net")
  writeln (f, "edge2_data_network", "", "Port Group backing for the data network on Edge2", "lab-dvpg")
  writeln (f, "edge2_system_password", "", "Edge2 CLI, root and audit user account passwords. The same password will be configured for all 3.", "myPassword1!myPassword1!")

  writeheader (f, "Tier0 Gateway Config")
  writeln (f, "Tier0_BGP_AS_Number", "", "BGP Neighbor AS number tobe configured on Tier0 Gateway", "1211")

  writeheader (f, "Host Switch Profile Settings")
  writeln (f, "host_switch_mtu", "", "MTU used for uplinks")
  writeln (f, "transport_vlan", "", "VLAN used for tagging Overlay traffic of associated HostSwitch")
  
  writeheader (f, "Host Transport Node Profile configurations")
  writeln (f, "host_vds_name", "", "VDS Name on vCenter server", "vds1")
  writeln (f, "host_number_of_uplinks", "2", "Number of Uplinks on the Host Node. Max: 2", "2")
  
  writeheader (f, "Compute Clusters to be Configured with NSX")
  writeln (f, "compute_clusters_for_prep", "", "Comma separated vSphere Compute Clusters to be Configured with NSX", "Cluster-A, Cluster-B, Cluster-C")

  logging.debug("reset_config: Success")
  print ("Reseting User Config done.")
  


#
# View existing Defaults
#
def view_defaults():
  logging.debug("view_defaults: Invoked. Not implemented yet")
  print("Not implemented yet")


#
# View existing config. if an existing Config file exists, then displays it
#
def view_config():
  logging.debug("view_config: Invoked. Not implemented yet")
  print("Not implemented yet")


def txt_to_json(filename):
  items = []
  jsondict = dict()
  for line in open(filename):
    line = line.strip()
    if not line.startswith('#') and line != '':
      items = line.split('=')
      jsondict[ items[0].strip() ] = items[1].strip().strip('"')
  return jsondict

#
# Reads the defaults and user config and generates the yml file
# that Ansible can consume
#
def generate_vars_file():
  logging.debug("generate_vars_file: Started")
  defaults = dict()
  config = dict()

  defaults = txt_to_json(g_defaults)
  config = txt_to_json(g_config)

#  for k in sorted(defaults.keys()):
#    print ("%s = %s" % (k, defaults[k]))
#  for k in sorted(config.keys()):
#    print ("%s" % k)

  nsx_vars = dict()

  nsx_vars ["state"] = "present"
  nsx_vars ["nsx_username"] = defaults ["nsx_username"]
  nsx_vars ["nsx_password"] = config ["nsx_password"]
  nsx_vars ["validate_certs"] = "False"
  nsx_vars ["nsx_ova_path"] = config ["nsx_ova_path"]
  nsx_vars ["nsx_ova"] = config ["nsx_ova"]
  nsx_vars ["domain"] = config ["domain"]
  nsx_vars ["netmask"] = config ["netmask"]
  nsx_vars ["gateway"] = config ["gateway"]
  nsx_vars ["dns_server"] = config ["dns_server"]
  nsx_vars ["ntp_server"] = config ["ntp_server"]

  nsx_vars ["nsx_vcenter_fqdn"] = config ["nsx_vcenter_fqdn"]
  nsx_vars ["nsx_vcenter_username"] = config ["nsx_vcenter_username"]
  nsx_vars ["nsx_vcenter_password"] = config ["nsx_vcenter_password"]

  node1 = dict()
  node1 ["hostname"] = config ["node1_hostname"]
  node1 ["mgmt_ip"] = config ["node1_mgmt_ip"]
  node1 ["datacenter"] = config ["node1_datacenter"]
  node1 ["cluster"] = config ["node1_cluster"]
  node1 ["datastore"] = config ["node1_datastore"]
  node1 ["portgroup"] = config ["node1_portgroup"] 
  nsx_vars ["nsx_node1"] = node1

  additional_nodes = list()
  node2 = dict()
  node2 ["hostname"] = config ["node2_hostname"]
  node2 ["mgmt_ip"] = config ["node2_mgmt_ip"]
  node2 ["prefix"] = config ["node2_netmask_prefix"]
  node2 ["datacenter"] = config ["node2_datacenter"]
  node2 ["cluster"] = config ["node2_cluster"]
  node2 ["datastore"] = config ["node2_datastore"]
  node2 ["portgroup"] = config ["node2_portgroup"]
  node2 ["vcenter"] = defaults ["nsx_vcenter"]
  node2 ["vcenter_user"] = config ["nsx_vcenter_username"]
  node2 ["vcenter_pass"] = config ["nsx_vcenter_password"]
  additional_nodes.append (node2)
  node3 = dict()
  node3 ["hostname"] = config ["node3_hostname"]
  node3 ["mgmt_ip"] = config ["node3_mgmt_ip"]
  node3 ["prefix"] = config ["node3_netmask_prefix"]
  node3 ["datacenter"] = config ["node3_datacenter"]
  node3 ["cluster"] = config ["node3_cluster"]
  node3 ["datastore"] = config ["node3_datastore"]
  node3 ["portgroup"] = config ["node3_portgroup"]
  node3 ["vcenter"] = defaults ["nsx_vcenter"]
  node3 ["vcenter_user"] = config ["nsx_vcenter_username"]
  node3 ["vcenter_pass"] = config ["nsx_vcenter_password"]
  additional_nodes.append (node3)
  nsx_vars ["additional_nodes"] = additional_nodes

  cm = list()
  cm1 = dict()
  cm1 ["display_name"] = defaults ["compute_manager_name"]
  cm1 ["mgmt_ip"] = config ["vcenter_fqdn"]
  cm1 ["origin_type"] = "vCenter"
  cm1 ["credential_type"] = "UsernamePasswordLoginCredential"
  cm1 ["username"] = config ["vcenter_username"]
  cm1 ["password"] = config ["vcenter_password"]
  cm1 ["set_as_oidc_provider"] = "true"
  cm.append (cm1)
  if (config["nsx_vcenter_fqdn"] != config["vcenter_fqdn"]):
    cm2 = dict()
    cm2 ["display_name"] = defaults ["nsx_vcenter"]
    cm2 ["mgmt_ip"] = config ["nsx_vcenter_fqdn"]
    cm2 ["origin_type"] = "vCenter"
    cm2 ["credential_type"] = "UsernamePasswordLoginCredential"
    cm2 ["username"] = config ["nsx_vcenter_username"]
    cm2 ["password"] = config ["nsx_vcenter_password"]
    cm2 ["set_as_oidc_provider"] = "false"
    cm.append (cm2)
  else:
    defaults ["nsx_vcenter"] = defaults ["compute_manager_name"]
  nsx_vars ["compute_managers"] = cm

  licences = list()
  license = dict()
  license ["license_key"] = config ["nsx_license_key"]
  licences.append (license)
  nsx_vars ["nsxt_licenses"] = licences

  tzs = list()
  tz1 = dict()
  tz1 ["display_name"] = defaults ["overlay_tz_name"]
  tz1 ["transport_type"] = "OVERLAY"
  tzs.append (tz1)
  tz2 = dict()
  tz2 ["display_name"] = defaults ["vlan_tz_name"]
  tz2 ["transport_type"] = "VLAN"
  tzs.append (tz2)
  nsx_vars ["transport_zones"] = tzs

  ip_pools = list()
  edge_pool = dict()
  edge_pool ["display_name"] = defaults ["ip_pool_1_name"]
  edge_pool_subnets = list()
  edge_pool_subnet = dict()
  edge_pool_subnet ["state"] = "present"
  edge_pool_subnet ["id"] = defaults ["ip_pool_1_name"] + "_subnets"
  edge_allocation_ranges = list()
  edge_ranges = dict()
  edge_ranges ["start"] = config ["ip_pool_1_start"]
  edge_ranges ["end"] = config ["ip_pool_1_end"]
  edge_allocation_ranges.append (edge_ranges)
  edge_pool_subnet ["allocation_ranges"] = edge_allocation_ranges
  edge_pool_subnet ["gateway_ip"] = config ["ip_pool_1_gateway"]
  edge_pool_subnet ["cidr"] = config ["ip_pool_1_cidr"]
  edge_pool_subnets.append (edge_pool_subnet)
  edge_pool ["pool_static_subnets"] = edge_pool_subnets
  ip_pools.append (edge_pool)

  host_pool = dict()
  host_pool ["display_name"] = defaults ["ip_pool_2_name"]
  host_pool_subnets = list()
  host_pool_subnet = dict()
  host_pool_subnet ["state"] = "present"
  host_pool_subnet ["id"] = defaults ["ip_pool_2_name"] + "_subnets"
  host_allocation_ranges = list()
  host_ranges = dict()
  host_ranges ["start"] = config ["ip_pool_2_start"]
  host_ranges ["end"] = config ["ip_pool_2_end"]
  host_allocation_ranges.append (host_ranges)
  host_pool_subnet ["allocation_ranges"] = host_allocation_ranges
  host_pool_subnet ["gateway_ip"] = config ["ip_pool_2_gateway"]
  host_pool_subnet ["cidr"] = config ["ip_pool_2_cidr"]
  host_pool_subnets.append (host_pool_subnet)
  host_pool ["pool_static_subnets"] = host_pool_subnets
  ip_pools.append (host_pool)
  nsx_vars ["ip_pools"] = ip_pools

  edge_tnp = list()
  edge1 = dict()
  host_switch_spec = dict()
  host_switch_spec ["resource_type"] = "StandardHostSwitchSpec"
  host_switches = list()
  host_switch = dict()
  host_switch ["host_switch_name"] = defaults ["edge1_host_switch_name"]
  host_switch ["host_switch_type"] = "NVDS"
  host_switch ["host_switch_mode"] = "STANDARD"
  host_switch_profiles = list()
  host_switch_profile = dict()
  host_switch_profile ["name"] = config ["edge1_host_switch_profile_name"]
  host_switch_profile ["type"] = "UplinkHostSwitchProfile"
  host_switch ["host_switch_profiles"] = host_switch_profiles
  pnics = list()
  if (int (config ["edge1_number_of_uplinks"]) > 2):
    logging.error ("Max allowed Edge Uplinks: 2. Configured: %s" % config ["edge1_number_of_uplinks"])
    print ("ERROR: Max allowed Edge Uplinks: 2. Configured: %s" % config ["edge1_number_of_uplinks"])
    sys.exit (2)
  for i in range (int (config ["edge1_number_of_uplinks"]) - 1):
    pnic = dict()
    if (i == 0):
      pnic ["device_name"] = "fp-eth0"
      pnic ["uplink_name"] = "uplink-1"
    elif (i == 1):
      pnic ["device_name"] = "fp-eth1"
      pnic ["uplink_name"] = "uplink-2"
    pnics.append (pnic)
  host_switch ["pnics"] = pnics
  ip_assignment_spec = dict()
  ip_assignment_spec ["resource_type"] = "StaticIpPoolSpec"
  ip_assignment_spec ["ip_pool_name" ] = defaults ["ip_pool_1_name"]
  host_switch ["ip_assignment_spec"] = ip_assignment_spec
  transport_zone_endpoints = list()
  tz = dict()
  tz ["transport_zone_name"] = defaults ["overlay_tz_name"]
  transport_zone_endpoints.append (tz)
  host_switch ["transport_zone_endpoints"] = transport_zone_endpoints
  host_switch_profiles.append (host_switch_profile)
  host_switches.append (host_switch)
  host_switch_spec ["host_switches"] = host_switches
  edge1 ["host_switch_spec"] = host_switch_spec
  node_dep_info = dict()
  node_dep_info ["deployment_type"] = "VIRTUAL_MACHINE"
  dep_config = dict()
  vm_dep_config = dict()
  vm_dep_config ["vc_name"] = defaults ["nsx_vcenter"]
  vm_dep_config ["vc_username"] = config ["nsx_vcenter_username"]
  vm_dep_config ["vc_password"] = config ["nsx_vcenter_password"]
  vm_dep_config ["compute"] = config ["edge1_cluster"]
  vm_dep_config ["storage"] = config ["edge1_storage"]
  vm_dep_config ["management_network"] = config ["edge1_mgmt_network"]
  vm_dep_config ["hostname"] = config ["edge1_fqdn"]
  vm_dep_config ["management_port_subnets"] = list()
  port_subnet = dict()
  port_subnet ["ip_addresses"] = list()
  port_subnet ["ip_addresses"].append (config ["edge1_mgmt_ip"])
  port_subnet ["prefix_length"] = int( config ["edge1_mgmt_netmask_prefix"])
  vm_dep_config ["management_port_subnets"].append (port_subnet)
  vm_dep_config ["default_gateway_addresses"] = list()
  vm_dep_config ["default_gateway_addresses"].append (config ["edge1_default_gateway"])
  vm_dep_config ["data_networks"] = list()
  vm_dep_config ["data_networks"].append (config ["edge2_data_network"])
  vm_dep_config ["enable_ssh"] = bool ("true")
  vm_dep_config ["allow_ssh_root_login"] = bool ("true")
  vm_dep_config ["placement_type"] = "VsphereDeploymentConfig"
  dep_config ["vm_deployment_config"] = vm_dep_config
  dep_config ["form_factor"] = defaults ['edge_form_factor']
  node_user_settings = dict()
  node_user_settings ["cli_username"] = "admin"
  node_user_settings ["cli_password"] = config ["edge1_system_password"]
  node_user_settings ["root_password"] = config ["edge1_system_password"]
  node_user_settings ["audit_username"] = "audit"
  node_user_settings ["audit_password"] = config ["edge1_system_password"]
  dep_config ["node_user_settings"] = node_user_settings
  node_dep_info ["deployment_config"] = dep_config
  node_settings = dict()
  node_settings ["hostname"] = config ["edge1_fqdn"]
  node_settings ["enable_ssh"] = bool ("true")
  node_settings ["allow_ssh_root_login"] = bool ("true")
  node_dep_info ["node_settings"] = node_settings
  node_dep_info ["resource_type"] = "EdgeNode"
  node_dep_info ["display_name"] = defaults ["edge1_display_name"]
  edge1 ["node_deployment_info" ] = node_dep_info
  edge1 ["display_name"] = defaults ["edge1_display_name"]
  edge1 ["resource_type"] = "TransportNode"
  edge_tnp.append(edge1)

  edge2 = dict()
  host_switch_spec = dict()
  host_switch_spec ["resource_type"] = "StandardHostSwitchSpec"
  host_switches = list()
  host_switch = dict()
  host_switch ["host_switch_name"] = defaults ["edge2_host_switch_name"]
  host_switch ["host_switch_type"] = "NVDS"
  host_switch ["host_switch_mode"] = "STANDARD"
  host_switch_profiles = list()
  host_switch_profile = dict()
  host_switch_profile ["name"] = config ["edge2_host_switch_profile_name"]
  host_switch_profile ["type"] = "UplinkHostSwitchProfile"
  host_switch ["host_switch_profiles"] = host_switch_profiles
  pnics = list()
  if (int (config ["edge2_number_of_uplinks"]) > 2):
    logging.error ("Max allowed Edge Uplinks: 2. Configured: %s" % config ["edge2_number_of_uplinks"])
    print ("ERROR: Max allowed Edge Uplinks: 2. Configured: %s" % config ["edge2_number_of_uplinks"])
    sys.exit (2)
  for i in range (int (config ["edge2_number_of_uplinks"]) - 1):
    pnic = dict()
    if (i == 0):
      pnic ["device_name"] = "fp-eth0"
      pnic ["uplink_name"] = "uplink-1"
    elif (i == 1):
      pnic ["device_name"] = "fp-eth1"
      pnic ["uplink_name"] = "uplink-2"
    pnics.append (pnic)
  host_switch ["pnics"] = pnics
  ip_assignment_spec = dict()
  ip_assignment_spec ["resource_type"] = "StaticIpPoolSpec"
  ip_assignment_spec ["ip_pool_name" ] = defaults ["ip_pool_1_name"]
  host_switch ["ip_assignment_spec"] = ip_assignment_spec
  transport_zone_endpoints = list()
  tz = dict()
  tz ["transport_zone_name"] = defaults ["overlay_tz_name"]
  transport_zone_endpoints.append (tz)
  host_switch ["transport_zone_endpoints"] = transport_zone_endpoints
  host_switch_profiles.append (host_switch_profile)
  host_switches.append (host_switch)
  host_switch_spec ["host_switches"] = host_switches
  edge2 ["host_switch_spec"] = host_switch_spec
  node_dep_info = dict()
  node_dep_info ["deployment_type"] = "VIRTUAL_MACHINE"
  dep_config = dict()
  vm_dep_config = dict()
  vm_dep_config ["vc_name"] = defaults ["nsx_vcenter"]
  vm_dep_config ["vc_username"] = config ["nsx_vcenter_username"]
  vm_dep_config ["vc_password"] = config ["nsx_vcenter_password"]
  vm_dep_config ["compute"] = config ["edge2_cluster"]
  vm_dep_config ["storage"] = config ["edge2_storage"]
  vm_dep_config ["management_network"] = config ["edge2_mgmt_network"]
  vm_dep_config ["hostname"] = config ["edge2_fqdn"]
  vm_dep_config ["management_port_subnets"] = list()
  port_subnet = dict()
  port_subnet ["ip_addresses"] = list()
  port_subnet ["ip_addresses"].append (config ["edge2_mgmt_ip"])
  port_subnet ["prefix_length"] = int (config ["edge2_mgmt_netmask_prefix"])
  vm_dep_config ["management_port_subnets"].append (port_subnet)
  vm_dep_config ["default_gateway_addresses"] = list()
  vm_dep_config ["default_gateway_addresses"].append (config ["edge2_default_gateway"])
  vm_dep_config ["data_networks"] = list()
  vm_dep_config ["data_networks"].append (config ["edge2_data_network"])
  vm_dep_config ["enable_ssh"] = bool ("true")
  vm_dep_config ["allow_ssh_root_login"] = bool ("true")
  vm_dep_config ["placement_type"] = "VsphereDeploymentConfig"
  dep_config ["vm_deployment_config"] = vm_dep_config
  dep_config ["form_factor"] =  defaults ['edge_form_factor']
  node_user_settings = dict()
  node_user_settings ["cli_username"] = "admin"
  node_user_settings ["cli_password"] = config ["edge2_system_password"]
  node_user_settings ["root_password"] = config ["edge2_system_password"]
  node_user_settings ["audit_username"] = "audit"
  node_user_settings ["audit_password"] = config ["edge2_system_password"]
  dep_config ["node_user_settings"] = node_user_settings
  node_dep_info ["deployment_config"] = dep_config
  node_settings = dict()
  node_settings ["hostname"] = config ["edge2_fqdn"]
  node_settings ["enable_ssh"] = bool ("true")
  node_settings ["allow_ssh_root_login"] = bool ("true")
  node_dep_info ["node_settings"] = node_settings
  node_dep_info ["resource_type"] = "EdgeNode"
  node_dep_info ["display_name"] = defaults ["edge2_display_name"]
  edge2 ["node_deployment_info" ] = node_dep_info
  edge2 ["display_name"] = defaults ["edge2_display_name"]
  edge2 ["resource_type"] = "TransportNode"
  edge_tnp.append(edge2)
  nsx_vars ["edge_transport_nodes"] = edge_tnp

  edge_clusters = list()
  edge_cluster = dict()
  edge_cluster ["display_name"] = defaults ["edge_cluster_display_name"]
  edge_cluster ["cluster_profile_bindings"] = list()
  profile = dict()
  profile ["profile_name"] = "nsx-default-edge-high-availability-profile"
  edge_cluster ["cluster_profile_bindings"].append (profile)
  edge_cluster ["members"] = list()
  tn1 = dict()
  tn1 ["transport_node_name"] = defaults ["edge1_display_name"]
  edge_cluster ["members"].append (tn1)
  tn2 = dict()
  tn2 ["transport_node_name"] = defaults ["edge2_display_name"]
  edge_cluster ["members"].append (tn2)
  edge_clusters.append (edge_cluster)
  nsx_vars ["edge_clusters"] = edge_clusters

  tier0s = list()
  tier0 = dict()
  tier0 ["display_name"] = defaults ["tier0_display_name"]
  tier0 ["ha_mode"] = "ACTIVE_STANDBY"
  locale_service = list()
  service = dict()
  service ["state"] = "present"
  service ["id"] = defaults ["tier0_display_name"] + "_service"
  service ["route_redistribution_types"] = list()
  service ["route_redistribution_types"].append ("TIER0_STATIC")
  service ["route_redistribution_types"].append ("TIER0_NAT")
  service ["edge_cluster_info"] = dict()
  service ["edge_cluster_info"]["edge_cluster_display_name"] = defaults ["edge_cluster_display_name"]
  service ["BGP"] = dict()
  service ["BGP"]["state"] = "present"
  service ["BGP"]["local_as_num"] = "1121"
  locale_service.append (service)
  tier0 ["locale_services"] = locale_service
  tier0s.append (tier0)
  nsx_vars ["tier0_gateways"] = tier0s

  hostsps = list()
  hostsp = dict()
  hostsp ["display_name"] = defaults ["host_switch_profile_name"]
  hostsp ["resource_type"] = "UplinkHostSwitchProfile"
  hostsp ["mtu"] = config ["host_switch_mtu"]
  teaming = dict()
  teaming ["standby_list"] = list()
  teaming ["active_list"] = list()
  al1 = dict()
  al1 ["uplink_name"] = defaults ["host_switch_uplink1_name"]
  al1 ["uplink_type"] = "PNIC"
  teaming ["active_list"].append (al1)
  al2 = dict()
  al2 ["uplink_name"] = defaults ["host_switch_uplink2_name"]
  al2 ["uplink_type"] = "PNIC"
  teaming ["active_list"].append (al2)
  teaming ["policy"] = defaults ["host_switch_teaming_policy"]
  hostsp ["teaming"] = teaming
  hostsp ["transport_vlan"] = config ["transport_vlan"]
  hostsps.append (hostsp)
  nsx_vars ["host_switch_profiles"] = hostsps

  host_tnps = list()
  tnp = dict()
  tnp ["resource_type"] = "TransportNodeProfile"
  tnp ["display_name"] = defaults ["host_tnp_display_name"]
  host_switch_spec = dict()
  host_switches = list()
  host_switch = dict()
  host_switch ["host_switch_id"] = get_vds_uuid (config ["host_vds_name"], config ["vcenter_fqdn"], config ["vcenter_username"], config ["vcenter_password"])
  host_switch ["host_switch_type"] = "VDS"
  host_switch ["host_switch_mode"] = "STANDARD"
  host_switch ["host_switch_profiles"] = list()
  host_switch_profile = dict()
  host_switch_profile ["type"] = "UplinkHostSwitchProfile"
  host_switch_profile ["name"] = defaults ["host_default_host_switch_profile"]
  host_switch ["host_switch_profiles"].append (host_switch_profile)
  host_switches.append (host_switch)
  host_switch ["pnics"] = list()
  uplinks = list()
  if (int (config ["host_number_of_uplinks"]) > 2):
    logging.error ("Max allowed Host Uplinks: 2. Configured: %s" % config ["host_number_of_uplinks"])
    print ("ERROR: Max allowed Host Uplinks: 2. Configured: %s" % config ["host_number_of_uplinks"])
    sys.exit (2)
  for i in range (int (config ["host_number_of_uplinks"])):
    uplink = dict()
    if (i == 0):
      uplink ["vds_uplink_name"] = "Uplink 1"
      uplink ["uplink_name"] = "uplink-1"
    else:
      uplink ["vds_uplink_name"] = "Uplink 2"
      uplink ["uplink_name"] = "uplink-2"
    uplinks.append (uplink)
  host_switch ["uplinks"] = uplinks
  ip_assignment_spec = dict()
  ip_assignment_spec ["resource_type"] = "StaticIpPoolSpec"
  ip_assignment_spec ["ip_pool_name" ] = defaults ["ip_pool_2_name"]
  host_switch ["ip_assignment_spec"] = ip_assignment_spec
  transport_zone_endpoints = list()
  tz = dict()
  tz ["transport_zone_name"] = defaults ["overlay_tz_name"]
  transport_zone_endpoints.append (tz)
  host_switch ["transport_zone_endpoints"] = transport_zone_endpoints
  host_switch_spec ["host_switches"] = host_switches
  host_switch_spec ["resource_type"] = "StandardHostSwitchSpec"
  tnp ["host_switch_spec"] = host_switch_spec
  host_tnps.append (tnp)
  tnp ["description"] = defaults ["host_tnp_display_name"]
  nsx_vars ["transport_node_profiles"] = host_tnps

  tn_collections = list()
  for cluster in config ["compute_clusters_for_prep"].split(','):
    cluster = cluster.strip()
    tn_collection = dict()
    tn_collection ["state"] = "present"
    tn_collection ["display_name"] = "TNP" + "_" + cluster
    tn_collection ["description"] = "TNP" + "_" + cluster
    tn_collection ["resource_type"] = "TransportNodeCollection"
    tn_collection ["compute_manager_name"] = defaults ["compute_manager_name"]
    tn_collection ["cluster_name"] = cluster
    tn_collection ["transport_node_profile_name"] = defaults ["host_tnp_display_name"]
    tn_collections.append (tn_collection)
  nsx_vars ["transport_node_collections"] = tn_collections

  with open(g_nsx_install_vars, 'w') as json_file:
    json.dump(nsx_vars, json_file, indent=2)


def call_ansible_to_install():
  print ("Deploying NSX Manager Cluster")
  logging.debug ("Deploying First NSX node")
  run_playbook ("01_deploy_first_node.yml", wait=300)

  logging.debug ("Accepting EULA and adding NSX License")
  run_playbook ("02_add_nsx_license_accept_eula.yml")

  logging.debug ("Configuring Compute Manager")
  run_playbook ("03_configure_compute_manager.yml")

  config = dict()
  config = txt_to_json(g_config)

  if (config ['nsx_manager_cluster'].lower() == "yes" or
      config ['nsx_manager_cluster'].lower() == "y"):
    logging.debug ("Deploying second and third NSX node")
    run_playbook ("04_deploy_second_third_node.yml", wait=300)
  else:
    print ("Skipping NSX Manager cluster deployment. Single node deployed")
    logging.debug ("Skipping cluster deplyment")

  logging.debug ("Deploying Transport Zones")
  run_playbook ("05_setup_transport_zones.yml")

  print ("Deploying Edge Cluster")
  logging.debug ("Deploying Tunnel IPs")
  run_playbook ("06_create_tunnel_ip_pools.yml")

  logging.debug ("Creating Edge Transport nodes")
  run_playbook ("07_create_edge_transport_nodes.yml", wait=300)

  logging.debug ("Creating Edge Cluster")
  run_playbook ("08_setup_edge_cluster.yml")

  print ("Creating a Tier0 Gateway")
  logging.debug ("Configure T0 Gateway")
  run_playbook ("09_configure_t0_gateway.yml")

  print ("Creating Uplink Host Switch Profile")
  logging.debug ("Creating Uplink Host Switch Profile")
  run_playbook ("10_create_host_switch_profile.yml")

  print ("Prepping Hosts for NSX")
  logging.debug ("Creating TNP")
  run_playbook("11_create_transport_node_profiles.yml")

  logging.debug ("Prepping hosts")
  run_playbook("12_configure_nsx_on_cluster.yml")

  logging.debug ("install_nsx: Done")
  print ("All deployments done!")


#
# Installs NSX
#   - Combine the defaults and the config file and generate the JSON required
#     by Ansible
#   - Run Ansible playbooks
#
def install_nsx():
  logging.debug ("install_nsx: Started")

  generate_vars_file()

  logging.debug("install_nsx: Done. Variables file generated.")

  print ("Variables file generated, Starting install")
  call_ansible_to_install()




#
# Main
#

parser = argparse.ArgumentParser(description='Install NSX')
#parser.add_argument('--view-defaults', dest='view_defaults',
#                    action='store_true',
#                    help='View the current Defaults')
#parser.add_argument('--view-config', dest='view_config',
#                    action='store_true',
#                    help='View existing Configs')
parser.add_argument('--start', dest='start_install',
                    action='store_true',
                    help='Start the installation')
parser.add_argument('--reset-defaults', dest='reset_defaults',
                    action='store_true',
                    help='Reset defaults to factory setting')
parser.add_argument('--reset-config', dest='reset_config',
                    action='store_true',
                    help='Reset the config file')
parser.add_argument('--manual', dest='manual',
                    help='Manual install. Only generate the variables file',
                    action='store_true')
args = parser.parse_args()

# Change the logfile if the default log file needs to be something different
logging.basicConfig(format='%(asctime)s: %(levelname)s: %(message)s',
                    filename=g_logfile, level=logging.DEBUG)

if (args.start_install):
  install_nsx()
elif (args.reset_defaults):
  reset_defaults()
elif (args.reset_config):
  reset_config()
elif (args.manual):
  generate_vars_file()
