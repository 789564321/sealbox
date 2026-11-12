"""密码 TXT 的渲染与解析。"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

RULE = "=" * 40
THIN = "-" * 40
PW_RE = re.compile(r"^密码\s*[:：]\s*(\S+)\s*$", re.MULTILINE)


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} 字节"
    units = ["KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:,.2f} {unit}"
    return f"{size} 字节"


def render(task, entries: list[dict]) -> str:
    """entries: name / fmt_label / size / sha256 / header / command"""
    style = getattr(task.options, "pwd_style", "hex32")
    try:
        from .password import LABELS, ENTROPY_BITS

        style_label = f"{LABELS.get(style, style)}（约 {ENTROPY_BITS.get(style, 0)} bit 熵）"
    except Exception:
        style_label = style

    lines: list[str] = [
        RULE,
        " SealBox 加密包信息",
        RULE,
        f"生成时间  : {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"密码      : {task.pw_text}",
        f"密码形态  : {style_label}",
        THIN,
    ]
    for entry in entries:
        lines += [
            f"加密包    : {entry['name']}",
            f"格式      : {entry['fmt_label']}",
            f"大小      : {_human_size(int(entry['size']))}",
            f"SHA-256   : {entry['sha256']}",
            f"解压      : {entry['command']}",
            THIN,
        ]
    lines += [
        "安全提示  : 密码与压缩包请分渠道发送；放在同一目录等于没有加密。",
        RULE,
    ]
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def extract_pw(text: str) -> str | None:
    match = PW_RE.search(text or "")
    return match.group(1) if match else None


def read_pw_file(path: Path) -> str | None:
    try:
        return extract_pw(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def find_sibling_pw_file(archive: Path) -> Path | None:
    """在归档旁边找 <base>.密码.txt。"""
    archive = Path(archive)
    stem = archive.stem
    for name in (f"{stem}.密码.txt", f"{archive.name}.密码.txt"):
        cand = archive.with_name(name)
        if cand.is_file():
            return cand
    return None
