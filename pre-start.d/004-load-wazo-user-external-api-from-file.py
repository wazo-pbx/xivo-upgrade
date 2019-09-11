#!/usr/bin/env python3
# Copyright 2018-2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import sys
import os
import uuid
import urllib3

from contextlib import closing

import psycopg2
import requests

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


def _create_user(auth_client, tenant_uuid, user):
    acl_templates = user.pop('acl_templates')
    try:
        user = auth_client.users.new(tenant_uuid=tenant_uuid, purpose='external_api', **user)
    except requests.HTTPError as e:
        error = e.response.json() or {}
        if error.get('error_id') == 'conflict':
            if error.get('details', {}).get('uuid', {}).get('constraint_id') == 'unique':
                return
            elif error.get('details', {}).get('username', {}).get('constraint_id') == 'unique':
                return
        _print_user_migrated_error(user, error)
        raise

    policy_name = '{}-{}'.format(user['username'], str(uuid.uuid4()))
    try:
        policy = auth_client.policies.new(
            tenant_uuid=tenant_uuid,
            name=policy_name,
            acl_templates=acl_templates,
        )
    except requests.HTTPError as e:
        error = e.response.json() or {}
        _print_user_migrated_error(user, error)
        raise

    try:
        auth_client.users.add_policy(user['uuid'], policy['uuid'])
    except requests.HTTPError as e:
        error = e.response.json() or {}
        _print_user_migrated_error(user, error)
        raise


def _print_user_migrated_error(user, error):
    print('The user could not be migrated')
    print('The user was:', user)
    print('The error was:', error)


def _find_older_tenant_uuid(cursor):
    qry = 'SELECT tenant_uuid FROM entity ORDER BY id ASC LIMIT 1'
    cursor.execute(qry)
    for row in cursor.fetchall():
        return row[0]
    print('Unable to fetch at least one tenant')
    sys.exit(-1)


def _import_wazo_user(users):
    config = _load_config()
    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new('wazo_user', expiration=36000)['token']
    auth_client.set_token(token)

    with closing(psycopg2.connect(config['db_uri'])) as conn:
        cursor = conn.cursor()
        tenant_uuid = _find_older_tenant_uuid(cursor)

    print('migrating services access to wazo-auth', end='', flush=True)
    for user in users:
        _create_user(auth_client, tenant_uuid, user)
        print('.', end='', flush=True)
    print('\ndone')

    auth_client.token.revoke(token)


def main():
    args = parse_args()

    if not args.force:
        version_installed = os.getenv('XIVO_VERSION_INSTALLED')
        if not version_installed:
            print('Variable XIVO_VERSION_INSTALLED must be set')
            sys.exit(1)
        if version_installed > '18.13':
            sys.exit(0)

        if version_installed <= '18.04':
            if not os.path.exists('/var/lib/xivo-upgrade/entity_tenant_migration'):
                print('load-wazo-user-external-api-from-file: 002-create-tenants-from-entities.py should be executed first')
                sys.exit(1)

    sentinel_file = '/var/lib/xivo-upgrade/migrate_xivo_service_to_wazo_user'
    if os.path.exists(sentinel_file):
        # migration already done
        sys.exit(0)

    user_file = '/var/lib/xivo-upgrade/xivo_service_dump.json'
    if not os.path.exists(user_file):
        print('xivo_service_user migration failed: File {} does not exist.'.format(user_file))
        sys.exit(-1)

    with open(user_file, 'r') as f:
        users = json.load(f)

    _import_wazo_user(users)

    with open(sentinel_file, 'w'):
        pass

    os.unlink(user_file)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help="Do not check the variable XIVO_VERSION_INSTALLED. Default: %(default)s",
    )
    return parser.parse_args()


if __name__ == '__main__':
    main()
