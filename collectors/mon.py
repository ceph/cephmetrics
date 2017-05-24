#!/usr/bin/env python

import rados
import json

from collectors.base import BaseCollector
from collectors.utils import add_dicts, merge_dicts

class Mon(BaseCollector):

    health = {
        "HEALTH_OK": 0
    }

    # metrics are declared, where each element has a description and collectd
    # data type. The description is used to ensure the names sent by collectd
    # remain the same even if the source name changes in ceph.
    cluster_metrics = {
        "num_mon": ("num_mon", "gauge"),
        "num_mon_quorum": ("num_mon_quorum", "gauge"),
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

    all_metrics = merge_dicts(pool_recovery_metrics, pool_client_metrics)
    all_metrics = merge_dicts(all_metrics, cluster_metrics)

    def _mon_command(self, cmd_request):
        """ Issue a command to the monitor """

        buf_s = '{}'
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)

        with rados.Rados(conffile=conf_file) as cluster:
            cmd = {'prefix': cmd_request, 'format': 'json'}
            rc, buf_s, out = cluster.mon_command(json.dumps(cmd), b'')

        return json.loads(buf_s)

    def _mon_health(self):

        cluster_data = self._admin_socket().get('cluster')
        health_text = self._mon_command("health").get('overall_status',
                                                      'UNKNOWN')
        health_num = Mon.health.get(health_text, 16)

        cluster = {Mon.cluster_metrics[k][0]: cluster_data[k]
                   for k in cluster_data}

        cluster['health'] = health_num

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
                pool_md = client_io
            else:
                pool_md = Mon._seed(Mon.pool_client_metrics)

            if recovery:
                pool_md = merge_dicts(pool_md, recovery)
            else:
                pool_md = merge_dicts(pool_md, Mon._seed(
                    Mon.pool_recovery_metrics))

            pool_stats[pool_name] = pool_md

        all_pools = merge_dicts(Mon._seed(Mon.pool_client_metrics),
                                Mon._seed(Mon.pool_recovery_metrics))

        # now walk all the pools to generate an _all_ entry
        for pool_name in pool_stats:
            pool_md = pool_stats[pool_name]
            all_pools = add_dicts(all_pools, pool_md)

        pool_stats['_all_'] = all_pools

        return pool_stats


    def get_stats(self):
        """
        method associated with the plugin callback to gather the metrics
        :return:
        """

        pool_stats = self._get_pool_stats()
        cluster_state = self._mon_health()

        return {"pools": pool_stats, "cluster": cluster_state}

