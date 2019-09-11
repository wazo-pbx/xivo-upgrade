#!/bin/bash
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

set -e
set -u  # fail if variable is undefined
set -o pipefail  # fail if command before pipe fails

wait_until_ready(){
    WAIT_TIMEOUT=60
    WAIT_INTERVAL=1
    while ! ss --listening --tcp '( sport = :9497 )' | grep -q LISTEN; do
        sleep ${WAIT_INTERVAL}
        WAIT_TIMEOUT=$((WAIT_TIMEOUT - WAIT_INTERVAL))
        if [ "$WAIT_TIMEOUT" -eq 0 ]; then
            echo "wazo-auth is not ready"
            return 1
        fi
    done
}

if [ $XIVO_VERSION_INSTALLED \< '18.04' ]
then
    cd /usr/share/xivo-manage-db
    alembic upgrade 01b4c79b3d47
    cd "$OLDPWD"

    systemctl restart wazo-auth
    wait_until_ready
    if [ $? -ne 0 ]; then
        echo "Cannot start wazo-auth, please fix wazo-auth, re-run /usr/share/xivo-upgrade/pre-start.d/00* scripts and re-run wazo-upgrade"
        exit -1
    fi
fi
