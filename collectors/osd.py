#!/usr/bin/env python

import time
from os import statvfs

from collectors.base import BaseCollector
from collectors.utils import todict, fread, freadlines, merge_dicts


__author__ = "Paul Cuzner"


class Disk(object):

    metrics = {
        "rotational": ("rotational", "gauge"),
        "disk_size": ("disk_size", "gauge"),
        "fs_size": ("fs_size", "gauge"),
        "fs_used": ("fs_used", "gauge"),
        "osd_id": ("osd_id", "gauge")
    }

    def _get_size(self):
        return int(fread("/sys/block/{}/size".format(self._name))) * 512

    def _get_rota(self):
        return int(fread("/sys/block/{}/queue/rotational".format(self._name)))

    def _get_fssize(self):
        s = statvfs("{}/whoami".format(self._path_name))
        return s.f_blocks * s.f_bsize, s.f_bfree * s.f_bsize
  
    def refresh(self):
        self.fs_size, self.fs_used = self._get_fssize()


class IOstat(object):

    raw_metrics = [
        "_reads",
        "_reads_mrgd",
        "_sectors_read",
        "_read_ms",
        "_writes",
        "_writes_mrgd",
        "_sectors_written",
        "_write_ms",
        "_current_io",
        "_ms_active_io",
        "_ms_active_io_w"
    ]

    sector_size = 512

    metrics = {
        "iops": ("iops", "gauge"),
        "r_iops": ("r_iops", "gauge"),
        "w_iops": ("w_iops", "gauge"),
        "mbps": ("mbps", "gauge"),
        "r_mbps": ("r_mbps", "gauge"),
        "w_mbps": ("w_mbps", "gauge"),
        "util": ("util", "gauge"),
        "await": ("await", "gauge"),
        "r_await": ("r_await", "gauge"),
        "w_await": ("w_await", "gauge"),
    }

    def __init__(self):
        self._previous = []
        self._current = []
        
        # Seed the metrics we're interested in 
        for ctr in IOstat.metrics.keys():
            setattr(self, ctr, 0)

    def __str__(self):
        s='\n- IOstat object:\n'
        for key in sorted(vars(self)):
            s += '\t{} ... {}\n'.format(key, getattr(self, key))
        return s

    def _calc_raw_delta(self):
        if not self._previous:
            # nothing to compute yet
            for ptr in range(len(IOstat.raw_metrics)):
                key = IOstat.raw_metrics[ptr]
                setattr(self, key, 0)
        else:
            for ptr in range(len(IOstat.raw_metrics)):
                key = IOstat.raw_metrics[ptr]
                setattr(self, key, (int(self._current[ptr]) -
                                    int(self._previous[ptr])))

    def compute(self, sample_interval):
        """
        Calculate the iostats for this device 
        """

        self._calc_raw_delta()

        if sample_interval > 0:	

            interval_ms = sample_interval * 1000
            total_io = self._reads + self._writes
            self.util = float(self._ms_active_io)/ interval_ms * 100
            self.iops = int(total_io) / sample_interval
            self.r_iops = int(self._reads) / sample_interval
            self.w_iops = int(self._writes) / sample_interval
            self.await = float(
                self._write_ms + self._read_ms) / total_io if total_io > 0 else 0
            self.w_await = float(self._write_ms) / self._writes if self._writes > 0 else 0 
            self.r_await = float(self._read_ms) / self._reads if self._reads > 0 else 0 
            self.r_mbps = (float(self._sectors_read * IOstat.sector_size)/1024**2) / sample_interval
            self.w_mbps = (float(self._sectors_written * IOstat.sector_size)/1024**2) / sample_interval
            self.mbps = self.r_mbps + self.w_mbps


class OSDs(BaseCollector):

    all_metrics = merge_dicts(Disk.metrics, IOstat.metrics)

    def __init__(self, cluster_name):
        BaseCollector.__init__(self, cluster_name)
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

        now = int(time.time())
        interval = now - self.timestamp
        self.timestamp = now

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

    def dump(self):

        osd_info = {}

        for dev in sorted(self.osd):
            device_obj = self.osd[dev]
            osd_info[dev] = todict(device_obj)

        return {"osd": osd_info}

    def get_stats(self):

        self._dev_to_osd()
        self._stats_lookup()

        return self.dump()
