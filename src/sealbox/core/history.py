"""压缩记录（本地 JSONL，默认可在窗口里查看）。

记录里含明文密码：仅存本机、权限 600，README 会明确提示风险。
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def default_dir() -> Path:
    base = os.environ.get("SEALBOX_HOME")
    if base:
        return Path(base).expanduser()
    if sys.platform == "win32":
        root = os.environ.get("APPDATA")
        if root:
            return Path(root) / "SealBox"
    return Path.home() / ".sealbox"


def history_path() -> Path:
    return default_dir() / "history.jsonl"


def _ensure() -> Path:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
        if os.name != "nt":
            os.chmod(path, 0o600)
    return path


def record(task) -> dict | None:
    """把一次成功任务的摘要追加进记录。"""
    if getattr(task, "state", "") != "done":
        return None
    entries = getattr(task, "entries", None) or []
    entry = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": [str(p) for p in task.inputs],
        "outputs": [
            {
                "name": e.get("name", ""),
                "size": int(e.get("size", 0)),
                "sha256": e.get("sha256", ""),
                "path": str(task.outputs[i]) if i < len(task.outputs) else "",
            }
            for i, e in enumerate(entries)
        ],
        "pw": task.pw_text or "",
        "pwd_file": str(task.pwd_file) if task.pwd_file else "",
        "formats": list(task.options.formats),
    }
    try:
        path = _ensure()
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
    except OSError:
        return None


def load(limit: int = 300) -> list[dict]:
    path = history_path()
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return list(reversed(rows[-limit:]))


def clear() -> None:
    path = history_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def export_csv(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = load(100000)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["时间", "原文件", "加密包", "密码", "大小(字节)", "SHA-256"])
        for row in rows:
            inputs = " | ".join(Path(p).name for p in row.get("inputs", []))
            for out in row.get("outputs", []) or [{}]:
                writer.writerow(
                    [
                        row.get("ts", ""),
                        inputs,
                        out.get("name", ""),
                        row.get("pw", ""),
                        out.get("size", ""),
                        out.get("sha256", ""),
                    ]
                )
    return path
