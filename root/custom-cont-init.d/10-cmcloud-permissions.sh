#!/usr/bin/with-contenv bash
set -Eeuo pipefail

if ! id abc >/dev/null 2>&1; then
  exit 0
fi

abc_uid="$(id -u abc)"
abc_gid="$(id -g abc)"

for path in /config/wineprefix /config/cmcloud-app /config/logs /config/.cmcloud-runtime.env; do
  if [[ -e "$path" ]]; then
    chown -R "${abc_uid}:${abc_gid}" "$path"
  fi
done

if [[ -x /usr/bin/Xvnc ]]; then
  ln -sf /usr/bin/Xvnc /usr/local/bin/Xvnc
fi

