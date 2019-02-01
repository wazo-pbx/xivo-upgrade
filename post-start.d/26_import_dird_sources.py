#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import os
import sys
import urllib3
import psycopg2

from contextlib import closing
from xivo.chain_map import ChainMap
from xivo.config_helper import (
    parse_config_file,
    read_config_file_hierarchy,
)
from xivo_auth_client import Client as AuthClient
from wazo_dird_client import Client as DirdClient

logger = logging.getLogger('26_import_dird_sources')
logging.basicConfig(level=logging.INFO)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DUMP_FILENAME = '/var/lib/xivo-upgrade/wazo_dird_source.json'
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
    return {
        'auth': {
            'username': key_file['service_id'],
            'password': key_file['service_key'],
        },
    }


def _update_source_backend_type(conn, source_uuid, backend):
    cursor = conn.cursor()
    query = 'UPDATE dird_source SET backend=%s WHERE uuid=%s'
    cursor.execute(query, (backend, source_uuid))
    conn.commit()


def _update_source(dird_client, source_uuid, source_config):
    update_functions = {
        'csv': dird_client.csv_source.edit,
        'csv_ws': dird_client.csv_ws_source.edit,
        'ldap': dird_client.ldap_source.edit,
        'personal': dird_client.personal_source.edit,
        'phonebook': dird_client.phonebook_source.edit,
        'wazo': dird_client.wazo_source.edit,
    }

    function = update_functions.get(source_config['type'])
    if not function:
        return

    function(source_uuid, source_config)


def _import_source(dird_client, source_config):
    create_functions = {
        'csv': dird_client.csv_source.create,
        'csv_ws': dird_client.csv_ws_source.create,
        'ldap': dird_client.ldap_source.create,
        'personal': dird_client.personal_source.create,
        'phonebook': dird_client.phonebook_source.create,
        'wazo': dird_client.wazo_source.create,
    }

    function = create_functions.get(source_config['type'])
    if not function:
        return

    function(source_config)


def _find_matching_source(existing_sources, source_name):
    for existing_source in existing_sources:
        if existing_source['name'] == source_name:
            return existing_source


def _delete_remaining_sources(conn):
    cursor = conn.cursor()
    query = 'DELETE dird_source WHERE backend=%s'
    cursor.execute(query, ('migration',))
    conn.commit()


def main():
    if not os.path.exists(DUMP_FILENAME):
        sys.exit(0)

    with open(DUMP_FILENAME, 'r') as f:
        dird_config = json.read(f)

    config = _load_config()
    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new(expiration=300)['token']
    dird_client = DirdClient(token=token, **config['dird'])
    existing_sources = dird_client.sources.list(recurse=True)['items']
    with closing(psycopg2.connect(config['db_uri'])) as conn:
        for source_config in dird_config.values():
            # TODO set the tenant_uuid of all sources
            existing_source = _find_matching_source(existing_sources, source_config['name'])
            if existing_source:
                _update_source_backend_type(conn, existing_source['uuid'], source_config['type'])
                _update_source(dird_client, existing_source['uuid'], source_config)
            else:
                _import_source(dird_client, source_config)
        _delete_remaining_sources(conn)


if __name__ == '__main__':
    main()
