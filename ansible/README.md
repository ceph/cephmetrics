# Deploying cephmetrics with ansible

This set of ansible roles, in combination with `playbook.yml`, provide a way to deploy cephmetrics to monitor a Ceph cluster.

## Prerequisites
- RHEL 7 is supported with `devel_mode` set to `True` or `False`. Ubuntu 16.04 and CentOS 7 are supported only when `devel_mode` is `True` at this point.
- Currently only RHEL 7 is supported for all hosts
- A functional [ceph](https://ceph.com/) cluster. [collectd](https://collectd.org/) will be used to collect metrics
- A separate host to receive data pushed by hosts in the Ceph cluster, and run the dashboard to display that data.
- An inventory file describing your cluster.
- A host on which to execute `ansible-playbook` to orchestrate the deployment. This can be the same as the dashboard host.
- Passwordless SSH access from the deploy host to the ceph hosts. The username should be the same for all hosts.
- Passwordless sudo access on the ceph and dashboard hosts
- All hosts must share the same DNS domain

## Example inventory file

    [ceph-grafana]
    cephmetrics.example.com

    [osds]
    osd0.example.com
    osd1.example.com
    osd3.example.com

    [mons]
    mon0.example.com
    mon1.example.com
    mon2.example.com

    [mdss]
    mds0.example.com

    [rgws]
    rgw0.example.com

Notes:
- Omit any sections from the inventory file for which your cluster has no hosts.
- If you are running `ansible-playbook` directly on the dashboard (`ceph-grafana`) host, its inventory entry should look like: 
    ```
    [ceph-grafana]
    cephmetrics.example.com ansible_connection=local
    ```

## Roles
- [ceph-collectd](./roles/ceph-collectd/): Used for ceph cluster hosts
- [ceph-graphite](./roles/ceph-graphite/): Used for the dashboard host
- [ceph-grafana](./roles/ceph-grafana/): Used for the dashboard host

## Variables
You may override certain variables by creating a `vars.yml` file:
- `ansible_ssh_user`: The user account use for SSH connections. This may also be set on a per-host basis in the inventory file.
- `cluster`: The name of the Ceph cluster. Default: ceph
- `firewalld_zone`: The `firewalld` zone to use when opening ports for Grafana and Carbon. Default: public
- `devel_mode`: Whether to perform a development-mode deployment vs. a production deployment. Default: true
- `whisper`: May be used to configure [whisper retention](http://graphite.readthedocs.io/en/latest/config-carbon.html#storage-schemas-conf) settings. Default:
    ```
    whisper:
      retention:
        - ['10s', '7d']
        - ['1m', '30d']
        - ['15m', '5y']
    ```
- `update_alerts`: Whether to update the alerts dashboard along with the rest. Removes any user-defined alerts. Default: false
- `custom_repos`: A list of custom package repositories to enable. Currently supports yum systems only. Format:
    ```
    custom_repos:
      yum:
      - name: my_repo
        baseurl: http://example.com/my/repo
    ```

## Current Limitations

- Currently, metrics are only *displayed* for `osd` and `rgw` hosts.
- Services are deployed on the dashboard host directly; there is not yet support for a containerized deployment.

## Usage
If you are not overriding any variables:
```
    ansible-playbook -v -i ./inventory
```
Or, if you are:
```
    ansible-playbook -v -i ./inventory -e '@vars.yml'
```
