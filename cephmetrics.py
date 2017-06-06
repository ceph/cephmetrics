#!/usr/bin/env python
import os
import glob
import collectd

from collectors.mon import Mon
from collectors.rgw import RGW
from collectors.osd import OSDs
from collectors.common import flatten_dict, get_hostname

__author__ = 'Paul Cuzner'

PLUGIN_NAME = 'cephmetrics'


class Ceph(object):
    def __init__(self):
        self.cluster_name = None
        self.host_name = get_hostname()

        self.mon_socket = None
        self.rgw_socket = None

        self.mon = None
        self.rgw = None
        self.osd = None

    def probe(self):
        """
        set up which collector(s) to use, based on what types of sockets we
        find in /var/run/ceph
        """

        mon_socket = '/var/run/ceph/{}-mon.{}.asok'.format(self.cluster_name,
                                                           self.host_name)
        if os.path.exists(mon_socket):
            self.mon_socket = mon_socket
            self.mon = Mon(self.cluster_name,
                           admin_socket=mon_socket)

        rgw_socket_list = glob.glob('/var/run/ceph/{}-client.rgw.{}.'
                                    '*.asok'.format(self.cluster_name,
                                                    self.host_name))
        if rgw_socket_list:
            rgw_socket = rgw_socket_list[0]
            self.rgw = RGW(self.cluster_name,
                           admin_socket=rgw_socket)


        osd_socket_list = glob.glob('/var/run/ceph/{}-osd.*'
                                    '.asok'.format(self.cluster_name))
        if osd_socket_list:
            self.osd = OSDs(self.cluster_name)


def write_stats(role_metrics, stats):

    flat_stats = flatten_dict(stats, '.')
    
    for key_name in flat_stats:
        attr_name = key_name.split('.')[-1]

        # TODO: this needs some more think time, since the key from the name
        # is not the key of the all_metrics dict
        attr_type = role_metrics[attr_name][1]     # gauge / derive etc
        attr_value = flat_stats[key_name]

        val = collectd.Values(plugin=PLUGIN_NAME, type=attr_type)
        instance_name = "{}.{}".format(CEPH.cluster_name,
                                       key_name)
        val.type_instance = instance_name
        val.values = [attr_value]
        val.dispatch()


def configure_callback(conf):

    global CEPH
    module_parms = {node.key: node.values[0] for node in conf.children}

    if 'ClusterName' in module_parms:
        cluster_name = module_parms['ClusterName']
        # cluster name is all we need to get started
        if not os.path.exists('/etc/ceph/{}.conf'.format(cluster_name)):
            collectd.error("Clustername given ('{}') not found in "
                           "/etc/ceph".format(module_parms['ClusterName']))

        # let's assume the conf file is OK to use
        CEPH.cluster_name = cluster_name

        CEPH.probe()

    else:
        collectd.error("ClusterName is required")


def read_callback():

    if CEPH.mon:
        mon_stats = CEPH.mon.get_stats()
        write_stats(Mon.all_metrics, mon_stats)

    if CEPH.rgw:
        rgw_stats = CEPH.rgw.get_stats()
        write_stats(RGW.all_metrics, rgw_stats)

    if CEPH.osd:
        osd_node_stats = CEPH.osd.get_stats()
        write_stats(OSDs.all_metrics, osd_node_stats)


if __name__ == '__main__':
    # run interactively or maybe test the code
    collectd.info("In main for some reason !")
    pass

else:

    CEPH = Ceph()

    collectd.register_config(configure_callback)
    collectd.register_read(read_callback)
