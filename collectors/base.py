#!/usr/bin/env python

import json
import time
import logging

from ceph_daemon import admin_socket


class BaseCollector(object):

    def __init__(self, cluster_name, admin_socket=None):
        self.cluster_name = cluster_name
        self.admin_socket = admin_socket

        self.logger = logging.getLogger('cephmetrics')

    def _admin_socket(self, cmds=None, socket_path=None):

        adm_socket = self.admin_socket if not socket_path else socket_path

        if not cmds:
            cmds = ['perf', 'dump']

        start = time.time()
        response = admin_socket(adm_socket, cmds,
                                format='json')
        end = time.time()

        self.logger.debug("admin_socket call '{}' : "
                          "{:.3f}s".format(' '.join(cmds),
                                           (end - start)))

        return json.loads(response)

    def get_stats(self):

        return {}
