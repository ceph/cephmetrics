#! /usr/bin/env python

import sys
import json

fin = open(sys.argv[1])
a = json.loads(fin.read())
fin.close()

b = {
    'meta': {},
    'dashboard': a,
}

fout = open(sys.argv[1], "w")
fout.write(json.dumps(b, indent=3))
fout.close()
