#!/usr/bin/env python

import os
import time
import math

from collectors.base import BaseCollector
from collectors.common import (todict, fread, freadlines, merge_dicts,
                               IOstat, Disk)


class OSDstats(object):

    osd_capacity = {
        "stat_bytes": ("stat_bytes", "gauge"),
        "stat_bytes_used": ("stat_bytes_used", "gauge"),
        "stat_bytes_avail": ("stat_bytes_avail", "gauge")
    }

    perf_metrics = {
        "filestore": {
            "journal_latency",
            "commitcycle_latency",
            "apply_latency",
            "queue_transaction_latency_avg"
        },
        "bluestore": {
            "submit_lat",
            "throttle_lat",
            "state_aio_wait_lat",
            "kv_flush_lat",
            "kv_commit_lat"
        }
    }

    def __init__(self, osd_type='filestore'):
        self._current = {}
        self._previous = {}
        self._osd_type = osd_type
        self.osd_type = Disk.osd_types[osd_type]
        self.osd_percent_used = 0

    def update(self, stats):
        """
        update the objects attributes based on the 'stats' dict
        :param stats: (dict) containing performance ('filestore' or 'bluestore')
               and capacity info ('osd')
        :return: None
        """

        if self._current:
            self._previous = self._current
            self._current = stats[self._osd_type]
        else:
            self._current = stats[self._osd_type]

        for attr in OSDstats.perf_metrics[self._osd_type]:

            if attr not in self._current:
                # skip if the attribute needed isn't available
                # eg. early versions of bluestore didn't have a 'stable'
                # set of perf counters
                continue

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

        self.osd_percent_used = math.ceil((float(self.stat_bytes_used) /
                                           self.stat_bytes) * 100)


class OSDs(BaseCollector):

    all_metrics = merge_dicts(Disk.metrics, IOstat.metrics)
    supported_object_stores = ['filestore', 'bluestore']

    def __init__(self, *args, **kwargs):
        BaseCollector.__init__(self, *args, **kwargs)
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

    def _fetch_osd_stats(self, osd_id, osd_type='filestore'):

        # NB: osd stats are cumulative

        stats = {}
        osd_socket_name = '/var/run/ceph/{}-osd.{}.asok'.format(self.cluster_name,
                                                                osd_id)

        if not os.path.exists(osd_socket_name):
            # all OSD's should expose an admin socket, so if it's missing
            # the osd hasn't initialized properly or it's gone down
            msg = "Socket file missing for OSD {}".format(osd_id)
            self.logger.error(msg)
            self.error = True
            self.error_msg = msg
            return

        self.logger.debug("fetching osd stats for osd {}".format(osd_id))
        resp = self._admin_socket(socket_path=osd_socket_name)

        perf_stats = resp.get(osd_type)

        stats[osd_type] = {key_name: perf_stats.get(key_name)
                           for key_name in OSDstats.perf_metrics[osd_type]}

        osd_stats = resp.get('osd')

        # Add disk usage stats
        stats['osd'] = {key_name: osd_stats.get(key_name)
                        for key_name in OSDstats.osd_capacity.keys()}

        return stats

    @staticmethod
    def get_osd_type(osd_path):

        osd_type_fname = os.path.join(osd_path, 'type')
        if os.path.exists(osd_type_fname):
            return fread(osd_type_fname)
        else:
            if os.path.exists(os.path.join(osd_path, 'journal')):
                return "filestore"
            else:
                raise ValueError("Unrecognised OSD type")

    def _dev_to_osd(self):
        """
        Look at the system to determine which disks are acting as OSD's
        """

        # the logic here uses the mount points to determine which OSD's are
        # in the system. The encryption state is determine just by the use
        # devicemapper (i.e. /dev/mapper prefixed devices) - since at this time
        # this is all dm is used for.

        osd_indicators = {'var', 'lib', 'osd'}

        for mnt in freadlines('/proc/mounts'):
            items = mnt.split(' ')
            dev_path, path_name = items[:2]
            if path_name.startswith('/var/lib'):
                # take a close look since this is where ceph osds usually
                # get mounted
                dirs = set(path_name.split('/'))
                if dirs.issuperset(osd_indicators):

                    # get the osd_id from the name is the most simple way
                    # to get the id, due to naming conventions. If this fails
                    # though, plan 'b' is the whoami file
                    osd_id = path_name.split('-')[-1]
                    if not osd_id.isdigit():
                        osd_id = fread(os.path.join(path_name, 'whoami'))

                    if osd_id not in self.osd:
                        osd_type = OSDs.get_osd_type(path_name)
                        self.osd[osd_id] = OSDstats(osd_type=osd_type)
                        self.osd_id_list.append(osd_id)

                        osd_type = self.osd[osd_id]._osd_type
                        if osd_type == 'filestore':
                            if dev_path.startswith('/dev/mapper'):
                                encrypted = 1
                                uuid = dev_path.split('/')[-1]
                                partuuid = '/dev/disk/by-partuuid/{}'.format(uuid)
                                dev_path = os.path.realpath(partuuid)
                                osd_device = dev_path.split('/')[-1]
                            else:
                                encrypted = 0
                                osd_device = dev_path.split('/')[-1]

                        elif osd_type == 'bluestore':
                            block_link = os.path.join(path_name, 'block')
                            osd_path = os.path.realpath(block_link)
                            osd_device = osd_path.split('/')[-1]
                            encrypted = 0
                        else:
                            raise ValueError("Unknown OSD type encountered")

                        # if the osd_id hasn't been seem neither has the
                        # disk
                        self.osd[osd_device] = Disk(osd_device,
                                                    path_name=path_name,
                                                    osd_id=osd_id,
                                                    in_osd_type=osd_type,
                                                    encrypted=encrypted)
                        self.dev_lookup[osd_device] = 'osd'
                        self.osd_count += 1

                        if osd_type == 'filestore':
                            journal_link = os.path.join(path_name, 'journal')
                        else:
                            journal_link = os.path.join(path_name, 'block.wal')

                        if os.path.exists(journal_link):
                            link_tgt = os.readlink(journal_link)
                            if link_tgt.startswith('/dev/mapper'):
                                encrypted = 1
                            else:
                                encrypted = 0

                            partuuid_path = os.path.join('/dev/disk/by-partuuid',
                                                         link_tgt.split('/')[-1])
                            jrnl_path = os.path.realpath(partuuid_path)
                            jrnl_dev = jrnl_path.split('/')[-1]

                            if jrnl_dev not in self.osd:
                                self.jrnl[jrnl_dev] = Disk(jrnl_dev,
                                                           osd_id=osd_id,
                                                           in_osd_type=osd_type,
                                                           encrypted=encrypted)

                                self.dev_lookup[jrnl_dev] = 'jrnl'

                        else:
                            # No journal or WAL link..?
                            pass

    def _stats_lookup(self):
        """
        Grab the disk stats from /proc/diskstats, and the key osd perf dump
        counters
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

        end = time.time()
        self.logger.debug("OS disk stats calculated in "
                          "{:.4f}s".format(end-now))

        # fetch stats from each osd daemon
        osd_stats_start = time.time()
        for osd_id in self.osd_id_list:

            osd_type = self.osd[osd_id]._osd_type

            if osd_type in OSDs.supported_object_stores:

                osd_stats = self._fetch_osd_stats(osd_id, osd_type)
                if osd_stats:
                    osd_device = self.osd[osd_id]
                    osd_device.update(osd_stats)
                else:
                    self.logger.warning("OSD stats for osd.{} not "
                                        "available".format(osd_id))

            else:
                self.logger.warning("Unknown OSD type encountered for "
                                    "osd.{}".format(osd_id))

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

        osds = OSDs._dump_devs(self.osd)
        osds['ceph_version'] = self.version
        osds['num_osds'] = self.osd_count

        return {
            "osd": osds,
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
