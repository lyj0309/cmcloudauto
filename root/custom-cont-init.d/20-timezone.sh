#!/usr/bin/with-contenv bash
set -Eeuo pipefail

tz_name="${TZ:-Asia/Shanghai}"
zoneinfo_path="/usr/share/zoneinfo/${tz_name}"

if [[ ! -e "$zoneinfo_path" ]]; then
  printf '[cmcloud-timezone] zoneinfo not found for %s\n' "$tz_name" >&2
  exit 0
fi

ln -snf "$zoneinfo_path" /etc/localtime
printf '%s\n' "$tz_name" >/etc/timezone

