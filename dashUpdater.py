#!/usr/bin/env python2

import os
import json
import yaml
from requests import get, post

__author__ = 'Paul Cuzner'

HEADERS = {"Accept": "application/json",
           "Content-Type": "application/json"
           }

dashboard_dir = 'dashboards/current'

# variables that need to be updated for the local environment must be defined
# to grafana as 'custom', for the updater to work

def fread(file_name=None):
    with open(file_name) as f:
        f_data = f.read()
    return f_data


def main():

    config_data = fread(file_name=os.path.join(os.getcwd(),
                                               "dashboard.yml"))

    config = yaml.load(config_data)

    dashboards = config.get('_dashboards', [])
    credentials = config.get('_credentials', {"user": 'admin',
                                              "password": "admin"})
    grafana_credentials = (credentials.get('user'),
                           credentials.get('password'))
    grafana_port = config.get('_grafana_port', 3000)

    if dashboards:
        vars_to_update = {k: config[k] for k in config
                          if not k.startswith('_')}
    else:
        print(
            "Config file doesn't contain dashboards! Unable to continue")
        return

    dashboards_updated = 0
    print(vars_to_update)

    for dashname in dashboards:
        print("\nProcessing dashboard {}".format(dashname))

        resp = get("http://localhost:{}/api/dashboards/"
                   "db/{}".format(grafana_port,
                                  dashname),
                   auth=grafana_credentials)

        if resp.status_code == 404:
            print("- dashboard not found, looking for a sample to upload")
            sample_dashboard = os.path.join(os.getcwd(), dashboard_dir,
                                            "{}.json".format(dashname))
            if os.path.exists(sample_dashboard):
                # load it in
                dashboard_data = fread(sample_dashboard)
                dashjson = json.loads(dashboard_data)

                del dashjson['meta']
                dashjson['overwrite'] = False

                # 'id' must be null for this to be a create, if it is anything
                # else grafana will attempt an update, which will fail
                # with a 404
                dashjson['dashboard']['id'] = None

            else:
                print("- sample not available, skipping")
                continue

        elif resp.status_code != 200:
            print("Problem fetching dashboard {} - status "
                  "code {}".format(dashname, resp.status_code))
            continue
        else:
            dashjson = resp.json()

        print("- dashboard retrieved")

        updates_made = 0
        templating = dashjson['dashboard'].get('templating')
        for l in templating.get('list'):
            template_name = l.get('name')
            if template_name in vars_to_update:
                print("\tprocessing - {}".format(template_name))
                print("\tbefore")
                print("\t{}".format(l))
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

                print("\tafter")
                print("\t{}".format(l))
                updates_made += 1

        upload_str = json.dumps(dashjson)
        resp = post("http://localhost:{}/api/dashboards/"
                    "db".format(grafana_port),
                    headers=HEADERS,
                    auth=grafana_credentials,
                    data=upload_str)

        if resp.status_code == 200:
            print("- dashboard updated successful, {} template variables"
                  " changed".format(updates_made))
            dashboards_updated += 1
        else:
            print("- Error : update failed - {}".format(resp.status_code))


    print("\nUpdate Summary: {} dashboards updated, "
          "{} failures".format(dashboards_updated,
                               (len(dashboards) - dashboards_updated)))


if __name__ == '__main__':
    main()