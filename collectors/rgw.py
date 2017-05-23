#!/usr/bin/env python

from collectors.base import BaseCollector
from collectors.utils import get_hostname, merge_dicts

__author__ = "paul.cuzner@redhat.com"


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

    latencies = {
        "get_initial_lat": ("get_initial_lat", "gauge"),
        "put_initial_lat": ("put_initial_lat", "gauge")
    }

    all_metrics = merge_dicts(simple_metrics, latencies)

    def __init__(self, cluster_name, admin_socket):
        BaseCollector.__init__(self, cluster_name, admin_socket)
        self.host_name = get_hostname()

    def _get_rgw_data(self):

        response = self._admin_socket()

        key_name = 'client.rgw.{}'.format(self.host_name)

        return response.get(key_name)

    def _filter(self, stats):
        # pick out the simple metrics

        filtered = {key: stats[key] for key in RGW.simple_metrics}

        for key in RGW.latencies:
            latency = stats[key]['sum'] / stats[key]['avgcount']
            filtered[key] = latency

        return filtered

    def get_stats(self):

        raw_stats = self._get_rgw_data()

        stats = self._filter(raw_stats)

        return {"rgw": stats}
