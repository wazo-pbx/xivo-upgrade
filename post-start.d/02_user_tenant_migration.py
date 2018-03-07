#!/usr/bin/env python3
# Copyright 2018 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

import os
import psycopg2
import sys

from contextlib import closing

from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy, parse_config_file
from xivo_auth_client import Client as AuthClient

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'auth': {
        'key_file': '/var/lib/xivo-auth-keys/wazo-upgrade-key.yml'
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


def get_tenants(cur):
    cur.execute('SELECT uuid, name FROM "tenant"')
    return {uuid: name for uuid, name in cur.fetchall()}


def get_users(cur):
    cur.execute('SELECT uuid, tenant_uuid FROM "userfeatures"')
    return {uuid: tenant_uuid for uuid, tenant_uuid in cur.fetchall()}


def main():
    if os.getenv('XIVO_VERSION_INSTALLED') > '18.03':
        sys.exit(0)

    migration_file = '/var/lib/xivo-upgrade/migrate_xivo_user_to_wazo_user'
    if not os.path.exists(migration_file):
        print('xivo_user to wazo_user migration not executed. aborting')
        sys.exit(1)

    migration_file = '/var/lib/xivo-upgrade/user_tenant_migration'
    if os.path.exists(migration_file):
        # Already executed
        sys.exit(2)

    config = _load_config()
    db_uri = config['db_uri']
    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new('xivo_service', expiration=36000)['token']
    auth_client.set_token(token)

    # Fetch manage db data
    with closing(psycopg2.connect(db_uri)) as conn:
        cursor = conn.cursor()
        manage_db_tenant_map = get_tenants(cursor)
        user_tenant_map = get_users(cursor)

    # Create all tenants in wazo-auth
    used_tenants = [manage_db_tenant_map.get(uuid) for uuid in user_tenant_map.values()]
    auth_tenant_map = {tenant['name']: tenant['uuid'] for tenant in auth_client.tenants.list()['items']}
    missing_tenants = set(used_tenants) - set(auth_tenant_map.keys())
    for tenant in missing_tenants:
        tenant_uuid = auth_client.tenants.new(name=tenant)
        auth_tenant_map[tenant_uuid] = tenant

    # Associate all users to their tenants
    for user_uuid, tenant_uuid in user_tenant_map.items():
        existing_user_tenants = set(tenant['uuid'] for tenant in auth_client.users.get_tenants(user_uuid))
        tenant_name = manage_db_tenant_map[tenant_uuid]
        if tenant_name in existing_user_tenants:
            # The user is already associated to this tenant
            continue

        auth_tenant_uuid = auth_tenant_map[tenant_name]
        auth_client.tenants.add_user(auth_tenant_uuid, user_uuid)

        # remove all other tenants for the import users
        existing_user_tenants.remove(tenant_name)
        for tenant_uuid in existing_user_tenants:
            auth_client.tenants.remove_user(tenant_uuid, user_uuid)

    # Mark the migration as completed
    with open(migration_file, 'w'):
        pass

if __name__ == '__main__':
    main()
