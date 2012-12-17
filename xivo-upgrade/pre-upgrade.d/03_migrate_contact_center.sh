#!/bin/bash
version=$(cat /usr/share/pf-xivo/XIVO-VERSION) 
is_executed_file="/var/lib/xivo-upgrade/$(basename $0)"

if [ -f "$is_executed_file" ]; then
    exit
else
    touch "$is_executed_file"
fi

if [ $version \< '12.24' ]
then
    for i in  `asterisk -rx "agent show" | grep available | awk '{print $1}'`
    do
        /usr/sbin/asterisk -rx "agent logoff Agent/${i}"
    done

    /usr/sbin/asterisk -rx "module unload app_queue.so"
    /usr/sbin/asterisk -rx "database deltree Queue/PersistentMembers"
fi
