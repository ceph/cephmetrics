#!/usr/bin/env python
import glob
import os
import sys

# Remove collectd's plugin dir from sys.path to avoid namespace collisions with
# .so files that are not actually Python modules
sys.path = [item for item in sys.path if not item.endswith('/collectd')]

from . import (common, iscsi, mon, osd, rgw)


class Ceph(object):
    def __init__(self):
        self.cluster_name = None
        self.host_name = common.get_hostname()

        self.mon_socket = None
        self.rgw_socket = None

        self.mon = None
        self.rgw = None
        self.osd = None
        self.iscsi = None

    def probe(self):
        """
        set up which collector(s) to use, based on what types of sockets we
        find in /var/run/ceph
        """

        mon_socket = '/var/run/ceph/{}-mon.{}.asok'.format(self.cluster_name,
                                                           self.host_name)
        if os.path.exists(mon_socket):
            self.mon_socket = mon_socket
            self.mon = mon.Mon(self.cluster_name, admin_socket=mon_socket)

        rgw_socket_list = glob.glob('/var/run/ceph/{}-client.rgw.*.'
                                    'asok'.format(self.cluster_name))

        if rgw_socket_list:
            rgw_socket = rgw_socket_list[0]
            self.rgw = rgw.RGW(self.cluster_name, admin_socket=rgw_socket)

        osd_socket_list = glob.glob('/var/run/ceph/{}-osd.*'
                                    '.asok'.format(self.cluster_name))
        mounted = common.freadlines('/proc/mounts')
        osds_mounted = [mnt for mnt in mounted
                        if mnt.split()[1].startswith('/var/lib/ceph')]
        if osd_socket_list or osds_mounted:
            self.osd = osd.OSDs(self.cluster_name)

        if os.path.exists('/sys/kernel/config/target/iscsi'):
            self.iscsi = iscsi.ISCSIGateway(self.cluster_name)
