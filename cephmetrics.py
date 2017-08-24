#!/usr/bin/env python

import os
import logging
import collectd

from collectors.mon import Mon
from collectors.rgw import RGW
from collectors.osd import OSDs
from collectors.iscsi import ISCSIGateway
from collectors.common import flatten_dict, get_hostname


PLUGIN_NAME = 'cephmetrics'


class Ceph(object):

    roles = {
        "mon": "Mon",
        "rgw": "RGW",
        "osd": "OSDs",
        "iscsi": "ISCSIGateway"
    }

    def __init__(self):
        self.cluster_name = None
        self.event_url = None
        self.host_name = get_hostname()

        self.mon = None
        self.rgw = None
        self.osd = None
        self.iscsi = None

    def probe(self):
        """
        set up which collector(s) to use
        """

        if Mon.probe():
            self.mon = Mon(self, self.cluster_name)

        if RGW.probe():
            self.rgw = RGW(self, self.cluster_name)

        if OSDs.probe():
            self.osd = OSDs(self, self.cluster_name)

        if ISCSIGateway.probe():
            self.iscsi = ISCSIGateway(self, self.cluster_name)

    def get_stats(self):

        stats = {}

        if self.mon:
            stats['mon'] = self.mon.get_stats()

        if self.rgw:
            stats['rgw'] = self.rgw.get_stats()

        if self.osd:
            stats['osd'] = self.osd.get_stats()

        if self.iscsi:
            stats['iscsi'] = self.iscsi.get_stats()

        return stats


def write_stats(role_metrics, stats):

    flat_stats = flatten_dict(stats, '.')
    
    for key_name in flat_stats:
        attr_name = key_name.split('.')[-1]

        # TODO: this needs some more think time, since the key from the name
        # is not the key of the all_metrics dict
        if attr_name in role_metrics:
            attr_type = role_metrics[attr_name][1]     # gauge / derive etc
        else:
            # assign a default
            attr_type = 'gauge'

        attr_value = flat_stats[key_name]

        val = collectd.Values(plugin=PLUGIN_NAME, type=attr_type)
        instance_name = "{}.{}".format(CEPH.cluster_name,
                                       key_name)
        val.type_instance = instance_name
        val.values = [attr_value]
        val.dispatch()


def configure_callback(conf):

    valid_log_levels = ['debug', 'info']

    global CEPH
    module_parms = {node.key: node.values[0] for node in conf.children}

    log_level = module_parms.get('LogLevel', 'debug')
    if log_level not in valid_log_levels:
        collectd.error("cephmetrics: LogLevel specified is invalid - must"
                       " be :{}".format(' or '.join(valid_log_levels)))

    if 'EventURL' in module_parms:
        CEPH.event_url = module_parms['EventURL']
        collectd.info("cephmetrics: Event messages enabled for target "
                      "{}".format(CEPH.event_url))
    else:
        collectd.warning("cephmetrics: EventURL missing - health events "
                         "will not be reported")

    if 'ClusterName' in module_parms:
        cluster_name = module_parms['ClusterName']
        # cluster name is all we need to get started
        if not os.path.exists('/etc/ceph/{}.conf'.format(cluster_name)):
            collectd.error("Clustername given ('{}') not found in "
                           "/etc/ceph".format(module_parms['ClusterName']))

        # let's assume the conf file is OK to use
        CEPH.cluster_name = cluster_name

        setup_module_logging(log_level)

        CEPH.probe()

        collectd.info("{}: Roles detected - "
                      "mon:{} osd:{} rgw:{} "
                      "iscsi:{}".format(__name__,
                                        isinstance(CEPH.mon, Mon),
                                        isinstance(CEPH.osd, OSDs),
                                        isinstance(CEPH.rgw, RGW),
                                        isinstance(CEPH.iscsi, ISCSIGateway)))
    else:
        collectd.error("cephmetrics: ClusterName is required")


def setup_module_logging(log_level):

    level = {"debug": logging.DEBUG,
             "info": logging.INFO}

    logging.getLogger('cephmetrics')
    logging.basicConfig(filename='/var/log/collectd-cephmetrics.log',
                        format='%(asctime)s - %(levelname)-7s - '
                               '[%(filename)s:%(lineno)s:%(funcName)s() - '
                               '%(message)s',
                        filemode='w',
                        level=level.get(log_level))


def read_callback():

    stats = CEPH.get_stats()

    for role in Ceph.roles:
        if role in stats:
            collector = getattr(CEPH, role)

            write_stats(collector.all_metrics, stats[role])

            error_handler(collector)


def error_handler(collector):
    if not collector.error:
        return

    # detected an error, let's flag it to the collectd log
    msg_text = ",".join(collector.error_msgs)

    collectd.error("cephmetrics error: {} - {}".format(collector._name,
                                                       msg_text))

    # reset the collector instance's error tracking
    collector.error = False
    del collector.error_msgs[:]


if __name__ == '__main__':

    # run interactively or maybe test the code

    pass

else:

    CEPH = Ceph()

    collectd.register_config(configure_callback)
    collectd.register_read(read_callback)
