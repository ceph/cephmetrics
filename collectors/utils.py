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
    return {prefix + separator + k if prefix else k: v
            for kk, vv in data.items()
            for k, v in flatten_dict(vv, separator, kk).items()
            } if isinstance(data, dict) else {prefix: data}