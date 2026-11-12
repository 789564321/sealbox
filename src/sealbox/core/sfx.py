"""自解压包构建。

* Windows：7z.sfx 模块 + 7z 载荷拼接成 .exe；
* macOS / Linux：shell 自解压脚本 + 载荷，双击运行，输入密码解压。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .sevenzip import SevenZip, SevenZipError, find_sfx_module

MARKER = "#__SEALBOX_PAYLOAD__"

# 注意：OFFSET 行必须是 12 位定宽占位符，构建时被替换成等长的真实偏移。
UNIX_TEMPLATE = """#!/bin/bash
# SealBox 自解压包（macOS / Linux）
# 双击运行，或在终端执行：bash 本文件
set -euo pipefail

SELF="${BASH_SOURCE[0]}"
OFFSET=000000000000
TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/sealbox.XXXXXX")"
trap 'rm -rf "$TMPROOT"' EXIT
PAYLOAD="$TMPROOT/payload.7z"
tail -c +$((OFFSET + 1)) "$SELF" > "$PAYLOAD"

SEVENZIP=""
for c in 7zz 7z 7za; do
  if command -v "$c" >/dev/null 2>&1; then SEVENZIP="$c"; break; fi
done
if [ -z "$SEVENZIP" ]; then
  for c in /opt/homebrew/bin/7zz /usr/local/bin/7zz /opt/homebrew/bin/7z /usr/local/bin/7z; do
    if [ -x "$c" ]; then SEVENZIP="$c"; break; fi
  done
fi
if [ -z "$SEVENZIP" ]; then
  echo "需要 7-Zip：macOS 可执行 brew install sevenzip；Linux 可安装 p7zip-full。" >&2
  exit 1
fi

printf '请输入密码: '
read -r -s PW
echo
OUTDIR="$(cd "$(dirname "$SELF")" && pwd)"
"$SEVENZIP" x -y "-p$PW" -o"$OUTDIR" "$PAYLOAD" >/dev/null
echo "解压完成：$OUTDIR"
if [ "$(uname)" = "Darwin" ]; then open "$OUTDIR" 2>/dev/null || true; fi
exit 0
#__SEALBOX_PAYLOAD__
"""


def resolve_target(target: str = "auto") -> str:
    if target in ("windows", "unix"):
        return target
    if sys.platform == "win32":
        return "windows"
    return "unix"


def suffix_for(target: str = "auto") -> str:
    resolved = resolve_target(target)
    if resolved == "windows":
        return ".exe"
    if sys.platform == "darwin":
        return ".command"
    return ".run"


def build_stub() -> bytes:
    """生成 shell 自解压头，并把 OFFSET 写成定长数字。"""
    stub = UNIX_TEMPLATE.encode("utf-8")
    placeholder = b"OFFSET=000000000000"
    offset = len(stub)
    if offset >= 10**12:
        raise SevenZipError("自解压头过大")
    stub = stub.replace(placeholder, f"OFFSET={offset:012d}".encode("ascii"))
    if len(stub) != offset:
        raise SevenZipError("自解压头偏移计算异常")
    return stub


def make_unix_sfx(archive: Path, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as out:
        out.write(build_stub())
        with open(archive, "rb") as src:
            shutil.copyfileobj(src, out, 1024 * 1024)
    os.chmod(dest, 0o755)
    return dest


def make_windows_sfx(sz: SevenZip, archive: Path, dest: Path, *, console: bool = False) -> Path:
    module = find_sfx_module(sz, console=console)
    if module is None:
        raise SevenZipError(
            "找不到 7z.sfx 自解压模块。请确认 7-Zip 安装完整，"
            "或把 7z.sfx 放到程序目录的 _vendor/7z 下。"
        )
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as out, open(module, "rb") as mod, open(archive, "rb") as src:
        shutil.copyfileobj(mod, out, 1024 * 1024)
        shutil.copyfileobj(src, out, 1024 * 1024)
    return dest


def build_sfx(sz: SevenZip, archive: Path, dest: Path, *, target: str = "auto", console: bool = False) -> Path:
    resolved = resolve_target(target)
    if resolved == "windows":
        return make_windows_sfx(sz, archive, dest, console=console)
    return make_unix_sfx(archive, dest)
