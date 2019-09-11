#!/bin/bash
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

sentinel="/var/lib/xivo-upgrade/10_remove_legacy_push_mobile_v2"

[ -e "$sentinel" ] && exit 0


# Remove the obsolete package built by wazo-plugind that will conflict
# the new one
pkg_name="wazo-plugind-wazo-push-mobile-official"
output=$(dpkg-query -W -f '${Status}' "$pkg_name" 2>/dev/null || true)
if [ "$output" == "install ok installed" ]; then
    # NOTE(sileht): postrm uses the rules file that no longer on the server
    # during purge, so delete it.
    rm -f /var/lib/dpkg/info/wazo-plugind-wazo-push-mobile-official.postrm
    apt-get purge -y "$pkg_name"
fi

touch $sentinel
