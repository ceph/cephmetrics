#!/usr/bin/env python

import json
import time
import logging
import os

import socket
import struct
from ceph_argparse import parse_json_funcsigs, validate_command
import select

# from ceph_daemon import admin_socket
from collectors.common import os_cmd, cmd_exists

READ_CHUNK_SIZE = 4096

# the ceph admin_command function currently uses a blocking socket call
# which causes issues when the OSD doesn't respond to the perf dump command.
#
# To address this, cephmetrics includes a 'fork' of the admin_socket function
# until upstream adopts a non-blocking socket approach. Prior to 'forking'
# other options were considered; signal.SIGALRM(n) - not possible since
# the collectors run outside of the main thread, threading.Timer - leads to
# zombie threads, multiprocessing.Pool - generates another collectd process.

def admin_socket2(asok_path, cmd, format='', timeout=1):
    """

    Local non-blocking fork of the main ceph admin_command function

    Send a daemon (--admin-daemon) command 'cmd'.  asok_path is the
    path to the admin socket; cmd is a list of strings; format may be
    set to one of the formatted forms to get output in that form
    (daemon commands don't support 'plain' output).
    """

    def do_sockio(path, cmd_bytes):
        """ helper: do all the actual low-level stream I/O """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setblocking(0)
        sock.connect(path)
        try:
            sock.sendall(cmd_bytes + b'\0')
            ready = select.select([sock], [], [], timeout)
            if not ready[0]:
                raise RuntimeError("timeout of {} secs exceeded for "
                                   "initial response".format(timeout))

            len_str = sock.recv(4)
            if len(len_str) < 4:
                raise RuntimeError("no data returned from admin socket")
            l, = struct.unpack(">I", len_str)
            sock_ret = b''

            got = 0
            while got < l:
                # recv() receives signed int, i.e max 2GB
                # workaround by capping READ_CHUNK_SIZE per call.
                want = min(l - got, READ_CHUNK_SIZE)
                ready = select.select([sock], [], [], 0.2)
                if not ready[0]:
                    raise RuntimeError("'payload' timeout exceeded "
                                       "".format(timeout))
                bit = sock.recv(want)
                sock_ret += bit
                got += len(bit)

        except Exception as sock_e:
            raise RuntimeError('exception: ' + str(sock_e))
        return sock_ret

    try:
        cmd_json = do_sockio(asok_path,
                             b'{"prefix": "get_command_descriptions"}')
    except Exception as e:
        raise RuntimeError(
            'exception getting command descriptions: ' + str(e))

    if cmd == 'get_command_descriptions':
        return cmd_json

    sigdict = parse_json_funcsigs(cmd_json.decode('utf-8'), 'cli')
    valid_dict = validate_command(sigdict, cmd)
    if not valid_dict:
        raise RuntimeError('invalid command')

    if format:
        valid_dict['format'] = format

    try:
        ret = do_sockio(asok_path, json.dumps(valid_dict).encode('utf-8'))
    except Exception as e:
        raise RuntimeError('exception: ' + str(e))

    return ret


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
        self.cmd_timeout = 1

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
                response = admin_socket2(adm_socket, cmds,
                                         format='json',
                                         timeout=self.cmd_timeout)
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
