#!/usr/bin/env python2

# requires python-rtslib_fb for LIO interaction
#
# NB. the rtslib_fb module is dynamically loaded by the ISCSIGateway
# class instantiation. This prevents import errors within the generic parent
# module cephmetrics
#
import os
import sys
import time

from collectors.base import BaseCollector
from collectors.common import fread


class Client(object):

    def __init__(self, iqn):
        self.iqn = iqn
        self.name = iqn.replace('.', '-')
        self.luns = {}
        self.lun_count = 0
        self._cycle = 0

    def dump(self):
        client_dump = {}
        lun_info = {}
        client_dump[self.name] = {"luns": {},
                                  "lun_count": self.lun_count}
        for lun_name in self.luns:
            lun = self.luns[lun_name]
            lun_info.update(lun.dump())

        return {self.name: {"luns": lun_info,
                            "lun_count": len(lun_info)}
                }


class LUN(object):

    def __init__(self, client, tpg_lun):
        self._path = tpg_lun.storage_object.path
        self._tpg_lun = tpg_lun
        self._name = tpg_lun.storage_object.name
        self._display_name = tpg_lun.storage_object.name.replace('.', "-")
        self._so = tpg_lun.storage_object
        self._client = client
        self._cycle = 0
        self.size = 0
        self.iops = 0
        self.read_bytes_per_sec = 0
        self.write_bytes_per_sec = 0
        self.total_bytes_per_sec = 0
        self.active_path = 0

    def refresh(self, cycle_id):
        self._cycle = cycle_id
        self.size = self._so.size
        stats_path = os.path.join(self._path, 'statistics/scsi_lu')
        self.iops = int(fread(os.path.join(stats_path, "num_cmds")))
        read_mb = float(fread(os.path.join(stats_path, "read_mbytes")))
        write_mb = float(fread(os.path.join(stats_path, "write_mbytes")))
        self.read_bytes_per_sec = int(read_mb * 1024 ** 2)
        self.write_bytes_per_sec = int(write_mb * 1024 ** 2)
        self.total_bytes_per_sec = self.read_bytes_per_sec + \
                                   self.write_bytes_per_sec

        if self._tpg_lun.alua_tg_pt_gp_name == 'ao':
            self.active_path = 1
        else:
            self.active_path = 0

    def dump(self):
        return {self._display_name: {k: getattr(self, k) for k in self.__dict__
                                     if not k.startswith("_")}}


class ISCSIGateway(BaseCollector):
    """
    created on a host that has a /sys/kernel/config/target/iscsi dir
    i.e. there is an iscsi gateway here!
    """

    all_metrics = {
        "lun_count": ("lun_count", "gauge"),
        "client_count": ("client_count", "gauge"),
        "tpg_count": ("tpg_count", "gauge"),
        "sessions": ("sessions", "gauge"),
        "capacity": ("capacity", "gauge"),
        "iops": ("iops", "derive"),
        "read_bytes_per_sec": ("read_bytes_per_sec", "derive"),
        "write_bytes_per_sec": ("write_bytes_per_sec", "derive"),
        "total_bytes_per_sec": ("total_bytes_per_sec", "derive")
    }

    def __init__(self, *args, **kwargs):
        BaseCollector.__init__(self, *args, **kwargs)

        # Since the module can be imported by a parent class but not
        # instantiated, the rtslib import is deferred until the first instance
        # of the the class is created. This keeps the parent module simple
        # and more importantly generic
        if 'rtslib_fb.root' not in sys.modules.keys():

            try:
                from rtslib_fb.root import RTSRoot
            except ImportError:
                raise

        self._root = RTSRoot()

        self.clients = {}
        self.cycle = 0

        self.iops = 0
        self.read_bytes_per_sec = 0
        self.write_bytes_per_sec = 0
        self.total_bytes_per_sec = 0

    def refresh(self):
        """
        populate the instance by exploring rtslib
        """

        self.iops = 0
        self.read_bytes_per_sec = 0
        self.write_bytes_per_sec = 0
        self.total_bytes_per_sec = 0

        if self.cycle == 10:
            self.cycle = 0
        else:
            self.cycle += 1

        for node_acl in self._root.node_acls:

            client_name = node_acl.node_wwn

            if client_name not in self.clients:
                new_client = Client(client_name)
                self.clients[client_name] = new_client

            client = self.clients[client_name]
            client.lun_count = 0
            client._cycle = self.cycle

            for lun in node_acl.mapped_luns:
                client.lun_count += 1
                tpg_lun = lun.tpg_lun
                lun_name = tpg_lun.storage_object.name
                if lun_name not in client.luns:
                    lun = LUN(client, tpg_lun)
                    client.luns[lun._name] = lun
                else:
                    lun = client.luns[lun_name]

                lun.refresh(self.cycle)

                self.iops += lun.iops
                self.read_bytes_per_sec += lun.read_bytes_per_sec
                self.write_bytes_per_sec += lun.write_bytes_per_sec
                self.total_bytes_per_sec = self.read_bytes_per_sec + \
                                           self.write_bytes_per_sec

    def prune(self):
        """
        drop child objects held by the instance, that are no longer in the
        iSCSI config i.e. don't report on old information
        """

        for client_name in self.clients:
            client = self.clients[client_name]

            for lun_name in client.luns:
                lun = client.luns[lun_name]
                if lun._cycle != self.cycle:
                    # drop the lun entry
                    self.logger.debug("pruning LUN '{}'".format(lun_name))

                    del client.luns[lun_name]

            if client._cycle != self.cycle:
                # drop the client entry
                self.logger.debug("pruning client '{}'".format(client_name))
                del self.clients[client_name]

    def dump(self):

        gw_stats = {}
        client_stats = {}

        for metric in ISCSIGateway.all_metrics:
            gw_stats[metric] = getattr(self, metric)

        for client_name in self.clients:
            client = self.clients[client_name]
            client_stats.update(client.dump())

        return {"iscsi": {
                           "ceph_version": self.version,
                           "gw_name": {self.gateway_name: 0},
                           "gw_stats": gw_stats,
                           "gw_clients": client_stats
                         }
               }

    def _get_so(self):
        return [so for so in self._root.storage_objects]

    def _get_node_acls(self):
        return [node for node in self._root.node_acls]

    @property
    def tpg_count(self):
        return len([tpg for tpg in self._root.tpgs])

    @property
    def lun_count(self):
        return len(self._get_so())

    @property
    def sessions(self):
        return len([session for session in self._root.sessions])

    @property
    def gateway_name(self):
        # Only the 1st gateway is considered/supported
        gw_iqn = [gw.wwn for gw in self._root.targets][0]
        return gw_iqn.replace('.', '-')

    @property
    def client_count(self):
        return len(self._get_node_acls())

    @property
    def capacity(self):
        return sum([so.size for so in self._get_so()])

    def get_stats(self):

        start = time.time()

        # populate gateway instance with the latest configuration from rtslib
        stats = {}
        if os.path.exists('/sys/kernel/config/target/iscsi'):
            self.refresh()

            # Overtime they'll be churn in client and disks so we need to drop
            # any entries from prior runs that are no longer seen in the iscsi
            # configuration with the prune method
            self.prune()
            stats = self.dump()
        else:
            msg = "iSCSI Gateway is not active on this host"
            self.logger.warning(msg)
            self.error = True
            self.error_msgs = [msg]
            stats = {"iscsi": {
                               "ceph_version": self.version
                              }
                     }

        end = time.time()

        self.logger.info("LIO stats took {}s".format(end - start))

        return stats

