#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import os
import sys
import requests
import json
import subprocess
import time

from contextlib import contextmanager
from urllib3.exceptions import InsecureRequestWarning
from wazo_auth_client import Client as AuthClient
from wazo_confd_client import Client as ConfdClient
from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy, parse_config_file

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'auth': {
        'key_file': '/var/lib/wazo-auth-keys/wazo-upgrade-key.yml'
    }
}

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def _load_config():
    file_config = read_config_file_hierarchy(_DEFAULT_CONFIG)
    key_config = _load_key_file(ChainMap(file_config, _DEFAULT_CONFIG))
    return ChainMap(key_config, file_config, _DEFAULT_CONFIG)


def _load_key_file(config):
    key_file = parse_config_file(config['auth']['key_file'])
    return {
        'auth': {'username': key_file['service_id'], 'password': key_file['service_key']},
    }


def _wait_for_call_logd(call_logd_config):
    url = 'https://{host}:{port}/{version}/status'.format(**call_logd_config)
    for _ in range(30):
        try:
            requests.get(url, verify=False)
            return
        except requests.exceptions.ConnectionError:
            time.sleep(1.0)

    print('call_logd tenant migration failed, could not connect to wazo-call-logd')
    sys.exit(2)


@contextmanager
def _migration_plugin(call_logd_config):

    config_filename = '/etc/wazo-call-logd/conf.d/50-wazo-tenant-migration.yml'
    config_file = '''\
enabled_plugins:
  tenant_migration: true
'''

    with open(config_filename, 'w') as f:
        f.write(config_file)
    subprocess.run(['systemctl', 'restart', 'wazo-call-logd'])
    _wait_for_call_logd(call_logd_config)

    try:
        yield
    finally:
        try:
            os.unlink(config_filename)
        except OSError:
            pass
        subprocess.run(['systemctl', 'restart', 'wazo-call-logd'])
        _wait_for_call_logd(call_logd_config)


def migrate_tenants():
    config = _load_config()
    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new(expiration=5 * 60)['token']
    auth_client.set_token(token)
    confd = ConfdClient(token=token, **config['confd'])

    body = {
        'contexts': [
            {"context": context['name'], "tenant_uuid": context['tenant_uuid']}
            for context in confd.contexts.list(recurse=True)["items"]
        ]
    }

    with _migration_plugin(config['call_logd']):
        url = 'https://{host}:{port}/{version}/tenant-migration'.format(**config['call_logd'])
        result = requests.post(
            url,
            data=json.dumps(body),
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            verify=False,
        )

        if result.status_code != 200:
            print(
                'call_logd tenant migration failed, status-code {}:\n'
                '{}\ncheck /var/log/wazo-call-logd.log for more info'
                .format(result.status_code, result.text)
            )
            sys.exit(2)


def main():
    args = parse_args()

    if not args.force:
        version_installed = os.getenv('XIVO_VERSION_INSTALLED')
        if version_installed > '19.10':
            sys.exit(0)

    sentinel_file = '/var/lib/xivo-upgrade/62_call_logd_tenant_migration'
    if os.path.exists(sentinel_file):
        # migration already done
        sys.exit(1)

    migrate_tenants()

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
