#!/usr/bin/env python

import time

from collectors.base import BaseCollector
from collectors.common import (todict, freadlines, merge_dicts,
                               IOstat, Disk)

__author__ = "Paul Cuzner"


class OSDs(BaseCollector):

    all_metrics = merge_dicts(Disk.metrics, IOstat.metrics)

    def __init__(self, cluster_name, **kwargs):
        BaseCollector.__init__(self, cluster_name, **kwargs)
        self.timestamp = int(time.time())

        self.osd = {}		# dict of disk objects, each disk contains osd_id

    def __repr__(self):

        s = ''
        for disk in self.osd:
            s += "{}\n".format(disk)
            dev = self.osd[disk]

            for var in vars(dev):
                if not var.startswith('_'):
                    s += "{} ... {}\n".format(var, getattr(dev, var))
        return s

    def _dev_to_osd(self):
        """
        Look at the system to determine which disks are acting as OSD's
        """

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

                    device = filter(lambda ch: ch.isalpha(),
                                    dev_path.split('/')[-1])

                    if device not in self.osd:
                        disk = Disk()
                        disk._name = device
                        disk._path_name = path_name
                        disk.osd_id = osd_id
                        disk.rotational = disk._get_rota()
                        disk.perf = IOstat()
                        disk.disk_size = disk._get_size()
                        disk.refresh()
                        self.osd[device] = disk

    def _stats_lookup(self):
        """
        Grab the disk stats from /proc
        """

        now = time.time()
        interval = int(now) - self.timestamp
        self.timestamp = int(now)

        for perf_entry in freadlines('/proc/diskstats'):

            field = perf_entry.split()
            dev_name = field[2]

            if dev_name in self.osd.keys():
                new_stats = field[3:]
                device = self.osd[dev_name]
                if device.perf._current:
                    device.perf._previous = device.perf._current
                    device.perf._current = new_stats
                else:
                    device.perf._current = new_stats
                
                device.perf.compute(interval)
                device.refresh()

        end = time.time()
        self.elapsed_log_msg("disk performance stats generation", (end - now))

    def dump(self):

        osd_info = {}

        for dev in sorted(self.osd):
            device_obj = self.osd[dev]
            osd_info[dev] = todict(device_obj)

        return {"osd": osd_info}

    def get_stats(self):

        start = time.time()

        self._dev_to_osd()
        self._stats_lookup()

        end = time.time()

        self.elapsed_log_msg("osd get_stats call", (end - start))

        return self.dump()
