#!/bin/bash
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

sentinel="/var/lib/xivo-upgrade/10_remove_legacy_google_plugin"

[ -e "$sentinel" ] && exit 0

# Remove the obsolete package built by wazo-plugind that will conflict
# the new one
pkg_name="wazo-plugind-wazo-google-official"
output=$(dpkg-query -W -f '${Status}' "$pkg_name" 2>/dev/null || true)
if [ "$output" == "install ok installed" ]; then
    rm -f /var/lib/dpkg/info/wazo-plugind-wazo-google-official.postrm
    apt-get purge -y "$pkg_name"
fi

touch $sentinel
