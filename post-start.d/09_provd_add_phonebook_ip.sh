#!/bin/bash

. /etc/xivo/common.conf

xivo-provd-cli -p "" -c "configs['base'].set_config({'X_xivo_phonebook_ip': '$XIVO_NET4_IP'})" >/dev/null
