import os
import json


def get_dashboards():
    dashboards = dict()
    db_dir = os.path.realpath(
        os.path.join(
            os.path.dirname(__file__),
            '..',
        )
    )
    for item in os.listdir(db_dir):
        if item.endswith('.json'):
            db_path = os.path.join(
                os.path.dirname(__file__),
                '..',
                item,
            )
            dashboards[item] = json.loads(
                open(db_path).read()
            )
    return dashboards


class TestDashboards(object):
    dashboards = None
