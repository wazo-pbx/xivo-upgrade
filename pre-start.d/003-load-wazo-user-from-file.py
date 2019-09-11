#!/usr/bin/env python3
# Copyright 2017-2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import sys
import os
import psycopg2
import urllib3

import requests

from contextlib import closing
from wazo_auth_client import Client as AuthClient
from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy, parse_config_file

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'auth': {
        'key_file': '/var/lib/wazo-auth-keys/wazo-upgrade-key.yml'
    }
}


def _load_config():
    file_config = read_config_file_hierarchy(_DEFAULT_CONFIG)
    key_config = _load_key_file(ChainMap(file_config, _DEFAULT_CONFIG))
    return ChainMap(key_config, file_config, _DEFAULT_CONFIG)


def _load_key_file(config):
    key_file = parse_config_file(config['auth']['key_file'])
    return {'auth': {'username': key_file['service_id'],
                     'password': key_file['service_key']}}


def _create_user(auth_client, entity_to_tenant_map, user):
    tenant_uuid = entity_to_tenant_map.get(user.get('entity_id'))
    if not tenant_uuid:
        print('The following user has no entity, skipping... ', user)
        return

    try:
        auth_client.users.new(tenant_uuid=tenant_uuid, **user)
    except requests.HTTPError as e:
        error = e.response.json() or {}
        if error.get('error_id') == 'invalid-data':
            # The email address was allowed in the php web interface, but is
            # not allowed in wazo-auth
            if error.get('details', {}).get('email_address', {}).get('constraint') == 'email':
                user['email_address'] = None
                _create_user(auth_client, entity_to_tenant_map, user)
                return
        if error.get('error_id') == 'conflict':
            if error.get('details', {}).get('uuid', {}).get('constraint_id') == 'unique':
                return
            elif error.get('details', {}).get('username', {}).get('constraint_id') == 'unique':
                return
            elif error.get('details', {}).get('email_address', {}).get('constraint_id') == 'unique':
                return

        print('The user could not be migrated')
        print('The user was:', user)
        print('The error was:', error)
        raise


def _build_entity_tenant_map(cursor):
    qry = 'SELECT id, tenant_uuid FROM entity'
    cursor.execute(qry)
    return {entity_id: tenant_uuid for (entity_id, tenant_uuid) in cursor.fetchall()}


def _import_wazo_user(users):
    config = _load_config()
    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new(expiration=36000)['token']
    auth_client.set_token(token)

    with closing(psycopg2.connect(config['db_uri'])) as conn:
        cursor = conn.cursor()
        entity_to_tenant_map = _build_entity_tenant_map(cursor)

    print('migrating users to wazo-auth', end='', flush=True)
    for user in users:
        _create_user(auth_client, entity_to_tenant_map, user)
        print('.', end='', flush=True)
    print('\ndone')

    auth_client.token.revoke(token)


def main():
    args = parse_args()

    if not args.force and os.getenv('XIVO_VERSION_INSTALLED') > '18.04':
        sys.exit(0)

    if not os.path.exists('/var/lib/xivo-upgrade/entity_tenant_migration'):
        print('load-wazo-user-from-file: 002-create-tenants-from_entities.py should be executed first')
        sys.exit(1)

    sentinel_file = '/var/lib/xivo-upgrade/migrate_xivo_user_to_wazo_user'
    if os.path.exists(sentinel_file):
        # migration already done
        sys.exit(1)

    user_file = '/var/lib/xivo-upgrade/xivo_user_dump.json'
    if not os.path.exists(user_file):
        print('xivo_user to wazo_user migration failed: File {} does not exist.'.format(user_file))
        sys.exit(-1)

    with open(user_file, 'r') as f:
        users = json.load(f)

    _import_wazo_user(users)

    with open(sentinel_file, 'w'):
        pass

    os.unlink(user_file)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f',
                        '--force',
                        action='store_true',
                        help="Do not check the variable XIVO_VERSION_INSTALLED. Default: %(default)s")
    return parser.parse_args()


if __name__ == '__main__':
    main()
