#!/usr/bin/env python

from collectors.osd import OSDs
from collectors.utils import flatten_dict

import time

def main():
    o = OSDs('ceph')
    ctr = 0
    while ctr < 30:

        s = o.get_stats()
        print(s)
        print(flatten_dict(s))

        time.sleep(1)
        ctr += 1

if __name__ == "__main__":
    main()
