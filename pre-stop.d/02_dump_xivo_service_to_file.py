#!/usr/bin/env python3
# Copyright 2018 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import os
import sys
import urllib3

from contextlib import closing

import psycopg2

from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy

logger = logging.getLogger('01_dump_xivo_service_to_file')
logging.basicConfig(level=logging.INFO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'db_uri': 'postgresql://asterisk:proformatique@localhost/asterisk'
}
EXCLUDE_SERVICES = [
    'asterisk',
    'wazo-auth',
    'wazo-call-logd',
    'wazo-dird-xivo-backend',
    'wazo-plugind',
    'wazo-plugind-cli',
    'wazo-upgrade',
    'xivo-agentd-cli',
    'xivo-agid',
    'xivo-confd',
    'xivo-ctid',
    'xivo-ctid-ng',
    'xivo-dird-phoned',
    'xivo-wizard',
]


def _load_config():
    file_config = read_config_file_hierarchy(_DEFAULT_CONFIG)
    return ChainMap(file_config, _DEFAULT_CONFIG)


def _read_accesswebservice(cur):
    accesswebservice_fields = [
        'uuid',
        'name',
        'login',
        'passwd',
        'acl',
        'disable',
    ]

    services = []

    cur.execute('SELECT {} FROM "accesswebservice"'.format(','.join(accesswebservice_fields)))
    for row in cur.fetchall():
        uuid, name, login, passwd, acl, disable = row
        if name in EXCLUDE_SERVICES:
            continue

        services.append({
            'uuid': uuid,
            'firstname': name or None,
            'username': login or uuid,
            'password': passwd or None,
            'enabled': not bool(disable),
            'acl_templates': acl or [],
        })

    return services


def _save_to_file(services, filename):
    print('saving services access to {}'.format(filename), end=' ... ')

    os.mknod(filename)
    os.chmod(filename, 0o600)
    with open(filename, 'w') as f:
        json.dump(services, f)

    print('done')


def main():
    config = _load_config()
    db_uri = config['db_uri']

    version_installed = os.getenv('XIVO_VERSION_INSTALLED')
    if not version_installed:
        print('Variable XIVO_VERSION_INSTALLED must be set')
        sys.exit(-1)

    if version_installed > '18.13':
        sys.exit(0)

    migration_file = '/var/lib/xivo-upgrade/migrate_xivo_service_to_wazo_user'
    if os.path.exists(migration_file):
        # migration already done
        sys.exit(0)

    service_filename = '/var/lib/xivo-upgrade/xivo_service_dump.json'
    if os.path.exists(service_filename):
        print('execute the following script before upgrading your wazo:')
        print('/usr/share/xivo-upgrade/post-start.d/24_load_wazo_user_external_api_from_file.py -f')
        sys.exit(-1)

    with closing(psycopg2.connect(db_uri)) as conn:
        services = _read_accesswebservice(conn.cursor())

    _save_to_file(services, service_filename)


if __name__ == '__main__':
    main()
