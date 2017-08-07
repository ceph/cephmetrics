#!/usr/bin/env python2

# requires python-rtslib_fb for LIO interaction

import os
import time
from collectors.base import BaseCollector
from rtslib_fb import RTSRoot
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

    metrics = {
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
        :return:
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
        iSCSI config i.e. don't report on old tut!
        :return:
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

        for metric in ISCSIGateway.metrics:
            gw_stats[metric] = getattr(self, metric)

        for client_name in self.clients:
            client = self.clients[client_name]
            client_stats.update(client.dump())

        return {"iscsi": {
                           "gw_name": {self.gateway_name: 0},
                           "gw_stats": gw_stats,
                           "gw_clients": client_stats
                         }
               }


    def _get_so(self):
        return [so for so in self._root.storage_objects]

    def _get_node_acls(self):
        return [node for node in self._root.node_acls]

    def _get_tpg_count(self):
        return len([tpg for tpg in self._root.tpgs])

    def _get_lun_count(self):
        return len(self._get_so())

    def _get_session_count(self):
        return len([session for session in self._root.sessions])

    def _get_gateway_name(self):
        # Only the 1st gateway is considered/supported
        gw_iqn = [gw.wwn for gw in self._root.targets][0]
        return gw_iqn.replace('.', '-')

    def _get_client_count(self):
        return len(self._get_node_acls())

    def _get_capacity(self):
        return sum([so.size for so in self._get_so()])

    lun_count = property(_get_lun_count)

    tpg_count = property(_get_tpg_count)

    sessions = property(_get_session_count)

    client_count = property(_get_client_count)

    gateway_name = property(_get_gateway_name)

    capacity = property(_get_capacity)

    def get_stats(self):

        start = time.time()

        # populate gateway instance with the latest configuration from rtslib
        self.refresh()

        # Overtime they'll be churn in client and disks so we need to drop
        # any entries from prior runs that are no longer seen in the iscsi
        # configuration with the prune method
        self.prune()

        end = time.time()

        self.logger.info("LIO stats took {}s".format(end - start))

        return self.dump()

