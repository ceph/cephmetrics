import json
import pytest

testinfra_hosts = ['mgrs']


class TestMgr(object):
    def maybe_skip(self, host):
        vars = host.ansible.get_variables()
        if vars.get('backend', dict()).get('metrics', 'mgr') != 'mgr':
            pytest.skip()

    def test_prometheus_module(self, host):
        self.maybe_skip(host)
        out = host.check_output("sudo ceph mgr module ls")
        obj = json.loads(out)
        assert 'prometheus' in obj['enabled_modules']

