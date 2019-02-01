#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import os
import sys
import urllib3

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


def _update_source(dird_client, source_uuid, source_config):
    update_functions = {
        'csv': dird_client.csv_source.edit,
        'csv_ws': dird_client.csv_ws_source.edit,
        'ldap': dird_client.ldap_source.edit,
        'personal': dird_client.personal_source.edit,
        'phonebook': dird_client.phonebook_source.edit,
        'wazo': dird_client.wazo_source.edit,
    }

    function = update_functions.get(source_config['backend'])
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

    function = create_functions.get(source_config['backend'])
    if not function:
        return

    function(source_config)


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
    for source_config in dird_config.values():
        name = source_config['name']
        for existing_source in existing_sources:
            if name == existing_source['name']:
                _update_source(dird_client, existing_source['uuid'], source_config)
                break
        else:
            _import_source(dird_client, source_config)


if __name__ == '__main__':
    main()
