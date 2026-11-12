#!/usr/bin/env bash
# 在 Linux 本机构建（PyInstaller 不能交叉编译）
set -euo pipefail
cd "$(dirname "$0")/.."
python3 packaging/build.py
echo
echo "产物：dist/SealBox/、dist/SealBoxCLI/、dist/SealBox-linux-x64.zip"
