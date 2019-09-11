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

logger = logging.getLogger('03_dump_xivo_admin_to_file')
logging.basicConfig(level=logging.INFO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'db_uri': 'postgresql://asterisk:proformatique@localhost/asterisk'
}


def _load_config():
    file_config = read_config_file_hierarchy(_DEFAULT_CONFIG)
    return ChainMap(file_config, _DEFAULT_CONFIG)


def _read_user(cur):
    user_fields = [
        'uuid',
        'login',
        'passwd',
        'entity_id',
        'valid',
    ]

    admins = []

    cur.execute('SELECT {} FROM "user"'.format(','.join(user_fields)))
    for row in cur.fetchall():
        uuid, login, passwd, entity_id, valid = row
        admins.append({
            'uuid': uuid,
            'username': login or uuid,
            'password': passwd or None,
            'entity_id': entity_id or None,
            'enabled': bool(valid),
        })

    return admins


def _save_to_file(admins, filename):
    print('saving admins access to {}'.format(filename), end=' ... ')

    os.mknod(filename)
    os.chmod(filename, 0o600)
    with open(filename, 'w') as f:
        json.dump(admins, f)

    print('done')


def main():
    config = _load_config()
    db_uri = config['db_uri']

    version_installed = os.getenv('XIVO_VERSION_INSTALLED')
    if not version_installed:
        print('Variable XIVO_VERSION_INSTALLED must be set')
        sys.exit(-1)

    if version_installed > '18.14':
        sys.exit(0)

    migration_file = '/var/lib/xivo-upgrade/migrate_xivo_admin_to_wazo_user'
    if os.path.exists(migration_file):
        # migration already done
        sys.exit(0)

    filename = '/var/lib/xivo-upgrade/xivo_admin_dump.json'
    if os.path.exists(filename):
        print('execute the following script before upgrading your wazo:')
        print('/usr/share/xivo-upgrade/post-start.d/25_load_wazo_user_admin_from_file.py -f')
        sys.exit(-1)

    with closing(psycopg2.connect(db_uri)) as conn:
        admins = _read_user(conn.cursor())

    _save_to_file(admins, filename)


if __name__ == '__main__':
    main()
