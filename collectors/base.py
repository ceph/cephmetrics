#!/usr/bin/env python

from ceph_daemon import admin_socket
import json
from collectors.common import CollectorLog
import time


class BaseCollector(object):

    def __init__(self, cluster_name, admin_socket=None, log_level='debug'):
        self.cluster_name = cluster_name
        self.admin_socket = admin_socket

        class_name = self.__class__.__name__
        self.logger = CollectorLog(log_type=class_name,
                                   log_level=log_level)

    def _admin_socket(self, cmds=None, socket_path=None):

        adm_socket = self.admin_socket if not socket_path else socket_path

        if not cmds:
            cmds = ['perf', 'dump']

        start = time.time()
        response = admin_socket(adm_socket, cmds,
                                format='json')
        end = time.time()

        self.elapsed_log_msg("admin_socket call for {}".format(' '.join(cmds)),
                             (end - start))
        return json.loads(response)

    def elapsed_log_msg(self, msg, elapsed_secs):
        self.logger.debug("{0} took {1:.2f} secs".format(msg,
                                                        elapsed_secs))

    def get_stats(self):

        return {}
