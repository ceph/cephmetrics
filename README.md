# cephmetrics

Cephmetrics is a tool that allows a user to visually monitor various metrics in a running Ceph cluster.

## Prerequisites
- RHEL 7 should be running on all hosts
- A functional ceph cluster running version ceph-osd-10.2.7-27.el7cp.x86_64 or later is already up and running.
- Another host machine independent of the ceph machines must be available.  This host will be used to receive data pushed by the hosts in the Ceph cluster, and will run the dashboard to display that data.
- A host machine on which to execute `ansible-playbook` to orchestrate the deployment must be available.
- Passwordless SSH access from the deploy host to the ceph hosts.  The username should be the same for all hosts.
- Passwordless sudo access on the ceph and dashboard hosts
- All hosts must share the same DNS domain

## Resulting configuration

After running this procedure, you will have the following configuration.
- The ceph nodes will have `collectd` installed, along with collector plugins from `cephmetrics-collectd`
- The dashboard host will have `grafana` installed and configured to display various dashboards by querying data received from Ceph nodes via a `graphite-web`, `python-carbon`, and `python-whisper` stack.

## Installation

### Install cephmetrics-ansible

First, decide which machine you want to use to run `ansible-playbook`.  If you used [`ceph-ansible`](https://github.com/ceph/ceph-ansible) to set up your cluster, you may want to reuse that same host to take advantage of the inventory file that was created as part of that process.

Once the host is selected, perform the following steps there.  This will install a repo which includes the cephmetrics installation code and ansible (version 2.2.3 or later):
```
sudo su -
mkdir ~/cephmetrics
subscription-manager repos --enable rhel-7-server-optional-rpms --enable rhel-7-server-rhscon-2-installer-rpms
curl -L -o /etc/yum.repos.d/cephmetrics.repo http://download.ceph.com/cephmetrics/rpm-master/el7/cephmetrics.repo
yum install cephmetrics-ansible
```

### Create or edit the inventory file

Next, we need an inventory file.  If you are running `ansible-playbook` on a host that previously ran `ceph-ansible`, you may simply modify `/etc/ansible/hosts`; otherwise you may copy `/usr/share/cephmetrics-ansible/inventory.sample` and modify it if you wish.

The inventory file format looks like:

    [ceph-grafana]
    grafana_host.example.com

    [osds]
    osd0.example.com
    osd1.example.com
    osd2.example.com

    [mons]
    mon0.example.com
    mon1.example.com
    mon2.example.com

    [mdss]
    mds0.example.com

    [rgws]
    rgw0.example.com

If you are running `ansible-playbook` on a host mentioned in the inventory file, you will need to append `ansible_connection=local` to each line in the inventory file that mentions that host.  An example:
    ```
    my_host.example.com ansible_connection=local
    ```
Omit the mdss section if no ceph mds nodes are installed.  Omit the rgws section if no rgw nodes are installed.

Ansible variables can be set in a `vars.yml` file if necessary.  If it is required, make sure to add `-e '@/path/to/vars.yml` to your `ansible-playbook` invocation below.  [Click here](./ansible/README.md) for more information.

## Deploy via ansible-playbook

If you are using a `ceph-ansible` host, run these commands:
```
cd /usr/share/cephmetrics-ansible
ansible-playbook -v playbook.yml
```

Otherwise, run these commands:
```
cd /usr/share/cephmetrics-ansible
ansible-playbook -v -i /path/to/inventory playbook.yml
```

Note: The reason it is necessary to change directories is so that `ansible-playbook` will use the bundled `ansible.cfg`; there is currently no command-line argument allowing the specification of an arbitrary `.cfg` file.
