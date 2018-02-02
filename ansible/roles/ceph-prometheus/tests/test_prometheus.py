import pytest

testinfra_hosts = ['ceph-grafana']


class TestPrometheus(object):
    def maybe_skip(self, host):
        vars = host.ansible.get_variables()
        if vars.get('backend', dict()).get('storage', 'prometheus') != 'prometheus':
            pytest.skip()

    def test_port_open(self, host):
        """ Is the prometheus port open? """
        self.maybe_skip(host)
        socket_spec = "tcp://0.0.0.0:9090"
        assert host.socket(socket_spec).is_listening
