import pytest

testinfra_hosts = ['ceph-grafana']


class TestGrafana(object):
    @pytest.mark.parametrize(
        "service",
        ['grafana-server']
    )
    def test_service_enabled(self, host, service):
        """ Are the proper services enabled? """
        if isinstance(service, dict):
            service = service[
                host.ansible('setup')['ansible_facts']['ansible_pkg_mgr']]
        service = host.service(service)
        assert service.is_running
        assert service.is_enabled

    @pytest.mark.parametrize(
        "proto,iface,port",
        [
            ('tcp', '0.0.0.0', '3000'),  # grafana
        ]
    )
    def test_ports_open(self, host, proto, iface, port):
        """ Are the proper ports open? """
        socket_spec = "%s://%s" % (proto, iface)
        if iface:
            socket_spec += ':'
        socket_spec += port
        assert host.socket(socket_spec).is_listening
