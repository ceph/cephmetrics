#!/usr/bin/env python

import json
import time
import logging
import os

from ceph_daemon import admin_socket
from collectors.common import os_cmd, cmd_exists


class BaseCollector(object):

    class_to_cmd = {
        "Mon": "ceph-mon",
        "RGW": "radosgw",
        "OSDs": "ceph-osd",
        "ISCSIGateway": "gwcli"
    }

    def __init__(self, parent, cluster_name, admin_socket=None):
        self._name = self.__class__.__name__
        self._parent = parent
        self.cluster_name = cluster_name
        self.admin_socket = admin_socket
        self.version = self.get_version()
        self.error = False
        self.error_msgs = []

        self.logger = logging.getLogger('cephmetrics')

        self.logger.info("ceph version for {}: {}".format(self._name,
                                                          self.version))

    def _admin_socket(self, cmds=None, socket_path=None):

        adm_socket = self.admin_socket if not socket_path else socket_path

        if not cmds:
            cmds = ['perf', 'dump']

        start = time.time()

        if os.path.exists(adm_socket):
            try:
                response = admin_socket(adm_socket, cmds,
                                        format='json')
            except RuntimeError as e:
                self.logger.error("admin_socket error: {}".format(e.message))
                self.error = True
                self.error_msgs = [e.message]
                resp = {}
            else:
                resp = json.loads(response)
        else:
            resp = {}

        end = time.time()

        self.logger.debug("admin_socket call '{}' : "
                          "{:.3f}s".format(' '.join(cmds),
                                           (end - start)))

        return resp

    def get_version(self):
        """
        Although the version number is v.r.m based, this isn't a float so it
        can't be stored as a number, so the version returned is just the
        vesion.release components (i.e. looks like a float!)
        :return: (float) version number (v.r format)
        """
        # version command returns output like this
        # ceph version 10.2.2-15.el7cp (60cd52496ca02bdde9c2f4191e617f75166d87b6)

        cmd = BaseCollector.class_to_cmd.get(self._name, 'ceph')
        vers_output = os_cmd('{} -v'.format(cmd))
        if vers_output:
            return float('.'.join(vers_output.split()[2].split('.')[:2]))
        else:
            return 0

    @classmethod
    def probe(cls):
        """
        Look for the relevant binary to signify a specific ceph role
        :return: (bool) showing whether the binary was found or not
        """

        return cmd_exists(BaseCollector.class_to_cmd.get(cls.__name__))

    def get_stats(self):

        return {}
