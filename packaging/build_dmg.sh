#!/usr/bin/env bash
# 构建 macOS 安装镜像（DMG）：在 macOS 本机或 CI 上执行
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="0.1.0"
APP="dist/SealBox.app"
OUT="dist/SealBox-${VERSION}-macos-arm64.dmg"

if [ ! -d "$APP" ]; then
  echo "未找到 $APP，请先运行 python3 packaging/build.py" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

rm -f "$OUT"
hdiutil create \
  -volname "SealBox" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$OUT"

echo "DMG: $OUT"
shasum -a 256 "$OUT"
