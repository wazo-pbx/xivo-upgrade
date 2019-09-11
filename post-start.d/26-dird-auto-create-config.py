#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import os
import sys
import requests

from wazo_auth_client import Client as AuthClient
from xivo.chain_map import ChainMap
from xivo.config_helper import (
    read_config_file_hierarchy,
    parse_config_file,
)

_DEFAULT_CONFIG = {
    'uuid': os.getenv('XIVO_UUID'),
    'config_file': '/etc/wazo-upgrade/config.yml',
    'auth': {
        'key_file': '/var/lib/wazo-auth-keys/wazo-upgrade-key.yml'
    }
}

DEFAULT_DISPLAY_COLUMNS = [
    {'field': 'name', 'title': 'Nom', 'type': 'name'},
    {'field': 'phone', 'title': "Num\xE9ro", 'type': 'number', 'number_display': '{name}'},
    {'field': 'phone_mobile', 'title': 'Mobile', 'type': 'number', 'number_display': '{name} (mobile)'},
    {'field': 'voicemail', 'title': "Bo\xEEte vocale", 'type': 'voicemail'},
    {'field': 'favorite', 'title': 'Favoris', 'type': 'favorite'},
    {'field': 'email', 'title': 'E-mail', 'type': 'email'},
]
CONFERENCE_SOURCE_BODY = {
    'auth': {
        'host': 'localhost',
        'port': 9497,
        'verify_certificate': '/usr/share/xivo-certs/server.crt',
        'key_file': '/var/lib/wazo-auth-keys/wazo-dird-conference-backend-key.yml',
        'version': '0.1',
    },
    'confd': {
        'host': 'localhost',
        'port': 9486,
        'https': True,
        'verify_certificate': '/usr/share/xivo-certs/server.crt',
        'version': '1.1',
    },
    'format_columns': {
        'phone': '{extensions[0]}',
    },
    'searched_columns': ['name', 'extensions'],
    'first_matched_columns': [],
}
PERSONAL_SOURCE_BODY = {
    'name': 'personal',
    'format_columns': {
        'phone': '{number}',
        'name': '{firstname} {lastname}',
        'phone_mobile': '{mobile}',
        'reverse': '{firstname} {lastname}',
    },
    'searched_columns': ['firstname', 'lastname', 'number', 'mobile', 'fax'],
    'first_matched_columns': ['number', 'mobile'],
}
WAZO_SOURCE_BODY = {
    'auth': {
        'host': 'localhost',
        'port': 9497,
        'verify_certificate': '/usr/share/xivo-certs/server.crt',
        'key_file': '/var/lib/wazo-auth-keys/wazo-dird-wazo-backend-key.yml',
        'version': '0.1',
    },
    'confd': {
        'host': 'localhost',
        'port': 9486,
        'https': True,
        'verify_certificate': '/usr/share/xivo-certs/server.crt',
        'version': '1.1',
    },
    'format_columns': {
        'phone': '{exten}',
        'name': '{firstname} {lastname}',
    },
    'searched_columns': ['firstname', 'lastname', 'exten'],
    'first_matched_columns': [],
}
OFFICE_365_SOURCE_BODY = {
    'auth': {
        'host': 'localhost',
        'port': 9497,
        'verify_certificate': '/usr/share/xivo-certs/server.crt',
        'key_file': '/var/lib/wazo-auth-keys/wazo-dird-wazo-backend-key.yml',
        'version': '0.1',
    },
    'endpoint': 'https://graph.microsoft.com/v1.0/me/contacts',
    'format_columns': {
        'name': '{givenName} {surname}',
        'phone_mobile': '{mobilePhone}',
        'reverse': '{givenName} {surname}',
        'phone': '{businessPhones[0]}',
    },
    'searched_columns': ['givenName', 'surname', 'businessPhones'],
    'first_matched_columns': ['mobilePhone', 'businessPhones'],
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


def _auto_create_config():
    config = _load_config()
    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new('wazo_user', expiration=36000)['token']
    auth_client.set_token(token)

    tenants = auth_client.tenants.list()['items']

    base_url = 'https://{host}:{port}/{version}'.format(
        **config['dird']
    )
    conference_url = '{}/backends/conference/sources'.format(base_url)
    profiles_url = '{}/profiles'.format(base_url)
    displays_url = '{}/displays'.format(base_url)
    personal_url = '{}/backends/personal/sources'.format(base_url)
    wazo_url = '{}/backends/wazo/sources'.format(base_url)
    office365_url = '{}/backends/office365/sources'.format(base_url)
    sources_url = '{}/sources'.format(base_url)
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Auth-Token': token,
    }
    for tenant in tenants:
        name = tenant['name']
        if name == 'master':
            continue

        headers['Wazo-Tenant'] = tenant['uuid']

        def post(*args, **kwargs):
            return requests.post(
                *args,
                headers=headers,
                verify=config['dird']['verify_certificate'],
                **kwargs
            )

        post(conference_url, json=CONFERENCE_SOURCE_BODY)
        post(personal_url, json=PERSONAL_SOURCE_BODY)
        wazo_body = dict(name='auto_wazo_{}'.format(name), **WAZO_SOURCE_BODY)
        post(wazo_url, json=wazo_body)

        # add office365 is the plugin is installed
        office365_body = dict(name='auto_office365_{}'.format(name), **OFFICE_365_SOURCE_BODY)
        post(office365_url, json=office365_body)

        display_name = 'auto_{}'.format(name)
        display_body = {
            'name': display_name,
            'columns': DEFAULT_DISPLAY_COLUMNS,
        }
        post(displays_url, json=display_body).json()

        # GET all auto created sources before or during this migration
        response = requests.get(
            sources_url,
            headers=headers,
            verify=config['dird']['verify_certificate'],
        )
        sources = []
        if response.status_code == 200:
            for source in response.json()['items']:
                if source['name'] == 'personal':
                    sources.append(source)
                    continue

                if not source['name'].startswith('auto_'):
                    continue
                if not source['name'].endswith(name):
                    continue
                sources.append(source)

        # GET the display because the POST could return a 409 if it already exists
        response = requests.get(
            displays_url,
            headers=headers,
            verify=config['dird']['verify_certificate'],
        )
        display = None
        if response.status_code == 200:
            for d in response.json()['items']:
                if d['name'] == display_name:
                    display = d
                    break

        profile_body = {
            'name': 'default',
            'display': display,
            'services': {
                'lookup': {'sources': sources},
                'favorites': {'sources': sources},
                'reverse': {'sources': sources, 'timeout': 0.5},
            },
        }
        post(profiles_url, json=profile_body)


def main():
    args = parse_args()
    if not args.force:
        version_installed = os.getenv('XIVO_VERSION_INSTALLED')
        if version_installed >= '19.08':
            sys.exit(0)

    sentinel_file = '/var/lib/xivo-upgrade/dird-auto-create-config-v3'
    if os.path.exists(sentinel_file):
        # migration already done
        sys.exit(1)

    _auto_create_config()

    with open(sentinel_file, 'w'):
        pass


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
