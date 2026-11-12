"""哈希与归档校验。"""

from __future__ import annotations

import hashlib
import os
from threading import Event
from typing import Callable

from .sevenzip import SevenZip, OperationCancelled

CHUNK = 1024 * 1024


def sha256_file(path, *, cancel: Event | None = None, on_progress: Callable[[float], None] | None = None) -> str:
    digest = hashlib.sha256()
    total = os.path.getsize(path) or 1
    done = 0
    with open(path, "rb") as fh:
        while True:
            if cancel is not None and cancel.is_set():
                raise OperationCancelled("已取消")
            block = fh.read(CHUNK)
            if not block:
                break
            digest.update(block)
            done += len(block)
            if on_progress is not None:
                on_progress(min(done / total, 1.0))
    return digest.hexdigest()


def test_archive(sz: SevenZip, archive, pw, *, cancel: Event | None = None) -> tuple[bool, str]:
    """用 7z t 校验归档；返回 (是否通过, 提示)。"""
    code, tail = sz.run(["t", "-y", f"-p{pw}", str(archive)], cancel=cancel)
    if code == 0:
        return True, "校验通过"
    return False, "密码错误或归档已损坏"


def list_archive(sz: SevenZip, archive, pw=None) -> list[str]:
    """列出归档条目名（用于判断文件数/展示）。"""
    code, tail = sz.run(list_args(archive, pw))
    if code != 0:
        return []
    names: list[str] = []
    for line in tail:
        if line.startswith("Path = "):
            names.append(line[len("Path = "):])
    return names


def extract_archive(sz: SevenZip, archive, out_dir, pw, *, cancel: Event | None = None) -> tuple[bool, str]:
    out_dir = str(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    code, tail = sz.run(["x", "-y", f"-o{out_dir}", f"-p{pw}", str(archive)], cancel=cancel)
    if code == 0:
        return True, str(out_dir)
    return False, "密码错误或归档已损坏"
