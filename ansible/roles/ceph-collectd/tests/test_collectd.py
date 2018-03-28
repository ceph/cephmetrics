import pytest

testinfra_hosts = ['!ceph-grafana']


class TestCollectd(object):
    def maybe_skip(self, host):
        vars = host.ansible.get_variables()
        if vars.get('backend', dict()).get('metrics', 'mgr') != 'cephmetrics':
            pytest.skip()

    def test_service_enabled(self, host):
        self.maybe_skip(host)
        assert host.service('collectd').is_enabled
        assert host.service('collectd').is_running

    def test_logfile_present(self, host):
        self.maybe_skip(host)
        assert host.file('/var/log/collectd-cephmetrics.log').is_file
