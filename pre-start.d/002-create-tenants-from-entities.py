#!/usr/bin/env python3
# Copyright 2018-2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import psycopg2
import os
import sys

from contextlib import closing
from wazo_auth_client import Client as AuthClient
from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy, parse_config_file

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


def _entity_to_tenant(row):
    name, number, line_1, line_2, city, state, zip_code, country = row

    body = {'name': name}
    if number:
        body['number'] = number

    address = {}
    if line_1:
        address['line_1'] = line_1
    if line_2:
        address['line_2'] = line_2
    if city:
        address['city'] = city
    if state:
        address['state'] = state
    if country:
        address['country'] = country

    if address:
        body['address'] = address

    return body


def _build_tenant_bodies_from_entities(cursor):
    qry = 'SELECT name, phonenumber, address1, address2, city, state, zipcode, country from entity'
    cursor.execute(qry)
    return [_entity_to_tenant(row) for row in cursor.fetchall()]


def _get_existing_tenants(auth_client):
    tenants = auth_client.tenants.list()['items']
    return {tenant['name']: tenant['uuid'] for tenant in tenants}


def _upsert_tenant(cursor, tenant_uuid):
    qry = 'INSERT INTO tenant(uuid) VALUES (%s) ON CONFLICT DO NOTHING'
    cursor.execute(qry, (tenant_uuid,))


def _update_entity_tenant_uuid(cursor, entity_name, tenant_uuid):
    qry = 'UPDATE entity SET tenant_uuid = %s WHERE name = %s'
    cursor.execute(qry, (tenant_uuid, entity_name))


def do_migration(config):
    with closing(psycopg2.connect(config['db_uri'])) as conn:
        tenants = _build_tenant_bodies_from_entities(conn.cursor())

    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new(expiration=36000)['token']
    auth_client.set_token(token)

    existing_tenants = _get_existing_tenants(auth_client)

    for tenant in tenants:
        if tenant['name'] in existing_tenants.keys():
            continue
        tenant = auth_client.tenants.new(**tenant)

        existing_tenants[tenant['name']] = tenant['uuid']

    with closing(psycopg2.connect(config['db_uri'])) as conn:
        cursor = conn.cursor()
        for name, tenant_uuid in existing_tenants.items():
            if not name:
                # wazo-auth allow tenants without names but those do not map to entities
                continue

            _upsert_tenant(cursor, tenant_uuid)
            conn.commit()
            _update_entity_tenant_uuid(cursor, name, tenant_uuid)
            conn.commit()

    auth_client.token.revoke(token)


def main():
    if os.getenv('XIVO_VERSION_INSTALLED') > '18.04':
        sys.exit(0)

    sentinel_file = '/var/lib/xivo-upgrade/entity_tenant_migration'
    if os.path.exists(sentinel_file):
        sys.exit(1)

    config = _load_config()
    do_migration(config)

    with open(sentinel_file, 'w'):
        pass


if __name__ == '__main__':
    main()
