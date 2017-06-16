# Deploying cephmetrics with ansible

This set of ansible roles, in combination with `playbook.yml`, provide a way to deploy cephmetrics to monitor a Ceph cluster.

## Prerequisites
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
- [ceph-grafana](./roles/ceph-grafana/): Used for the dashboard host

## Variables
TODO

## Current Limitations

- Only RHEL 7 hosts are supported
- Currently, metrics are only *displayed* for `osd` and `rgw` hosts.
- The `collectd` and `graphite-web` packages are sourced from [EPEL](https://fedoraproject.org/wiki/EPEL) and the `grafana` package is sourced from [grafana.com](https://grafana.com/)
- Authentication for grafana and graphite is fixed and creates a user `admin` with password `admin`.
- Services are deployed on the dashboard host directly; there is not yet support for a containerized deployment.

## Usage

    ansible-playbook -v -i ./inventory
