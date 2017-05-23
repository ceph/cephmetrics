#!/usr/bin/env python
from ceph_daemon import admin_socket
import json

class BaseCollector(object):

    def __init__(self, cluster_name, admin_socket=None):
        self.cluster_name = cluster_name
        self.admin_socket = admin_socket

    def _admin_socket(self, cmds=None):
        if not cmds:
            cmds = ['perf', 'dump']

        response = admin_socket(self.admin_socket, cmds,
                                format='json')
        return json.loads(response)

    def get_stats(self):

        return {}
