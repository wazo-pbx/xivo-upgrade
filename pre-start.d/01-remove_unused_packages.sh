#!/bin/bash
# Copyright 2018-2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

is_package_installed() {
    [ "$(dpkg-query -W -f '${Status}' "$1" 2>/dev/null)" = 'install ok installed' ]
}

is_package_purgeable() {
    local output

    output="$(dpkg-query -W -f '${Status}' "$1" 2>/dev/null)"

    [ "$?" -eq 0 -a "$output" != 'unknown ok not-installed' ]
}

renamed_packages="wazo-dird-phoned
                  xivo-ctid-ng
                  xivo-dird
                  xivo-websocketd
                  xivo-dird-phoned
                  xivo
                  xivo-base
                  xivo-confd
                  xivo-agentd
                  xivo-purge-db
                  xivo-agid
                  xivo-provd
                  xivo-provd-cli
                  xivo-dhcpd-update"

removed_packages="python-alembic
                  wazo-admin-ui
                  xivo-ctid
                  xivo-ctid-client
                  xivo-ctid-client-python3
                  xivo-web-interface"

for package in $renamed_packages $removed_packages; do
    if is_package_purgeable $package; then
        apt-get purge -y $package
    fi
done

# purge postgresql-X.X packages
if is_package_installed xivo-dbms; then
   if is_package_purgeable postgresql-9.4; then
       apt-get purge -y postgresql-9.4 postgresql-client-9.4 postgresql-plpython-9.4 postgresql-contrib-9.4
       systemctl restart postgresql.service
   fi
fi

# purge php5-common
if ! is_package_installed php5-common; then
    if is_package_purgeable php5-common; then
       apt-get purge -y php5-common
    fi
fi
