import pytest

from .util import TestDashboards, get_dashboards


def walk(obj, callback, parent_key=None, path=None):
    if path is None:
        path = '.'
    if isinstance(obj, dict):
        for key, value in obj.items():
            walk(
                value,
                callback,
                parent_key=key,
                path='{}["{}"]'.format(path, key),
            )
    elif isinstance(obj, list):
        for i in range(len(obj)):
            walk(
                obj[i],
                callback,
                parent_key=parent_key,
                path='{}[{}]'.format(path, i),
            )
    else:
        callback(obj, parent_key, path)


class TestMgrDashboards(TestDashboards):
    dashboards = get_dashboards()

    @pytest.mark.parametrize("name", dashboards.keys())
    def test_type(self, name):
        assert name
        obj = self.dashboards[name]
        assert type(obj) is dict

    @pytest.mark.parametrize("name", dashboards.keys())
    def test_no_collectd(self, name):
        def test(item, pkey, path):
            if type(item) in (basestring, unicode):
                assert 'collectd' not in item
        walk(self.dashboards[name], test)

    @pytest.mark.parametrize("name", dashboards.keys())
    def test_no_ds_local(self, name):
        def test(item, pkey, path):
            if type(item) in (basestring, unicode):
                assert '${DS_LOCAL}' not in item
        walk(self.dashboards[name], test)

    @pytest.mark.parametrize("name", dashboards.keys())
    def test_no_influxdb_dstype(self, name):
        def test(item, pkey, path):
            if pkey == 'dsType' and type(item) in (basestring, unicode):
                assert 'influxdb' not in item
        walk(self.dashboards[name], test)

    @pytest.mark.parametrize("name", dashboards.keys())
    def test_no_influxdb_query(self, name):
        def test(item, pkey, path):
            if pkey == 'query':
                assert 'SELECT' not in item
                assert 'FROM' not in item
                assert 'WHERE' not in item
        walk(self.dashboards[name], test)
