#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json
import os
import requests
import subprocess
import sys
import time

from urllib3.exceptions import InsecureRequestWarning
from wazo_auth_client import Client as AuthClient
from xivo.chain_map import ChainMap
from xivo.config_helper import read_config_file_hierarchy, parse_config_file

_DEFAULT_CONFIG = {
    'config_file': '/etc/wazo-upgrade/config.yml',
    'auth': {
        'key_file': '/var/lib/wazo-auth-keys/wazo-upgrade-key.yml'
    },
    'provd': {
        'prefix': '',
    }
}
PROVD_JSONDB_DEVICES_DIR = '/var/lib/wazo-provd/jsondb/devices'

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


def _wait_for_provd(provd_config):
    url = 'https://{host}:{port}{prefix}/configure'.format(**provd_config)
    for _ in range(30):
        try:
            requests.get(url, verify=False)
            return
        except requests.exceptions.ConnectionError:
            time.sleep(1.0)

    print('provd is_new device migration failed, could not connect to wazo-provd')
    sys.exit(2)


def _migrate_device(device_id, master_tenant_uuid):
    device_path = os.path.join(PROVD_JSONDB_DEVICES_DIR, device_id)
    with open(device_path, 'r+') as file_:
        device = json.load(file_)
        device['is_new'] = device['tenant_uuid'] == master_tenant_uuid
        file_.seek(0)
        json.dump(device, file_)
        file_.truncate()


def migrate_new_status():
    config = _load_config()
    _wait_for_provd(config['provd'])

    auth_client = AuthClient(**config['auth'])
    token = auth_client.token.new('wazo_user', expiration=5 * 60)
    auth_client.set_token(token['token'])

    master_tenant_uuid = token['metadata']['tenant_uuid']

    # Migrate devices
    for dir_entry in os.scandir(PROVD_JSONDB_DEVICES_DIR):
        device_id = dir_entry.name
        try:
            _migrate_device(device_id, master_tenant_uuid)
        except json.JSONDecodeError:
            print(device_id, 'is not a valid JSON file. Skipping.')
            continue

    subprocess.run(['systemctl', 'restart', 'wazo-provd'])


def main():
    args = parse_args()

    if not args.force:
        version_installed = os.getenv('XIVO_VERSION_INSTALLED')
        if version_installed > '19.05':
            sys.exit(0)

    sentinel_file = '/var/lib/xivo-upgrade/56_provd_device_new_status_migration'
    if os.path.exists(sentinel_file):
        # migration already done
        sys.exit(1)

    migrate_new_status()

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
