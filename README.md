# NSX Install for Project Pacific

# Overview
This repository contains code that simplifies NSX Install. The information needed to install NSX is read from 2 files.

* Defaults: This contains certain display names. Users can change this but is not required to.

* Uer Config: This contains all the information that is needed from the user (like network details, passwords etc)

The provided nsx-install.py script merges these files to generate a JSON file which is used by the Ansible modules to install NSX.

# Dependencies
There are dependency on the following tools:
* Python > 3.6.x
* Ansible > 2.9.x
* PyVmomi

## Version Check
An easy way to verify if Python and Ansible are in the right versions:
```
$> ansible-playbook --version
ansible-playbook 2.9.6
  config file = /etc/ansible/ansible.cfg
  configured module search path = ['/home/vmware/.ansible/plugins/modules', '/usr/share/ansible/plugins/modules']
  ansible python module location = /usr/local/lib/python3.6/dist-packages/ansible
  executable location = /usr/local/bin/ansible-playbook
  python version = 3.6.9 (default, Nov  7 2019, 10:44:02) [GCC 8.3.0]
```

# Getting Started
* Clone this repo to a linux based system (Ubuntu/CentOS)
* Make sure the dependencies are met (Install Python/Ansible/PyVmomi)
* Download the NSX unified appliance installer OVA on the local file system
* Edit nsx-config.txt file and update ALL the fields. Make sure you also have a NSX License!
* Run python nsx-install.py --start

# Optional (Advanced) functionality
* Run python nsx-install.py --reset-defaults
  This creates the nsx-defaults.txt file. Edit the file if needed. Editing it is purely optional
  Note: Running python nsx-install.py --reset-defaults will overwrite the existing file
* Run python nsx-install.py --reset-config
  This creates the nsx-config.txt file. Edit the file and provide all the information
  Save the nsx-config.txt in case you want to refer to it later
  Note: Running python nsx-install.py --reset-config will overwrite the existing file

# Logging
All logs are generated in nsx-install.log


# Resources
For general information about Ansible, visit the [GitHub project page][an-github].

[an-github]: https://github.com/ansible/ansible

Documentation on the NSX platform can be found at the [NSX-T Documentation page](https://docs.vmware.com/en/VMware-NSX-T/index.html)

