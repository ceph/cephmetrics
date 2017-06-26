#!/usr/bin/env python

import rados
import rbd
import json
import threading
import time

from collectors.base import BaseCollector
from collectors.common import add_dicts, merge_dicts, get_hostname

class RBDScanner(threading.Thread):

    def __init__(self, cluster_name, pool_name):
        self.cluster_name = cluster_name
        self.pool_name = pool_name
        self.num_rbds = 0
        threading.Thread.__init__(self)

    def run(self):
        rbd_images = []
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)
        with rados.Rados(conffile=conf_file) as cluster:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                rbd_inst = rbd.RBD()
                rbd_images = rbd_inst.list(ioctx)

        self.num_rbds = len(rbd_images)


class Mon(BaseCollector):

    health = {
        "HEALTH_OK": 0,
        "HEALTH_WARN": 4,
        "HEALTH_ERR": 8
    }

    osd_state = {
        "up": 0,
        "down": 1
    }

    # metrics are declared, where each element has a description and collectd
    # data type. The description is used to ensure the names sent by collectd
    # remain the same even if the source name changes in ceph.
    cluster_metrics = {
        "num_mon": ("num_mon", "gauge"),
        "num_mon_quorum": ("num_mon_quorum", "gauge"),
        "num_rbds": ("num_rbds", "gauge"),
        "num_osd_hosts": ("num_osd_hosts", "gauge"),
        "num_osd": ("num_osd", "gauge"),
        "num_osd_up": ("num_osd_up", "gauge"),
        "num_osd_in": ("num_osd_in", "gauge"),
        "osd_epoch": ("osd_epoch", "gauge"),
        "osd_bytes": ("osd_bytes", "gauge"),
        "osd_bytes_used": ("osd_bytes_used", "gauge"),
        "osd_bytes_avail": ("osd_bytes_avail", "gauge"),
        "num_pool": ("num_pool", "gauge"),
        "num_pg": ("num_pg", "gauge"),
        "num_pg_active_clean": ("num_pg_active_clean", "gauge"),
        "num_pg_active": ("num_pg_active", "gauge"),
        "num_pg_peering": ("num_pg_peering", "gauge"),
        "num_object": ("num_object", "gauge"),
        "num_object_degraded": ("num_object_degraded", "gauge"),
        "num_object_misplaced": ("num_object_misplaced", "gauge"),
        "num_object_unfound": ("num_object_unfound", "gauge"),
        "num_bytes": ("num_bytes", "gauge"),
        "num_mds_up": ("num_mds_up", "gauge"),
        "num_mds_in": ("num_mds_in", "gauge"),
        "num_mds_failed": ("num_mds_failed", "gauge"),
        "mds_epoch": ("mds_epoch", "gauge"),
        "health": ("health", "gauge")
    }

    pool_client_metrics = {
        'bytes_sec': ("bytes_sec", "gauge"),
        'op_per_sec': ("op_per_sec", "gauge"),
        'read_bytes_sec': ("read_bytes_sec", "gauge"),
        'write_op_per_sec': ("write_op_per_sec", "gauge"),
        'write_bytes_sec': ("write_bytes_sec", "gauge"),
        'read_op_per_sec': ("read_op_per_sec", "gauge")
    }

    pool_recovery_metrics = {
        "recovering_objects_per_sec": ("recovering_objects_per_sec", "gauge"),
        "recovering_bytes_per_sec": ("recovering_bytes_per_sec", "gauge"),
        "recovering_keys_per_sec": ("recovering_keys_per_sec", "gauge"),
        "num_objects_recovered": ("num_objects_recovered", "gauge"),
        "num_bytes_recovered": ("num_bytes_recovered", "gauge"),
        "num_keys_recovered": ("num_keys_recovered", "gauge")
    }

    osd_metrics = {
        "status": ("status", "gauge")
    }

    mon_states = {
        "mon_status": ("mon_status", "gauge")
    }

    all_metrics = merge_dicts(pool_recovery_metrics, pool_client_metrics)
    all_metrics = merge_dicts(all_metrics, cluster_metrics)
    all_metrics = merge_dicts(all_metrics, osd_metrics)
    all_metrics = merge_dicts(all_metrics, mon_states)

    def _mon_command(self, cmd_request):
        """ Issue a command to the monitor """

        buf_s = '{}'
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)

        start = time.time()
        with rados.Rados(conffile=conf_file) as cluster:
            cmd = {'prefix': cmd_request, 'format': 'json'}
            rc, buf_s, out = cluster.mon_command(json.dumps(cmd), b'')
        end = time.time()

        self.elapsed_log_msg("_mon_command call for {}".format(cmd_request),
                             (end - start))

        return json.loads(buf_s)

    def _mon_health(self):

        cluster_data = self._admin_socket().get('cluster')
        health_data = self._mon_command("health")
        health_text = health_data.get('overall_status',
                                      'UNKNOWN')

        health_num = Mon.health.get(health_text, 16)

        cluster = {Mon.cluster_metrics[k][0]: cluster_data[k]
                   for k in cluster_data}

        cluster['health'] = health_num

        services = health_data.get('health').get('health_services')
        monstats = {}
        for svc in services:
            if 'mons' in svc:
                monstats = { mon.get('name'): Mon.health.get(mon.get('health'))
                             for mon in svc.get('mons')}

        cluster['mon_status'] = monstats

        return cluster

    @classmethod
    def _seed(cls, metrics):
        return {metrics[key][0]: 0 for key in metrics}

    def display_names(self, metric_format, metrics):
        """
        convert the keys to the static descriptions
        :return:
        """
        return {metric_format[k][0]: metrics[k]
                for k in metrics} if metrics else {}

    def _get_pool_stats(self):
        """ get pool stats from rados """

        raw_stats = self._mon_command('osd pool stats')
        pool_stats = {}

        # process each pool
        for pool in raw_stats:

            pool_name = pool['pool_name'].replace('.', '_')
            client_io = self.display_names(Mon.pool_client_metrics,
                                           pool.get('client_io_rate'))
            recovery = self.display_names(Mon.pool_recovery_metrics,
                                          pool.get('recovery_rate'))

            pool_md = {}
            if client_io:

                # Add pool level aggregation
                client_io['bytes_sec'] = client_io.get('read_bytes_sec', 0) + \
                    client_io.get('write_bytes_sec', 0)
                client_io["op_per_sec"] = client_io.get('read_op_per_sec', 0)+ \
                    client_io.get('write_op_per_sec', 0)
                pool_md = client_io

            else:
                pool_md = Mon._seed(Mon.pool_client_metrics)

            if recovery:
                pool_md = merge_dicts(pool_md, recovery)
            else:
                pool_md = merge_dicts(pool_md, Mon._seed(
                    Mon.pool_recovery_metrics))

            pool_stats[pool_name] = pool_md

        return pool_stats

    def _get_osd_states(self):

        raw = self._mon_command('osd tree')
        osds = {str(osd.get('id')): {"status":
                Mon.osd_state.get(osd.get('status'))}
                for osd in raw.get('nodes')
                if osd.get('type') == 'osd'}

        num_osd_hosts = len([node.get('name') for node in raw.get('nodes')
                             if node.get('type') == 'host'])

        return num_osd_hosts, osds

    @staticmethod
    def _select_pools(pools, mons):
        """
        determine the pools this mon should scan based on it's name. We select
        pools from the an offset into the pool list, and then repeat at an
        interval set by # mons in the configuration. This splits up the pools
        we have, so each mon looks at a discrete set of pools instead of all
        mons performing all scans.
        :param pools: (list) rados pool names
        :param mons: (list) monitor names from ceph health
        :return: (list) of pools this monitor should scan. empty list if the
                 monitor name mismatches - so no scans done
        """

        pools_to_scan = []

        try:
            freq = mons.index(get_hostname())
        except ValueError:
            # this host's name is not in the monitor list?
            # twilight zone moment
            pass
        else:

            pools_to_scan = [pools[ptr]
                             for ptr in xrange(freq, len(pools), len(mons))]

        return pools_to_scan

    def get_pools(self):

        start = time.time()
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)
        with rados.Rados(conffile=conf_file) as cluster:
            rados_pools = sorted(cluster.list_pools())
        end = time.time()

        self.logger.debug('lspools took {0:.2f} secs'.format(end - start))

        return rados_pools

    def _get_rbds(self, monitors):

        pool_list = self.get_pools()
        mon_list = sorted(monitors.keys())
        my_pools = Mon._select_pools(pool_list, mon_list)
        threads = []

        start = time.time()

        for pool in my_pools:
            thread = RBDScanner(self.cluster_name, pool)
            thread.start()
            threads.append(thread)

        # wait for all threads
        for thread in threads:
            thread.join()

        end = time.time()
        self.elapsed_log_msg("rbd scans", (end - start))

        total_rbds = sum([thread.num_rbds for thread in threads])

        for thread in threads:
            del thread

        return total_rbds

    def get_stats(self):
        """
        method associated with the plugin callback to gather the metrics
        :return:
        """

        start = time.time()

        pool_stats = self._get_pool_stats()
        num_osd_hosts, osd_states = self._get_osd_states()
        cluster_state = self._mon_health()
        cluster_state['num_osd_hosts'] = num_osd_hosts
        cluster_state['num_rbds'] = self._get_rbds(cluster_state['mon_status'])

        all_stats = merge_dicts(cluster_state, {"pools": pool_stats,
                                                "osd_state": osd_states})

        end = time.time()
        self.elapsed_log_msg("mon get_stats call", (end - start))

        return {"mon": all_stats}

