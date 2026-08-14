#!/usr/bin/with-contenv bash
set -Eeuo pipefail

wine_prefix="${CMCLOUD_WINEPREFIX:-${WINEPREFIX:-/config/wineprefix}}"
replacement_key='HKCU\Software\Wine\Fonts\Replacements'

export WINEPREFIX="$wine_prefix"
export WINEDEBUG=-all

add_replacement() {
  wine reg add "$replacement_key" /v "$1" /t REG_SZ /d "$2" /f >/dev/null
}

for font_name in 'SimSun' 'NSimSun' 'FangSong' 'KaiTi' '宋体' '新宋体' '仿宋' '楷体'; do
  add_replacement "$font_name" 'Noto Serif CJK SC'
done

for font_name in 'SimHei' 'Microsoft YaHei' 'Microsoft YaHei UI' 'DengXian' 'Arial Unicode MS' '黑体' '微软雅黑' '等线'; do
  add_replacement "$font_name" 'Noto Sans CJK SC'
done

wineserver -w

