#!/usr/bin/env python


import socket


def get_hostname():
    return socket.gethostname().split('.')[0]


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
    :return: (str) contents of the file
    """

    with open(file_name, 'r') as f:
        setting = f.read().rstrip()
    return setting 


def freadlines(file_name=None):
    """
    simple readlines function to return all records of a given file
    :param file_name: (str) file name to read
    :return: (list) contents of the file
    """

    with open(file_name, 'r') as f:
        data = f.readlines()
    return data
