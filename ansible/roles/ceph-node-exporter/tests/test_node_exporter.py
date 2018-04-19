import pytest

testinfra_hosts = ['!ceph-grafana']


class TestNodeExporter(object):
    def maybe_skip(self, host):
        vars = host.ansible.get_variables()
        if vars.get('backend', dict()).get('storage', 'prometheus') != 'prometheus':
            pytest.skip()

    def test_service_enabled(self, host):
        self.maybe_skip(host)
        assert host.service('node_exporter').is_enabled
        assert host.service('node_exporter').is_running

    def test_port_open(self, host):
        """ Is the node_exporter port open? """
        self.maybe_skip(host)
        socket_spec = "tcp://0.0.0.0:9100"
        assert host.socket(socket_spec).is_listening
