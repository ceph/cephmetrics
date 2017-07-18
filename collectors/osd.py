#!/usr/bin/env python

import os
import time

from collectors.base import BaseCollector
from collectors.common import (todict, freadlines, merge_dicts,
                               IOstat, Disk)

__author__ = "Paul Cuzner"


class OSDstats(object):

    osd_capacity = {
        "stat_bytes": ("stat_bytes", "gauge"),
        "stat_bytes_used": ("stat_bytes_used", "gauge"),
        "stat_bytes_avail": ("stat_bytes_avail", "gauge")
    }

    filestore_metrics = {
        "journal_latency",
        "commitcycle_latency",
        "apply_latency",
        "queue_transaction_latency_avg"
    }

    def __init__(self):
        self._current = {}
        self._previous = {}


    def update(self, stats):
        """
        update the objects attributes based on the dict
        :param stats: (dict) containing filestore performance ('filestore')
               and capacity info ('osd')
        :return: None
        """

        if self._current:
            self._previous = self._current
            self._current = stats['filestore']
        else:
            self._current = stats['filestore']

        for attr in OSDstats.filestore_metrics:

            if self._previous:
                d_sum = self._current[attr].get('sum') - \
                        self._previous[attr].get('sum')
                d_avgcount = self._current[attr].get('avgcount') - \
                             self._previous[attr].get('avgcount')

                if d_sum == 0 or d_avgcount == 0:
                    val = 0
                else:
                    val = float(d_sum) / d_avgcount
            else:
                # no previous value, so set to 0
                val = 0

            setattr(self, attr, val)

        for attr in stats['osd']:
            setattr(self, attr, stats['osd'].get(attr))


class OSDs(BaseCollector):

    all_metrics = merge_dicts(Disk.metrics, IOstat.metrics)

    def __init__(self, cluster_name, **kwargs):
        BaseCollector.__init__(self, cluster_name, **kwargs)
        self.timestamp = int(time.time())

        self.osd = {}		# dict of disk objects, each disk contains osd_id
        self.jrnl = {}      # dict of journal devices (if not collocated)
        self.osd_id_list = []
        self.dev_lookup = {}    # dict dev_name -> osd | jrnl
        self.osd_count = 0

    def __repr__(self):

        s = ''
        for disk in self.osd:
            s += "{}\n".format(disk)
            dev = self.osd[disk]

            for var in vars(dev):
                if not var.startswith('_'):
                    s += "{} ... {}\n".format(var, getattr(dev, var))
        return s

    def _fetch_osd_stats(self, osd_id):

        # NB: osd stats are cumulative

        stats = {}
        osd_socket_name = '/var/run/ceph/{}-osd.{}.asok'.format(self.cluster_name,
                                                                osd_id)

        if not os.path.exists(osd_socket_name):
            # all OSD's should expose an admin socket, so if it's missing
            # this node has a problem!
            raise IOError("Socket file missing for OSD {}".format(osd_id))

        self.logger.debug("fetching osd stats for osd {}".format(osd_id))
        resp = self._admin_socket(socket_path=osd_socket_name)

        filestore_stats = resp.get('filestore')
        stats['filestore'] = {key_name: filestore_stats.get(key_name)
                              for key_name in OSDstats.filestore_metrics}

        osd_stats = resp.get('osd')

        # Add disk usage stats
        stats['osd'] = {key_name: osd_stats.get(key_name)
                        for key_name in OSDstats.osd_capacity.keys()}

        return stats

    def _dev_to_osd(self):
        """
        Look at the system to determine which disks are acting as OSD's
        """

        # the logic here uses the mount points to determine which OSD's are
        # in the system - so the focus is on filestore (XFS) OSD's. Another
        # approach could be to go directly to the admin socket (status cmd)
        # to get the osd_fsid, and then lookup that in /dev/disk/by-partuuid
        # to derive the osd device name...

        osd_indicators = {'var', 'lib', 'osd'}

        for mnt in freadlines('/proc/mounts'):
            items = mnt.split(' ')
            dev_path, path_name = items[:2]
            if path_name.startswith('/var/lib'):
                # take a close look since this is where ceph osds usually
                # get mounted
                dirs = set(path_name.split('/'))
                if dirs.issuperset(osd_indicators):
                    osd_id = path_name.split('-')[-1]

                    osd_device = dev_path.split('/')[-1]

                    if osd_device not in self.osd:
                        self.osd[osd_device] = Disk(osd_device,
                                                    path_name=path_name,
                                                    osd_id=osd_id)
                        self.dev_lookup[osd_device] = 'osd'
                        self.osd_count += 1

                    if osd_id not in self.osd:
                        self.osd[osd_id] = OSDstats()
                        self.osd_id_list.append(osd_id)

                    journal_link = os.path.join(path_name, 'journal')
                    if os.path.exists(journal_link):
                        # this is a filestore based OSD
                        jrnl_path = os.path.realpath(journal_link)
                        jrnl_dev = jrnl_path.split('/')[-1]

                        if jrnl_dev not in self.osd:
                            self.jrnl[jrnl_dev] = Disk(jrnl_dev,
                                                       osd_id=osd_id)

                            self.dev_lookup[jrnl_dev] = 'jrnl'

                    else:
                        # No journal..?
                        pass

    def _stats_lookup(self):
        """
        Grab the disk stats from /proc
        """

        now = time.time()
        interval = int(now) - self.timestamp
        self.timestamp = int(now)

        # Fetch diskstats from the OS
        for perf_entry in freadlines('/proc/diskstats'):

            field = perf_entry.split()
            dev_name = field[2]

            device = None
            if self.dev_lookup.get(dev_name, None) == 'osd':
                device = self.osd[dev_name]
            elif self.dev_lookup.get(dev_name, None) == 'jrnl':
                device = self.jrnl[dev_name]

            if device:
                new_stats = field[3:]

                if device.perf._current:
                    device.perf._previous = device.perf._current
                    device.perf._current = new_stats
                else:
                    device.perf._current = new_stats
                
                device.perf.compute(interval)
                device.refresh()

        end = time.time()
        self.logger.debug("OS disk stats calculated in "
                          "{:.4f}s".format(end-now))

        # fetch stats from each osd daemon
        osd_stats_start = time.time()
        for osd_id in self.osd_id_list:
            osd_stats = self._fetch_osd_stats(osd_id)
            # self.logger.debug('stats : {}'.format(osd_stats))
            osd_device = self.osd[osd_id]
            osd_device.update(osd_stats)
        osd_stats_end = time.time()
        self.logger.debug("OSD perf dump stats collected for {} OSDs "
                          "in {:.3f}s".format(len(self.osd_id_list),
                                          (osd_stats_end - osd_stats_start)))

    @staticmethod
    def _dump_devs(device_dict):

        dumped = {}

        for dev_name in sorted(device_dict):
            device = device_dict[dev_name]
            dumped[dev_name] = todict(device)

        return dumped

    def dump(self):
        """
        dump the osd object(s) to a dict. The object *must* not have references
        to other objects - if this rule is broken cephmetrics caller will fail
        when parsing the dict

        :return: (dict) dictionary representation of this OSDs on this host
        """

        return {
            "num_osds": self.osd_count,
            "osd": OSDs._dump_devs(self.osd),
            "jrnl": OSDs._dump_devs(self.jrnl)
        }

    def get_stats(self):

        start = time.time()

        self._dev_to_osd()
        self._stats_lookup()

        end = time.time()

        self.logger.info("osd get_stats call "
                         ": {:.3f}s".format((end - start)))

        return self.dump()
