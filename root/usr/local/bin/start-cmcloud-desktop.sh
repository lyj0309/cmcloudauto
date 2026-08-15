#!/usr/bin/with-contenv bash
set -Eeuo pipefail

if [[ "${CMCLOUD_FUNCTION_MODE:-0}" == "1" ]]; then
  exit 0
fi

/usr/local/bin/bootstrap-cmcloud-runtime.sh

(
  while sleep 1; do
    DISPLAY=:1 wmctrl -r 'cmcloud - Wine 桌面' \
      -b remove,fullscreen 2>/dev/null || true
    DISPLAY=:1 wmctrl -r 'cmcloud - Wine 桌面' \
      -b remove,maximized_vert,maximized_horz 2>/dev/null || true
    DISPLAY=:1 wmctrl -r 'cmcloud - Wine 桌面' \
      -e 0,40,20,1180,540 2>/dev/null || true
  done
) &

if [[ "${CMCLOUD_AUTO_LOGIN:-1}" == "1" ]]; then
  /usr/local/bin/cmcloud-autologin.py >>/config/logs/autologin.log 2>&1 &
fi

if [[ "${AUTO_START_CMCLOUD:-1}" == "1" ]]; then
  exec /usr/local/bin/launch-cmcloud.sh
fi

exec /usr/bin/xterm -fa Monospace -fs 11 -geometry 100x24+24+24 -title "Ecloud Desktop" -e bash
