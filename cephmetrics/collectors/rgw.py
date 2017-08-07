#!/usr/bin/env python

import time

from cephmetrics.collectors import (base, common)

__author__ = "paul.cuzner@redhat.com"


class RGW(base.BaseCollector):

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

    all_metrics = common.merge_dicts(simple_metrics, latencies)

    def __init__(self, cluster_name, admin_socket, **kwargs):
        base.BaseCollector.__init__(self, cluster_name, admin_socket, **kwargs)
        self.host_name = common.get_hostname()

    def _get_rgw_data(self):

        response = self._admin_socket()

        key_name = 'client.rgw.{}'.format(self.host_name)

        return response.get(key_name)

    def _filter(self, stats):
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

        stats = self._filter(raw_stats)

        end = time.time()

        self.logger.info("RGW get_stats : {:.3f}s".format((end - start)))

        return {"rgw": stats}
