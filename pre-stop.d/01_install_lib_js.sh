#!/bin/bash
dpkg -l pf-xivo-lib-js-jqplot 2>/dev/null | grep '^i' -q
if [ $? -eq 0 ]; then
    apt-get install -y xivo-lib-js-jqplot xivo-lib-js-jquery.mousewheel xivo-lib-js-schedule 1> /dev/null
fi