import pytest

testinfra_hosts = ['ceph-grafana']


class TestDocker(object):
    def maybe_skip(self, host):
        vars = host.ansible.get_variables()
        if vars.get('containerized', False) is False:
            pytest.skip()

    def test_docker_running(self, host):
        self.maybe_skip(host)
        assert host.service('docker').is_enabled
        assert host.service('docker').is_running
