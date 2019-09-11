#!/usr/bin/env python3
# Copyright 2017-2018 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import os
import psycopg2
import sys
import urllib3

from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy
from contextlib import closing

logger = logging.getLogger('01_dump_xivo_user_to_file')
logging.basicConfig(level=logging.INFO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'db_uri': 'postgresql://asterisk:proformatique@localhost/asterisk'
}


def _load_config():
    file_config = read_config_file_hierarchy(_DEFAULT_CONFIG)
    return ChainMap(file_config, _DEFAULT_CONFIG)


def _read_userfeatures(cur):
    userfeatures_fields = [
        'uuid',
        'firstname',
        'lastname',
        'email',
        'enableclient',
        'loginclient',
        'passwdclient',
        'entityid',
    ]

    users = []
    abort = False

    cur.execute('SELECT {} FROM "userfeatures"'.format(','.join(userfeatures_fields)))
    for row in cur.fetchall():
        uuid, firstname, lastname, email, enableclient, loginclient, passwdclient, entity_id = row
        if not entity_id:
            print('User "{} {}" <{}> is not associated to an entity. Aborting...'.format(firstname, lastname, email))
            abort = True

        users.append({
            'uuid': uuid,
            'firstname': firstname or None,
            'lastname': lastname or None,
            'email_address': email or None,
            'enabled': bool(enableclient),
            'username': loginclient or email or uuid,
            'password': passwdclient or None,
            'entity_id': entity_id,
        })

    if not users:
        return []

    if abort:
        sys.exit(2)

    return users


def _save_to_file(users, filename):
    print('saving users to {}'.format(filename), end=' ... ')

    os.mknod(filename)
    os.chmod(filename, 0o600)
    with open(filename, 'w') as f:
        json.dump(users, f)

    print('done')


def main():
    config = _load_config()
    db_uri = config['db_uri']

    if os.getenv('XIVO_VERSION_INSTALLED') > '18.04':
        sys.exit(0)

    migration_file = '/var/lib/xivo-upgrade/migrate_xivo_user_to_wazo_user'
    if os.path.exists(migration_file):
        # migration already done
        sys.exit(0)

    user_filename = '/var/lib/xivo-upgrade/xivo_user_dump.json'
    if os.path.exists(user_filename):
        print('execute the following script before upgrading your wazo:')
        print('/usr/share/xivo-upgrade/post-start.d/23_load_wazo_user_from_file.py -f')
        sys.exit(-1)

    with closing(psycopg2.connect(db_uri)) as conn:
        users = _read_userfeatures(conn.cursor()) or []

    _save_to_file(users, user_filename)


if __name__ == '__main__':
    main()
