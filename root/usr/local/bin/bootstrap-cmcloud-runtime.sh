#!/usr/bin/with-contenv bash
set -Eeuo pipefail

runtime_prefix="${CMCLOUD_WINEPREFIX:-/config/wineprefix}"
state_file="${CMCLOUD_STATE_FILE:-/config/.cmcloud-runtime.env}"
app_home="${CMCLOUD_APP_HOME:-/config/cmcloud-app}"
source_zip="${CMCLOUD_SOURCE_ZIP:-/workspace/CloudComputer.zip}"
archive_sha_file="${app_home}/.source-archive.sha256"
fonts_stamp="${runtime_prefix}/.cmcloud-wine-fonts-v1"

log() {
  printf '[cmcloud-bootstrap] %s\n' "$*"
}

mkdir -p /config "$app_home" "$runtime_prefix" /config/logs

if [[ ! -f "${runtime_prefix}/system.reg" ]]; then
  log "Initializing Wine prefix in ${runtime_prefix}"
  mkdir -p "$runtime_prefix"
  xvfb-run -a env WINEPREFIX="$runtime_prefix" bash -c \
    'wineboot -i && winetricks -q win10 && wineserver -w'
fi

if [[ ! -f "$fonts_stamp" ]]; then
  log "Configuring Chinese font replacements"
  CMCLOUD_WINEPREFIX="$runtime_prefix" /usr/local/bin/configure-wine-fonts.sh
  touch "$fonts_stamp"
fi

exe_path="${app_home}/Ecloud Cloud Computer Application.exe"
if [[ ! -f "$exe_path" ]]; then
  if [[ ! -f "$source_zip" ]]; then
    printf '[cmcloud-bootstrap] source archive not found: %s\n' "$source_zip" >&2
    exit 1
  fi

  incoming="${app_home}.incoming"
  rm -rf "$incoming"
  mkdir -p "$incoming"
  log "Extracting ${source_zip}; first startup can take several minutes"
  unzip -q "$source_zip" -d "$incoming"

  extracted_root="$incoming"
  if [[ -f "${incoming}/CloudComputer/Ecloud Cloud Computer Application.exe" ]]; then
    extracted_root="${incoming}/CloudComputer"
  fi

  rsync -a "${extracted_root}/" "${app_home}/"
  sha256sum "$source_zip" | awk '{print $1}' >"$archive_sha_file"
  rm -rf "$incoming"
fi

if [[ ! -f "$exe_path" ]]; then
  printf '[cmcloud-bootstrap] executable not found after extraction: %s\n' "$exe_path" >&2
  exit 1
fi

mkdir -p "${runtime_prefix}/drive_c"
ln -sfn "$app_home" "${runtime_prefix}/drive_c/cmcloud"

{
  printf 'export CMCLOUD_WINEPREFIX=%q\n' "$runtime_prefix"
  printf 'export CMCLOUD_APP_HOME=%q\n' "$app_home"
  printf 'export CMCLOUD_EXECUTABLE=%q\n' "$exe_path"
} >"$state_file"

log "Launch target: ${exe_path}"
