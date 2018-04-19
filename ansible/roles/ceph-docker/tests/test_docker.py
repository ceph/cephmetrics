import pytest

testinfra_hosts = ['ceph-grafana']


class TestDocker(object):
    def maybe_skip(self, host):
        services = ['grafana', 'prometheus']

        def is_containerized(service):
            vars = host.ansible.get_variables()
            return vars.get(service, dict()).get('containerized')
        if not any(map(is_containerized, services)):
            pytest.skip()

    def test_docker_running(self, host):
        self.maybe_skip(host)
        assert host.service('docker').is_enabled
        assert host.service('docker').is_running
