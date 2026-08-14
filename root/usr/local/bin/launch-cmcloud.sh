#!/usr/bin/with-contenv bash
set -Eeuo pipefail

/usr/local/bin/bootstrap-cmcloud-runtime.sh

state_file="${CMCLOUD_STATE_FILE:-/config/.cmcloud-runtime.env}"
# shellcheck disable=SC1090
source "$state_file"

app_dir="$(dirname "$CMCLOUD_EXECUTABLE")"
log_file="${CMCLOUD_WINE_LOG:-/config/logs/cmcloud-wine.log}"
debug_port="${CMCLOUD_DEBUG_PORT:-9222}"

export WINEPREFIX="$CMCLOUD_WINEPREFIX"
export WINEDEBUG="${CMCLOUD_WINEDEBUG:--all}"
cd "$app_dir"

printf '\n[%s] launching %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$CMCLOUD_EXECUTABLE" >>"$log_file"
wine_command=(wine)
if [[ -n "${CMCLOUD_DESKTOP_SIZE:-1180x540}" ]]; then
  wine_command+=(explorer "/desktop=cmcloud,${CMCLOUD_DESKTOP_SIZE:-1180x540}")
fi
wine_command+=("$CMCLOUD_EXECUTABLE")

exec env TZ="${CMCLOUD_WINE_TZ:-UTC}" "${wine_command[@]}" \
  --disable-gpu \
  --disable-software-rasterizer=false \
  --no-sandbox \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port="$debug_port" \
  --remote-allow-origins="http://127.0.0.1:${debug_port}" \
  >>"$log_file" 2>&1
