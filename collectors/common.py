#!/usr/bin/env python


import socket
import os
import subprocess


def cmd_exists(command):
    return any(
        os.access(os.path.join(path, command), os.X_OK)
        for path in os.environ["PATH"].split(os.pathsep)
    )


def os_cmd(command):
    """
    Issue a command to the OS and return the output. NB. check_output default
    is shell=False
    :param command: (str) OS command
    :return: (str) command response (lines terminated with \n)
    """
    cmd_list = command.split(' ')
    if cmd_exists(cmd_list[0]):
        cmd_output = subprocess.check_output(cmd_list,
                                             stderr=subprocess.STDOUT).rstrip()
        return cmd_output
    else:
        return ''


def get_hostname():
    return socket.gethostname().split('.')[0]


def get_names():
    return [get_hostname()]


def add_dicts(dict1, dict2):
    """
    Add dictionary values together
    :param dict1:
    :param dict2:
    :return: dict with matching fields sum'd together
    """
    return {key: dict1.get(key, 0) + dict2.get(key, 0)
            for key in set(dict1).union(dict2)}


def merge_dicts(dict1, dict2):
    """
    merges two dicts together to form a single dict. when dict keys overlap
    the value in the 2nd dict takes precedence
    :param dict1:
    :param dict2:
    :return: combined dict
    """

    new = dict1.copy()
    new.update(dict2)

    return new


def flatten_dict(data, separator='.', prefix=''):
    """
    flatten a dict, so it is just simple key/value pairs
    :param data: (dict)
    :param separator: (str) char to use when combining keys
    :param prefix: key prefix
    :return:
    """
    return {prefix + separator + k if prefix else k: v
            for kk, vv in data.items()
            for k, v in flatten_dict(vv, separator, kk).items()
            } if isinstance(data, dict) else {prefix: data}


def todict(obj):
    """
    convert an object to a dict representation
    :param obj: (object) object to examine, to extract variables/values from
    :return: (dict) representation of the given object
    """
    data = {}
    for key, value in obj.__dict__.iteritems():

        if key.startswith('_'):
            continue

        try:
            data[key] = todict(value)
        except AttributeError:
            data[key] = value
    
    return data


def fread(file_name=None):
    """
    Simple read function for files of a single value
    :param file_name: (str) file name to read
    :return: (str) contents of the file, or null string for non-existent file
    """
    if os.path.exists(file_name):
        with open(file_name, 'r') as f:
            setting = f.read().rstrip()
        return setting
    else:
        return ''


def freadlines(file_name=None):
    """
    simple readlines function to return all records of a given file
    :param file_name: (str) file name to read
    :return: (list) contents of the file, empty if file doesn't exist
    """

    if os.path.exists(file_name):
        with open(file_name, 'r') as f:
            data = f.readlines()
        return data
    else:
        return []



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
        "bytes_per_sec": ("bytes_per_sec", "gauge"),
        "r_bytes_per_sec": ("r_bytes_per_sec", "gauge"),
        "w_bytes_per_sec": ("w_bytes_per_sec", "gauge"),
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
        s = '\n- IOstat object:\n'
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
            self.util = float(self._ms_active_io) / interval_ms * 100
            self.iops = int(total_io) / sample_interval
            self.r_iops = int(self._reads) / sample_interval
            self.w_iops = int(self._writes) / sample_interval
            self.await = float(
                self._write_ms + self._read_ms) / total_io if total_io > 0 else 0
            self.w_await = float(
                self._write_ms) / self._writes if self._writes > 0 else 0
            self.r_await = float(
                self._read_ms) / self._reads if self._reads > 0 else 0
            self.r_bytes_per_sec = (float(
                self._sectors_read * IOstat.sector_size)) / sample_interval
            self.w_bytes_per_sec = (float(
                self._sectors_written * IOstat.sector_size)) / sample_interval
            self.bytes_per_sec = self.r_bytes_per_sec + self.w_bytes_per_sec


class Disk(object):

    metrics = {
        "rotational": ("rotational", "gauge"),
        "disk_size": ("disk_size", "gauge"),
        "osd_id": ("osd_id", "gauge")
    }

    osd_types = {"filestore": 0,
                "bluestore": 1}

    def __init__(self, device_name, path_name=None, osd_id=None,
                 in_osd_type="filestore", encrypted=0):

        self._name = device_name
        self._path_name = path_name
        self._base_dev = Disk.get_base_dev(device_name)
        self.osd_id = osd_id

        self.rotational = self._get_rota()
        self.disk_size = self._get_size()
        self.perf = IOstat()
        self.encrypted = encrypted
        self.osd_type = Disk.osd_types[in_osd_type]

    def _get_size(self):
        size = fread("/sys/block/{}/size".format(self._base_dev))
        if size.isdigit():
            size = int(size) * 512
        else:
            size = 0
        return size

    def _get_rota(self):
        rota = fread("/sys/block/{}/queue/rotational".format(self._base_dev))
        if rota.isdigit():
            # 0 = flash/nvme/ssd, 1 = HDD
            return rota
        else:
            # default to a HDD response
            return 1

    @staticmethod
    def get_base_dev(dev_name):

        # for intelcas devices, just use the device name as is
        if dev_name.startswith('intelcas'):
            device = dev_name
        elif dev_name.startswith('nvme'):
            if 'p' in dev_name:
                device = dev_name[:(dev_name.index('p'))]
            else:
                device = dev_name
        else:
            # default strip any numeric ie. sdaa1 -> sdaa
            device = filter(lambda ch: ch.isalpha(), dev_name)

        return device

