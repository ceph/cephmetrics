#!/usr/bin/env python

from collectors.base import BaseCollector

__author__ = "Paul Cuzner"

OBS_INTERVAL_MS = 1000


class Disk(object):

    def _get_size(self):
        path = "/sys/block/{}/size".format(self.name)
        with open(path, 'r') as f:
            s = f.read().rstrip()
       
        return int(s) * 512


class IOstat(object):
    raw_metrics = [
        "reads",
        "reads_mrgd",
        "sectors_read",
        "read_ms",
        "writes",
        "writes_mrgd",
        "sectors_written",
        "write_ms",
        "current_io",
        "ms_active_io",
        "ms_active_io_w"
    ]

    metrics = [ 
        "util"
    ]

    def __init__(self):
        self.previous = []
        self.current = []

    def __str__(self):
        s='\n'
        for key in self.__dict__:
            s += '\t{} ... {}\n'.format(key, getattr(self, key))
        return s

    def _calc_raw_delta(self):
        if not self.previous:
            print("nothing to compute yet")
            for ptr in range(len(IOstat.raw_metrics)):
                key = IOstat.raw_metrics[ptr]
                setattr(self, key, 0)
        else:
            for ptr in range(len(IOstat.raw_metrics)):
                key = IOstat.raw_metrics[ptr]
                setattr(self, key, (int(self.current[ptr]) -
                                    int(self.previous[ptr])))

    def compute(self):
        """
        Calculate the iostats for this device 
        """
        self._calc_raw_delta()
        num_secs = (OBS_INTERVAL_MS / 1000)
        total_io = self.reads + self.writes

        self.util = float(self.ms_active_io)/ OBS_INTERVAL_MS * 100
        self.iops = int(total_io) / num_secs
        self.r_iops = int(self.reads) / num_secs
        self.w_iops = int(self.writes) / num_secs
        self.await = float(self.ms_active_io) / total_io if total_io > 0 else 0


class OSDs(BaseCollector):

    def __init__(self, cluster_name):
        BaseCollector.__init__(self, cluster_name)

        self.mounts = open('/proc/mounts', 'r')
        self.stats = open('/proc/diskstats', 'r')

        self.osd = {}		# dict of disk objects, each disk contains osd_id

    def __str__(self):

        s = ''
        for disk in self.osd:
            s += "{}\n".format(disk)
            dev = self.osd[disk]

            for var in dev.__dict__:
                s += "{} ... {}\n".format(var, getattr(dev, var))
        return s

    def _dev_to_osd(self):
        """
        Look at the system to determine which disks are acting as OSD's
        """

        osd_indicators = {'var', 'lib', 'osd'}
        mounts = self.mounts.readlines()
        self.mounts.seek(0)
        for mnt in mounts:
            items = mnt.split(' ')
            dev_path, path_name = items[:2]
            if path_name.startswith('/var/lib'):
                # take a close look since this is where ceph osds usually
                # get mounted
                dirs = set(path_name.split('/'))
                if dirs.issuperset(osd_indicators):
                    osd_id = path_name.split('-')[-1]
                    device = filter(lambda ch: ch.isalpha(), dev_path.split('/')[-1])
                    if device not in self.osd:
                        disk = Disk()
                        disk.name = device
                        disk.osd_id = osd_id
                        disk.perf = IOstat()
                        disk.size = disk._get_size()
                        self.osd[device] = disk

    def _get_stats(self):
        """
        Grab the disk stats from /proc
        """

        stats = self.stats.readlines()
        self.stats.seek(0)
        for perf_entry in stats:
            field = perf_entry.split()
            dev_name = field[2]
            if dev_name in self.osd.keys():
                new_stats = field[3:]
                if self.osd[dev_name].perf.current:
                    self.osd[dev_name].perf.previous = self.osd[dev_name].perf.current
                    self.osd[dev_name].perf.current = new_stats
                else:
                    self.osd[dev_name].perf.current = new_stats
                
                self.osd[dev_name].perf.compute()

    def _stats_lookup(self):
        self._dev_to_osd()
        self._get_stats()

