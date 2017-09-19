#!/usr/bin/env python

import time
import glob

from collectors.base import BaseCollector
from collectors.common import get_hostname, merge_dicts


class RGW(BaseCollector):

    simple_metrics = {
        "req": ("requests", "derive"),
        "failed_req": ("requests_failed", "derive"),
        "get": ("gets", "derive"),
        "get_b": ("get_bytes", "derive"),
        "put": ("puts", "derive"),
        "put_b": ("put_bytes", "derive"),
        "qlen": ("qlen", "derive"),
        "qactive": ("requests_active", "derive")
    }

    int_latencies = [
        "get_initial_lat",
        "put_initial_lat"
    ]

    latencies = {
        "get_initial_lat_sum": ("get_initial_lat_sum", "derive"),
        "get_initial_lat_avgcount": ("get_initial_lat_avgcount", "derive"),
        "put_initial_lat_sum": ("put_initial_lat_sum", "derive"),
        "put_initial_lat_avgcount": ("put_initial_lat_avgcount", "derive")
    }

    all_metrics = merge_dicts(simple_metrics, latencies)

    def __init__(self, *args, **kwargs):
        BaseCollector.__init__(self, *args, **kwargs)

        self.host_name = get_hostname()

    def _get_rgw_data(self):

        rgw_sockets = glob.glob('/var/run/ceph/{}-client.rgw.'
                                '{}.*asok'.format(self.cluster_name,
                                                  self.host_name))
        if rgw_sockets:

            if len(rgw_sockets) > 1:
                self.logger.warning("multiple rgw sockets found - "
                                    "data sent from {}".format(rgw_sockets[0]))

            response = self._admin_socket(socket_path=rgw_sockets[0])

            if response:
                key_name = 'client.rgw.{}'.format(self.host_name)
                return response.get(key_name)
            else:
                # admin_socket call failed
                return {}
        else:
            # no socket found on the host, nothing to send to caller
            return {}

    @staticmethod
    def stats_filter(stats):
        # pick out the simple metrics

        filtered = {key: stats[key] for key in RGW.simple_metrics}

        for key in RGW.int_latencies:
            for _attr in stats[key]:
                new_key = "{}_{}".format(key, _attr)
                filtered[new_key] = stats[key].get(_attr)

        return filtered

    def get_stats(self):

        start = time.time()

        raw_stats = self._get_rgw_data()
        if raw_stats:
            stats = RGW.stats_filter(raw_stats)
        else:
            stats = {}
            self.error = True
            msg = 'RGW socket not available...radosgw running?'
            self.error_msgs = [msg]
            self.logger.warning(msg)

        stats['ceph_version'] = self.version

        end = time.time()

        self.logger.info("RGW get_stats : {:.3f}s".format((end - start)))

        return {
                "rgw": stats
        }
