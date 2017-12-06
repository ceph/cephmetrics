#! /usr/bin/env python2

import sys
import json

def compatibility_check(a, b):
    a = a['dashboard']
    b = b['dashboard']
    assert len(a['templating']) == len(b['templating']), "(%d, %d)" % (len(a['templating']), len(b['templating']))
    assert len(a['rows']) == len(b['rows']), "%d, %d" % (len(a['rows']), len(b['rows']))
    for row_nr in range(len(a['rows'])):
        ra = a['rows'][row_nr]
        rb = b['rows'][row_nr]
        assert ra['title'] == rb['title'], 'row %d title assertion failed (%s, %s)' % (row_nr, ra['title'], rb['title'])
        assert len(ra['panels']) == len(rb['panels']), 'row %d panels assertion failed (%d, %d)' % (row_nr, len(ra['panels']), len(rb['panels']))
        for panel_nr in range(len(ra['panels'])):
            ta = a['rows'][row_nr]['panels'][panel_nr]['title']
            tb = b['rows'][row_nr]['panels'][panel_nr]['title']
            assert ta == tb, 'row %d panel %d title assertion failed (%s, %s)' % (row_nr, panel_nr, ta, tb)

def update(a, b):
    a = a['dashboard']
    b = b['dashboard']
    a['templating'] = b['templating']
    for row_nr in range(len(a['rows'])):
        ra = a['rows'][row_nr]
        rb = b['rows'][row_nr]
        for panel_nr in range(len(ra['panels'])):
            if 'datasource' in rb['panels'][panel_nr].keys():
                ra['panels'][panel_nr]['datasource'] = rb['panels'][panel_nr]['datasource']
            if 'targets' not in ra['panels'][panel_nr]:
                continue
            if 'targets' in rb['panels'][panel_nr]:
                ra['panels'][panel_nr]['targets'] = rb['panels'][panel_nr]['targets']

if len(sys.argv) != 4:
    print "Usage: %s <primary.json> <secondary.json> <out.json>"
    sys.exit(1)

fin = open(sys.argv[1])
a = json.loads(fin.read())
fin.close()

fin = open(sys.argv[2])
b = json.loads(fin.read())
fin.close()

compatibility_check(a, b)

update(a, b)

fout = open(sys.argv[3], "w")
fout.write(json.dumps(a, indent=4))
fout.close()
