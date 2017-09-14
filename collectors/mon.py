#!/usr/bin/env python

import rados
import rbd
import json
import threading
import time
import logging
import requests

from collectors.base import BaseCollector
from collectors.common import merge_dicts, get_hostname, get_names


class CephState(object):

    def __init__(self, status=None, summary_list=[]):
        self.status = status

        # create a list of health issues, ignoring the warning that Luminous
        # issues
        summary_data = [health_issue.get('summary', '')
                        for health_issue in summary_list]
        self.summary = [health_desc for health_desc in summary_data
                        if 'update your health monitoring' not in health_desc]

    def update(self, state_object):
        self.status = state_object.status
        self.summary = state_object.summary

    @property
    def status_items(self):
        """
        The summary text will track pgs objects during recovery or backfill
        operations, so every status could be different from the last as these
        counts change. this function removes the int(s) from the status text
        to reduce the frequency that a status check would generate an event
        :return: items (set) unique set of status items
        """
        priority_errors = ['mons', 'osds', 'flag(s)']

        items = set()
        for summary_text in self.summary:
            if any(prio_field in summary_text
                   for prio_field in priority_errors):
                # priority health messages kept as is
                items.add(summary_text)
            else:
                # other messages get their 'counts' removed
                new_text = filter(lambda x: not x.isdigit(), summary_text)
                items.add(new_text)

        return items

    @property
    def status_str(self):
        return "{} : {}".format(self.status,
                                ','.join(self.summary))


class RBDScanner(threading.Thread):

    def __init__(self, cluster_name, pool_name):
        self.cluster_name = cluster_name
        self.pool_name = pool_name
        self.num_rbds = 0
        self.logger = logging.getLogger('cephmetrics')

        threading.Thread.__init__(self)

    def run(self):
        rbd_images = []
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)
        self.logger.debug("scan of '{}' starting".format(self.pool_name))
        with rados.Rados(conffile=conf_file) as cluster:
            with cluster.open_ioctx(self.pool_name) as ioctx:
                rbd_inst = rbd.RBD()
                self.logger.debug("listing rbd's in {}".format(self.pool_name))
                rbd_images = rbd_inst.list(ioctx)

        self.logger.info("pool scan complete for '{}'".format(self.pool_name))
        self.num_rbds = len(rbd_images)


class Mon(BaseCollector):

    health = {
        "HEALTH_OK": 0,
        "HEALTH_WARN": 4,
        "HEALTH_ERR": 8
    }

    osd_state = {
        "up": 0,
        "down": 1
    }

    # metrics are declared, where each element has a description and collectd
    # data type. The description is used to ensure the names sent by collectd
    # remain the same even if the source name changes in ceph.
    cluster_metrics = {
        "num_mon": ("num_mon", "gauge"),
        "num_mon_quorum": ("num_mon_quorum", "gauge"),
        "num_rbds": ("num_rbds", "gauge"),
        "num_osd_hosts": ("num_osd_hosts", "gauge"),
        "num_osd": ("num_osd", "gauge"),
        "num_osd_up": ("num_osd_up", "gauge"),
        "num_osd_in": ("num_osd_in", "gauge"),
        "osd_epoch": ("osd_epoch", "gauge"),
        "osd_bytes": ("osd_bytes", "gauge"),
        "osd_bytes_used": ("osd_bytes_used", "gauge"),
        "osd_bytes_avail": ("osd_bytes_avail", "gauge"),
        "num_pool": ("num_pool", "gauge"),
        "num_pg": ("num_pg", "gauge"),
        "num_pg_active_clean": ("num_pg_active_clean", "gauge"),
        "num_pg_active": ("num_pg_active", "gauge"),
        "num_pg_peering": ("num_pg_peering", "gauge"),
        "num_object": ("num_object", "gauge"),
        "num_object_degraded": ("num_object_degraded", "gauge"),
        "num_object_misplaced": ("num_object_misplaced", "gauge"),
        "num_object_unfound": ("num_object_unfound", "gauge"),
        "num_bytes": ("num_bytes", "gauge"),
        "num_mds_up": ("num_mds_up", "gauge"),
        "num_mds_in": ("num_mds_in", "gauge"),
        "num_mds_failed": ("num_mds_failed", "gauge"),
        "mds_epoch": ("mds_epoch", "gauge"),
        "health": ("health", "gauge")
    }

    pool_client_metrics = {
        'bytes_sec': ("bytes_sec", "gauge"),
        'op_per_sec': ("op_per_sec", "gauge"),
        'read_bytes_sec': ("read_bytes_sec", "gauge"),
        'write_op_per_sec': ("write_op_per_sec", "gauge"),
        'write_bytes_sec': ("write_bytes_sec", "gauge"),
        'read_op_per_sec': ("read_op_per_sec", "gauge")
    }

    pool_recovery_metrics = {
        "recovering_objects_per_sec": ("recovering_objects_per_sec", "gauge"),
        "recovering_bytes_per_sec": ("recovering_bytes_per_sec", "gauge"),
        "recovering_keys_per_sec": ("recovering_keys_per_sec", "gauge"),
        "num_objects_recovered": ("num_objects_recovered", "gauge"),
        "num_bytes_recovered": ("num_bytes_recovered", "gauge"),
        "num_keys_recovered": ("num_keys_recovered", "gauge")
    }

    mon_states = {
        "mon_status": ("mon_status", "gauge")
    }

    all_metrics = merge_dicts(pool_recovery_metrics, pool_client_metrics)
    all_metrics = merge_dicts(all_metrics, cluster_metrics)
    all_metrics = merge_dicts(all_metrics, mon_states)

    def __init__(self, *args, **kwargs):
        BaseCollector.__init__(self, *args, **kwargs)

        self.admin_socket = ('/var/run/ceph/{}-mon.'
                             '{}.asok'.format(self.cluster_name,
                                              get_hostname()))

        self.last_state = CephState()

        self.ip_names = get_names()

        if self.version < 12:
            self.get_mon_health = self._mon_health
        else:
            self.get_mon_health = self._mon_health_new



        if self._parent:
            self.logger.debug("Event URL is : "
                              "{}".format(self._parent.event_url))

    def _mon_command(self, cmd_request):
        """ Issue a command to the monitor """

        buf_s = '{}'
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)

        start = time.time()
        with rados.Rados(conffile=conf_file) as cluster:
            cmd = {'prefix': cmd_request, 'format': 'json'}
            rc, buf_s, out = cluster.mon_command(json.dumps(cmd), b'')
        end = time.time()

        self.logger.debug("_mon_command call '{}' :"
                          " {:.3f}s".format(cmd_request,
                                        (end - start)))

        return json.loads(buf_s)

    @staticmethod
    def get_feature_state(summary_data, pg_states):
        """
        Look at the summary list to determine the state of RADOS features
        :param summary_data: (list) summary data from a ceph health command
        :return: (dict) dict indexed by feature
                        0 Inactive, 1 Active, 2 Disabled
        """
        feature_lookup = {"noscrub": "scrub",
                          "nodeep-scrub": "deep_scrub",
                          "norecover": "recovery",
                          "nobackfill": "backfill",
                          "norebalance": "rebalance",
                          "noout": "out",
                          "nodown": "down"}

        # Start with all features inactive i.e. enabled
        feature_state = {feature_lookup.get(key): 0 for key in feature_lookup}

        for summary in summary_data:
            summary_desc = summary.get('summary')
            if "flag(s) set" in summary_desc:
                flags = summary_desc.replace(' flag(s) set', '').split(',')
                for disabled_feature in flags:
                    if disabled_feature in feature_lookup:
                        feature = feature_lookup.get(disabled_feature)
                        feature_state[feature] = 2      # feature disabled

        # Now use the current pg state names to determine whether a feature is
        # active - if not it stays set to '0', which means inactive
        pg_state_names = [pg_state.get('name') for pg_state in pg_states]
        for pg_state in pg_state_names:
            states = pg_state.split('+')
            if 'recovering' in states:
                feature_state['recovery'] = 1  # Active
                continue
            if 'backfilling' in states:
                feature_state['backfill'] = 1
                continue
            if 'deep' in states:
                feature_state['deep_scrub'] = 1
                continue
            if 'scrubbing' in states:
                feature_state['scrub'] = 1

        return feature_state

    @classmethod
    def check_stuck_pgs(cls, summary_list):
        bad_pg_words = ['pgs', 'stuck', 'inactive']
        stuck_pgs = 0
        for summary_data in summary_list:
            if summary_data.get('severity') != 'HEALTH_ERR':
                continue
            if all(trigger in summary_data.get('summary')
                   for trigger in bad_pg_words):
                stuck_pgs = int(summary_data.get('summary').split()[0])

        return stuck_pgs

    def _mon_health_new(self, cluster_data):

        cluster, health_data = self._mon_health_common(cluster_data)

        mon_status_output = self._mon_command('mon_status')
        quorum_list = mon_status_output.get('quorum')
        mon_list = mon_status_output.get('monmap').get('mons')
        mon_status = {}
        for mon in mon_list:
            state = 0 if mon.get('rank') in quorum_list else 4
            mon_status[mon.get('name')] = state

        cluster['mon_status'] = mon_status

        self.manage_event(health_data.get('status'),
                          health_data.get('summary', []),
                          mon_status)

        return cluster

    def _mon_health_common(self, cluster_data):

        # for v12 (Luminous and beyond) add the following setting to
        # ceph.conf "mon_health_preluminous_compat=true"
        # this will provide the same output as pre-luminous

        health_data = {}
        cluster = {}

        pg_data = self._mon_command("pg stat")
        health_data = self._mon_command("health")
        health_text = health_data.get('status',
                                      health_data.get('overall_status', ''))

        cluster = {Mon.cluster_metrics[k][0]: cluster_data[k]
                   for k in cluster_data}

        health_num = Mon.health.get(health_text, 16)

        cluster['health'] = health_num

        pg_states = pg_data.get('num_pg_by_state')  # list of dict name,num
        health_summary = health_data.get('summary', [])  # list of issues
        cluster['num_pgs_stuck'] = Mon.check_stuck_pgs(health_summary)
        cluster['features'] = Mon.get_feature_state(health_summary,
                                                    pg_states)

        self.logger.debug(
            'Features:{}'.format(json.dumps(cluster['features'])))

        return cluster, health_data

    def get_cluster_state(self):
        return self._admin_socket().get('cluster', {})

    def _mon_health(self, cluster_data):

        cluster, health_data = self._mon_health_common(cluster_data)

        services = health_data.get('health').get('health_services')
        mon_status = {}
        for svc in services:
            if 'mons' in svc:
                # Each monitor will have a numeric value denoting health
                mon_status = {mon.get('name'): Mon.health.get(mon.get('health'))
                              for mon in svc.get('mons')}

        cluster['mon_status'] = mon_status

        self.manage_event(health_data.get('overall_status'),
                          health_data.get('summary', []),
                          mon_status)

        return cluster

    def manage_event(self, health_text, health_summary, mon_status):

        if not self._parent:
            # invoked without a parent, as part of system tests
            return
        elif not self._parent.event_url:
            # event generation skipped
            return

        candidates = [mon_name for mon_name in sorted(mon_status)
                      if mon_status.get(mon_name) == 0]

        if candidates:
            sender = candidates[0]
            if sender not in self.ip_names:
                # only one mon should send, so if that's not us do nothing
                return
        else:
            # no suitable mon to send the alert
            self.logger.error("Unable to send ANY event - no valid mon "
                              "found")
            return

        # If we're here, the current host is suitable to send an event so lets
        # look deeper to see if we need to

        current_state = CephState(health_text, health_summary)
        self.logger.debug("health:{}".format(current_state.status))
        self.logger.debug("health:{}".format(current_state.summary))
        send_it = False

        if health_text != self.last_state.status:
            # Overall health has changed, so just send the current state!
            send_it = True
        else:
            # look deeper - only send if the list of issues is different
            if health_text == 'HEALTH_OK':
                # nothing to do, nothing to send
                pass
            else:
                if self.last_state.status_items != current_state.status_items:
                    send_it = True

        self.last_state.update(current_state)

        if send_it:
            tag = 'health_ok' if current_state.status == 'HEALTH_OK' \
                else 'health_alert'

            self.logger.info("sending cluster status to "
                             "{}".format(self._parent.event_url))
            self.logger.debug(current_state.status_str)

            rc = Mon.post_event(self._parent.event_url,
                                tag,
                                current_state.status_str)

            if rc != 200:
                self.error = True
                self.error_msgs = ['POST request to {} failed ({}) - '
                                   'firewall?'.format(self._parent.event_url,
                                                      rc)]
                self.logger.warning("Unable to send event - graphite response "
                                    "{}".format(rc))

        else:
            # no real change to report
            pass

    @staticmethod
    def post_event(url, tag_name, event_message):

        headers = {"Content-Type": "application/json"}

        try:
            r = requests.post(url,
                              headers=headers,
                              data='{{"what":"Ceph Health",'
                                   '"tags":"{}",'
                                   '"data":"{}"}}'.format(tag_name,
                                                          event_message))
        except requests.ConnectionError:
            # if we hit this, the endpoint wasn't there (graphite web was not
            # accessible) so identify that issue as a server error (500)
            return 500

        else:
            return r.status_code

    @classmethod
    def _seed(cls, metrics):
        return {metrics[key][0]: 0 for key in metrics}

    def display_names(self, metric_format, metrics):
        """
        convert the keys to the static descriptions
        :return:
        """
        return {metric_format[k][0]: metrics[k]
                for k in metrics} if metrics else {}

    def _get_df_stats(self):
        """ get 'ceph df' stats from rados """
        raw_stats = self._mon_command('df')
        for pool in raw_stats['pools']:
            pool['name'] = pool['name'].replace('.', '_')
        return raw_stats

    def _get_pool_stats(self):
        """ get pool stats from rados """

        raw_stats = self._mon_command('osd pool stats')
        pool_stats = {}

        # process each pool
        for pool in raw_stats:

            pool_name = pool['pool_name'].replace('.', '_')
            client_io = self.display_names(Mon.pool_client_metrics,
                                           pool.get('client_io_rate'))
            recovery = self.display_names(Mon.pool_recovery_metrics,
                                          pool.get('recovery_rate'))

            pool_md = {}
            if client_io:

                # Add pool level aggregation
                client_io['bytes_sec'] = client_io.get('read_bytes_sec', 0) + \
                    client_io.get('write_bytes_sec', 0)
                client_io["op_per_sec"] = client_io.get('read_op_per_sec', 0)+ \
                    client_io.get('write_op_per_sec', 0)
                pool_md = client_io

            else:
                pool_md = Mon._seed(Mon.pool_client_metrics)

            if recovery:
                pool_md = merge_dicts(pool_md, recovery)
            else:
                pool_md = merge_dicts(pool_md, Mon._seed(
                    Mon.pool_recovery_metrics))

            pool_stats[pool_name] = pool_md

        return pool_stats

    def _get_osd_states(self):

        self.logger.debug("fetching osd states from the local mon")
        raw = self._mon_command('osd dump')
        osd_hosts = set()
        osds = {}
        for osd in raw.get('osds'):
            cluster_addr = osd.get('cluster_addr').split(':')[0]
            osd_hosts.add(cluster_addr)

            # NB. The key for the osds dict must be a string as the dict is
            # flattened when the metric name is derived in the parent collectd
            # module. If it is not converted, you get a TypeError
            osds[str(osd.get('osd'))] = {"up": osd.get('up'),
                                         "in": osd.get('in')}

        return len(osd_hosts), osds

    @staticmethod
    def _select_pools(pools, mons):
        """
        determine the pools this mon should scan based on it's name. We select
        pools from the an offset into the pool list, and then repeat at an
        interval set by # mons in the configuration. This splits up the pools
        we have, so each mon looks at a discrete set of pools instead of all
        mons performing all scans.
        :param pools: (list) rados pool names
        :param mons: (list) monitor names from ceph health
        :return: (list) of pools this monitor should scan. empty list if the
                 monitor name mismatches - so no scans done
        """

        pools_to_scan = []

        try:
            freq = mons.index(get_hostname())
        except ValueError:
            # this host's name is not in the monitor list?
            # twilight zone moment
            pass
        else:

            pools_to_scan = [pools[ptr]
                             for ptr in xrange(freq, len(pools), len(mons))]

        return pools_to_scan

    def get_rbd_pools(self):
        """
        Look at the rados pools to filter out pools that would normally not
        be associated with rbd images
        :return: (list) of pools that may contain rbd images
        """
        skip_pools = ('default.rgw', '.rgw.')

        start = time.time()
        conf_file = "/etc/ceph/{}.conf".format(self.cluster_name)
        with rados.Rados(conffile=conf_file) as cluster:
            rados_pools = sorted(cluster.list_pools())
        end = time.time()

        self.logger.debug('lspools took {:.3f}s'.format(end - start))

        filtered_pools = [pool for pool in rados_pools
                          if not pool.startswith(skip_pools)]

        return filtered_pools

    def _get_rbds(self, monitors):
        """
        Scan a subset of the rados pools for rbd images. Each mon collector
        will scan a subset of the pools to distribute the load using the
        RBSScanner class
        :param monitors: (dict) monitor names and states
        :return total_rbs: (int) total rbd images found across pools
        """

        pool_list = self.get_rbd_pools()
        mon_list = sorted(monitors.keys())
        my_pools = Mon._select_pools(pool_list, mon_list)
        self.logger.debug("Pools to be scanned on this mon"
                          " : {}".format(','.join(my_pools)))
        threads = []

        start = time.time()

        for pool in my_pools:
            thread = RBDScanner(self.cluster_name, pool)
            thread.start()
            threads.append(thread)

        # wait for all threads to complete
        for thread in threads:
            thread.join(1)

        end = time.time()
        self.logger.debug("rbd scans {:.3f}s".format((end - start)))

        total_rbds = sum([thread.num_rbds for thread in threads])
        self.logger.debug("total rbds found : {}".format(total_rbds))

        for thread in threads:
            del thread

        return total_rbds

    def get_stats(self):
        """
        method associated with the plugin callback to gather the metrics
        :return: (dict) metadata describing the state of the mon/osd's etc
        """

        start = time.time()

        # Attempt to read the admin socket for cluster data
        cluster_data = self.get_cluster_state()

        if cluster_data:

            # read from the admin socket was OK, so process the data
            cluster_state = self.get_mon_health(cluster_data)
            pool_stats = self._get_pool_stats()
            df_stats = self._get_df_stats()
            for df_obj in df_stats['pools']:
                pool_name = df_obj['name']
                pool_stats[pool_name] = merge_dicts(
                    pool_stats[pool_name], df_obj['stats'])
            num_osd_hosts, osd_states = self._get_osd_states()

            cluster_state['num_osd_hosts'] = num_osd_hosts
            cluster_state['num_rbds'] = self._get_rbds(cluster_state['mon_status'])

            all_stats = merge_dicts(cluster_state, {"pools": pool_stats,
                                                    "osd_state": osd_states})
        else:
            # problem reading from the admin socket, record it in cephmetrics
            # log and set the object's error flag so it can be picked up at the
            # layer above the Mon instance (Ceph instance -> collectd log)
            all_stats = {}
            self.error = True
            msg = 'MON socket is not available...is ceph-mon active?'
            self.error_msgs = [msg]
            self.logger.warning(msg)

        all_stats['ceph_version'] = self.version

        end = time.time()
        self.logger.info("mon get_stats call : {:.3f}s".format((end - start)))

        return {
            "mon": all_stats
        }

