#! /usr/bin/env python

import sys
import json

fin = open(sys.argv[1])
a = json.loads(fin.read())
fin.close()

b = {
    'dashboard': {
        'rows': [],
        'templating': a['dashboard']['templating'],
    },
}

for row in a['dashboard']['rows']:
    b['dashboard']['rows'].append({
        'title': row['title'],
        'panels': [],
    })
    for panel in row['panels']:
        np = {'title': panel['title'] }

        if 'targets' in panel.keys():
            np['targets'] = panel['targets']

        if 'datasource' in panel.keys():
            np['datasource'] = 'Prometheus'

        b['dashboard']['rows'][-1]['panels'].append(np)

fout = open(sys.argv[1], "w")
fout.write(json.dumps(b, indent=3))
fout.close()
