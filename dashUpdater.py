#!/usr/bin/env python2

import os
import sys
import logging
import json
import yaml
from requests import get, post, put
import argparse
import socket

__author__ = 'Paul Cuzner'
__version__ = '2.0'

HEADERS = {"Accept": "application/json",
           "Content-Type": "application/json"
           }

# variables that need to be updated for the local environment must be defined
# to grafana as 'custom', for the updater to work


class Config(object):
    pass


class DashBoardException(Exception):
    pass


def get_options():
    """
    Process runtime options

    """
    # Set up the runtime overrides
    parser = argparse.ArgumentParser(prog='dashmgr',
                                     description='Manage Ceph Monitoring '
                                                 'dashboards in Grafana')
    parser.add_argument('-A', '--update-alerts', action='store_true',
                        default=False)
    parser.add_argument('-c', '--config-file', type=str,
                        help='path of the config file to use',
                        default=os.path.join(os.getcwd(), 'dashboard.yml'))
    parser.add_argument('-D', '--dashboard-dir', type=str,
                        help='path to the directory containing dashboards',
                        default=os.path.join(
                            os.getcwd(), 'dashboards/cephmetrics-graphite'))
    parser.add_argument('-m', '--mode', type=str,
                        help='run mode',
                        choices=['update', 'refresh'],
                        default='update')
    parser.add_argument('-d', '--debug', action='store_true',
                        default=False,
                        help='run with additional debug')
    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s - {}'.format(__version__))

    return parser.parse_args()


def fread(file_name=None):
    with open(file_name) as f:
        f_data = f.read()
    return f_data


def port_open(port, host='localhost'):
    """
    Check a given port is accessible
    :param port: (int) port number to check
    :param host: (str)hostname to check, default is localhost
    :return: (bool) true if the port is accessible
    """
    socket.setdefaulttimeout(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect_ex((host, port))
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
        return True
    except socket.error:
        return False


def get_config(file_name):
    """
    read a given file, and attempt to load as yaml
    :return (Config) config object instance
    """
    if os.path.exists(file_name):
        config_data = fread(file_name)
        try:
            yaml_config = yaml.load(config_data)
        except:
            return None
        else:
            cfg = Config()
            cfg.grafana_host = yaml_config.get('_grafana_host', 'localhost')
            cfg.dashboards = yaml_config.get('_dashboards', [])
            cfg.auth = yaml_config.get('_credentials', {"user": 'admin',
                                                      "password": "admin"})
            cfg.grafana_credentials = (cfg.auth.get('user'),
                                       cfg.auth.get('password'))
            cfg.grafana_port = yaml_config.get('_grafana_port', 3000)
            cfg.home_dashboard = yaml_config.get('_home_dashboard',
                                                 'ceph-at-a-glance')
            cfg.alert_dashboard = yaml_config.get('_alert_dashboard',
                                                  'alert-status')
            cfg.domain = yaml_config.get('domain', '')
            cfg.yaml = yaml_config
            return cfg

    else:
        return None


def update_dashboard(dashboard_json, vars_to_update):
    updates_made = 0
    templating = dashboard_json['dashboard'].get('templating')
    template_names = []
    for l in templating.get('list'):
        template_name = l.get('name')
        if template_name in vars_to_update:

            logger.debug("\tprocessing variable '{}'".format(template_name))
            logger.debug("\tbefore")
            logger.debug("\t{}".format(l))
            template_names.append(template_name)
            replacement_vars = vars_to_update.get(template_name)

            if isinstance(replacement_vars, str):
                replacement_vars = [replacement_vars]

            l['query'] = ','.join(replacement_vars)
            num_new_items = len(replacement_vars)
            if num_new_items == 1:
                l['current'] = {"text": replacement_vars[0],
                                "value": replacement_vars[0]}
                l['options'] = [{"text": replacement_vars[0],
                                 "selected": True,
                                 "value": replacement_vars[0]}]
            else:
                l['current'] = {"text": "All",
                                "selected": True,
                                "value": "$__all"}
                l['options'] = [{"text": "All",
                                 "selected": True,
                                 "value": "$__all"}]
                for item in replacement_vars:
                    l['options'].append({"text": item,
                                         "selected": False,
                                         "value": item})

            logger.debug("\tafter")
            logger.debug("\t{}".format(l))
            updates_made += 1

    logger.info("- {} templating variables updated "
                ": {}".format(updates_made,
                              ','.join(template_names)))
    return dashboard_json


def load_dashboard(dashboard_dir, dashboard_name):

    sample_dashboard = os.path.join(dashboard_dir,
                                    "{}.json".format(dashboard_name))
    if os.path.exists(sample_dashboard):
        # load it in
        dashboard_data = fread(sample_dashboard)

        # if domain has not been given, we need to remove it from the queries
        if not config.domain:
            dashboard_data = dashboard_data.replace('$domain.', '')

        try:
            dashjson = json.loads(dashboard_data)
        except:
            raise DashBoardException("Invalid json in {} "
                                     "dashboard".format(dashboard_name))
        else:
            logger.debug("- {} sample loaded from {}".format(dashboard_name,
                                                    dashboard_dir))
            del dashjson['meta']
            dashjson['overwrite'] = True

            # 'id' must be null for this to be a create, if it is anything
            # else grafana will attempt an update, which will fail
            # with a 404
            dashjson['dashboard']['id'] = None
            return dashjson
    else:
        logger.warning("- sample not available for {}, "
                       "skipping".format(dashboard_name))
        return {}


def get_dashboard(dashboard_name):

    resp = get("http://{}:{}/api/dashboards/"
               "db/{}".format(config.grafana_host,
                              config.grafana_port,
                              dashboard_name),
               auth=config.grafana_credentials)

    if resp.status_code == 404:
        logger.info("- dashboard not found in Grafana")
        return resp.status_code, {}

    elif resp.status_code == 200:
        logger.debug("- fetch of {} from Grafana "
                     "successful".format(dashboard_name))
        return resp.status_code, resp.json()
    else:
        raise DashBoardException("Unknown problem fetching dashboard")


def put_dashboard(dashjson):
    upload_str = json.dumps(dashjson)
    resp = post("http://{}:{}/api/dashboards/"
                "db".format(config.grafana_host,
                            config.grafana_port),
                headers=HEADERS,
                auth=config.grafana_credentials,
                data=upload_str)

    return resp.status_code


def star_dashboard(dashboard_id):

    resp = post('http://{}:{}/api/user/stars/'
                'dashboard/{}'.format(config.grafana_host,
                                      config.grafana_port,
                                      dashboard_id),
                headers=HEADERS,
                auth=config.grafana_credentials)

    if resp.status_code == 200:
        logger.debug("- dashboard starred successfully")
    else:
        logger.warning("- starring dashboard with id {} "
                       "failed : {}".format(dashboard_id,
                                            resp.status_code))
    return resp.status_code

def set_home_dashboard(home_dashboard):
    # Ideally we should just check the json returned from an org query...but
    # 4.3 of grafana doesn't return the home dashboard or theme settings!

    logger.debug("- checking '{}' is starred".format(home_dashboard))

    http_rc, dashjson = get_dashboard(home_dashboard)
    if http_rc == 200 and dashjson:

        dash_id = dashjson.get('dashboard').get('id')
        is_starred = dashjson.get('meta').get('isStarred')
        if not is_starred:
            # star it
            http_rc = star_dashboard(dash_id)
            is_starred = True if http_rc == 200 else False

        if is_starred:
            # update the org's home dashboard
            resp = put('http://{}:{}/api/org/'
                       'preferences'.format(config.grafana_host,
                                            config.grafana_port),
                       headers=HEADERS,
                       auth=config.grafana_credentials,
                       data=json.dumps({"name": "Main Org.",
                                        "theme": "light",
                                        "homeDashboardId": dash_id}))

            if resp.status_code == 200:
                logger.info("- setting home dashboard complete")
            else:
                logger.error("- setting home dashboard failed")

            return resp.status_code

    else:
        logger.error("- unable to access dashboard {}".format(home_dashboard))

    return http_rc


def setup_logging():

    logger = logging.getLogger('dashUpdater')
    logger.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    if opts.debug:
        stream_handler.setLevel(logging.DEBUG)
    else:
        stream_handler.setLevel(logging.INFO)

    logger.addHandler(stream_handler)

    return logger


def get_notification_id(channel_name):
    """
    Check whether the given notification channel has been defined to Grafana
    :param (str) notification channel name
    :return: (int) id of the channel, or 0 for doesn't exist
    """

    resp = get("http://{}:{}/api/"
               "alert-notifications".format(config.grafana_host,
                                            config.grafana_port),
               auth=config.grafana_credentials)

    if resp.status_code == 200:
        notifications = resp.json()     # list if dicts returned by Grafana

        # convert the list into a dict for lookup purposes
        channels = {channel.get('name'): channel.get('id')
                    for channel in notifications}
        if channel_name in channels:
            return channels[channel_name]
        else:
            return 0
    else:
        raise DashBoardException("Unable to get nofification channels from"
                                 " Grafana")


def define_notification(channel_name):
    """
    Add a given "seed" notification channel to Grafana using http post
    :param channel_name: (str) channel name
    :return: (int) http response code from post operation
             (dict) response json object
    """

    seed_channel = json.dumps({"name": channel_name,
                               "type": "email",
                               "isDefault": False
                               })

    resp = post('http://{}:{}/api/'
                'alert-notifications'.format(config.grafana_host,
                                             config.grafana_port),
                headers=HEADERS,
                auth=config.grafana_credentials,
                data=seed_channel)

    return resp.status_code, resp.json()


def main():

    rc = 0

    if port_open(config.grafana_port, config.grafana_host):
        logger.debug("Connection to Grafana is ok")
    else:
        logger.error("Unable to contact Grafana - does the config file "
                     "specify a valid host/ip address for Grafana?")
        return 16

    if config.dashboards:
        vars_to_update = {k: config.yaml[k] for k in config.yaml
                          if not k.startswith('_')}
        if 'domain' not in vars_to_update:
            vars_to_update['domain'] = config.domain

    else:
        logger.error("Config file doesn't contain dashboards! Unable "
                     "to continue")
        return 16

    dashboards_updated = 0
    logger.debug("Templates to update: {}".format(vars_to_update))

    for dashname in config.dashboards:
        logger.info("\nProcessing dashboard {}".format(dashname))

        http_rc, dashjson = get_dashboard(dashname)
        if (dashname == config.alert_dashboard and http_rc == 200 and not
                opts.update_alerts):
            logger.info("- existing alert dashboard found, update bypassed")
            continue

        if opts.mode == 'update':

            if http_rc == 200:
                # the dashboard is already loaded, so we'll use the existing
                # definition
                logger.debug("- existing dashboard will be updated")
            else:
                # get of dashboard failed, so just load it
                dashjson = load_dashboard(opts.dashboard_dir, dashname)

                if dashjson:
                    logger.info("- dashboard loaded from sample")
                else:
                    logger.warning("- sample not available, skipping")
                    rc = max(rc, 4)
                    continue

            logger.info("- dashboard retrieved")

        elif opts.mode == 'refresh':

            dashjson = load_dashboard(opts.dashboard_dir, dashname)

            if not dashjson:
                logger.warning("- sample not available, skipping")
                rc = max(rc, 4)
                continue

        if dashname == config.alert_dashboard:
            # if processing is here, this is 1st run so the alert_dashboard
            # is new to grafana
            channel_id = get_notification_id("cephmetrics")
            if channel_id:
                logger.info("- notification channel already in place")
            else:
                http_rc, resp_json = define_notification("cephmetrics")
                if http_rc == 200:
                    channel_id = resp_json['id']
                    logger.info("- notification channel added :"
                                "{}".format(channel_id))
                else:
                    raise DashBoardException("Problem adding notification "
                                             "channel ({})".format(http_rc))

            dash_str = json.dumps(dashjson)
            dash_str = dash_str.replace('"notifications": []',
                                        '"notifications": [{{ "id":'
                                        ' {0} }}]'.format(channel_id))
            if config.domain:
                logger.debug("- queries updated, replacing $domain with "
                             "'{}'".format(config.domain))
                dash_str = dash_str.replace('.$domain',
                                            ".{}".format(config.domain))
            else:
                logger.debug("- queries updated, replacing $domain with NULL")
                dash_str = dash_str.replace('.$domain',
                                            '')

            dashjson = json.loads(dash_str)

        else:
            # Normal dashboard processing
            templating = dashjson['dashboard'].get('templating')
            if templating:
                dashjson = update_dashboard(dashjson, vars_to_update)
            else:
                logger.info('- templating not defined in {}, '
                            'skipping'.format(dashname))
                rc = max(rc, 4)

        http_rc = put_dashboard(dashjson)

        if http_rc == 200:
            logger.info("- dashboard update successful")
            dashboards_updated += 1

            if dashname == config.home_dashboard:
                # ensure the home dashboard is defined
                http_rc = set_home_dashboard(dashname)

                if http_rc != 200:
                    logger.warning("- Unable to set the home dashboard")
                    rc = max(rc, 12)

        else:
            logger.error("- dashboard {} update failed ({})".format(dashname,
                                                                    http_rc))
            rc = max(rc, 8)

    return rc


if __name__ == '__main__':

    opts = get_options()

    config = get_config(opts.config_file)

    if config:

        logger = setup_logging()

        rc = main()

        sys.exit(rc)

    else:

        print("Invalid config file detected, unable to start")
        sys.exit(16)
