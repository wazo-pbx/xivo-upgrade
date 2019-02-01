#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import os
import sys

from xivo.config_helper import read_config_file_hierarchy

logger = logging.getLogger('01_dump_dird_sources')
logging.basicConfig(level=logging.INFO)

DUMP_FILENAME = '/var/lib/xivo-upgrade/wazo_dird_source.json'


def main():
    if os.path.exists(DUMP_FILENAME):
        sys.exit(0)

    dird_config = read_config_file_hierarchy(
        {
            'config_file': '/etc/wazo-dird/config.yml',
            'extra_config_files': '/etc/wazo-dird/conf.d/',
        },
    )
    if not dird_config:
        dird_config = read_config_file_hierarchy(
            {
                'config_file': '/etc/xivo-dird/config.yml',
                'extra_config_files': '/etc/xivo-dird/conf.d/',
            },
        )

    with open(DUMP_FILENAME, 'w') as f:
        json.dump(dird_config['sources'], f)


if __name__ == '__main__':
    main()
