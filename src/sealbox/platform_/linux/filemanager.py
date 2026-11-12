"""Linux 文件管理器脚本（Nautilus / Nemo / Caja）。"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

SCRIPT_NAME = "SealBox 加密"


def _script_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / ".local" / "share" / "nautilus" / "scripts",
        home / ".local" / "share" / "nemo" / "scripts",
        home / ".local" / "share" / "caja" / "scripts",
    ]


def _launcher() -> str:
    from ..win.shellmenu import launcher

    return " ".join(f'"{p}"' for p in launcher())


def install_menu() -> list[str]:
    if sys.platform == "win32" or sys.platform == "darwin":
        raise NotImplementedError("Linux 文件管理器脚本仅支持 Linux。")
    body = (
        "#!/bin/sh\n"
        "# SealBox：对选中的文件/文件夹加密\n"
        f'exec {_launcher()} --seal --gui "$@"\n'
    )
    written: list[str] = []
    for folder in _script_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / SCRIPT_NAME
            path.write_text(body, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            written.append(str(path))
        except OSError:
            continue
    if not written:
        return ["未找到可用的文件管理器脚本目录。"]
    return ["已安装文件管理器脚本：", *[f"  {p}" for p in written]]


def uninstall_menu() -> list[str]:
    removed: list[str] = []
    for folder in _script_dirs():
        path = folder / SCRIPT_NAME
        try:
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        except OSError:
            continue
    return ["已移除：", *[f"  {p}" for p in removed]] if removed else ["没有找到已安装的脚本。"]


def status() -> dict:
    return {"installed": any((d / SCRIPT_NAME).is_file() for d in _script_dirs())}
