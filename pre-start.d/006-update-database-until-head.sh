#!/bin/bash
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

set -e
set -u  # fail if variable is undefined
set -o pipefail  # fail if command before pipe fails

export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:=noninteractive}"

TENANT_MIGRATION='/var/lib/xivo-upgrade/entity_tenant_migration'
USER_MIGRATION='/var/lib/xivo-upgrade/migrate_xivo_user_to_wazo_user'
SERVICE_MIGRATION='/var/lib/xivo-upgrade/migrate_xivo_service_to_wazo_user'
ADMIN_MIGRATION='/var/lib/xivo-upgrade/migrate_xivo_admin_to_wazo_user'

if [ $XIVO_VERSION_INSTALLED \< '18.04' ]
then
    if [ ! -f $TENANT_MIGRATION ]; then
        echo 'update-database-until-head: 002-create-tenants-from-entities.py should be executed first'
        exit 1
    fi
    if [ ! -f $USER_MIGRATION ]; then
        echo 'update-database-until-head: 003-load-wazo-user-from-file.py should be executed first'
        exit 1
    fi
    if [ ! -f $SERVICE_MIGRATION ]; then
        echo 'update-database-until-head: 004-load-wazo-user-external-api-from-file.py should be executed first'
        exit 1
    fi
    if [ ! -f $ADMIN_MIGRATION ]; then
        echo 'update-database-until-head: 005-load-wazo-user-admin-from-file.py should be executed first'
        exit 1
    fi
    echo "xivo-manage-db xivo-manage-db/db-skip boolean false" | debconf-set-selections
    systemctl stop wazo-auth
    dpkg-reconfigure xivo-manage-db
fi
