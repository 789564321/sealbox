"""任务模型与执行引擎。

一次任务 = 一批输入（文件/文件夹）+ 一组输出格式 + 一份密码。
执行时先写到暂存目录，校验通过后再改名落到目标目录，避免半成品。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable

from . import history as history_mod
from . import manifest as manifest_mod
from . import password as pw_mod
from . import sfx as sfx_mod
from . import verifier
from .sevenzip import (
    OperationCancelled,
    SevenZip,
    SevenZipError,
    add_args,
    find_sevenzip,
    parse_percent,
)

FORMATS = ("7z", "zip", "sfx")
FORMAT_LABELS = {"7z": "7z", "zip": "ZIP", "sfx": "自解压"}

STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


@dataclass
class JobOptions:
    formats: tuple[str, ...] = ("7z",)
    output_dir: Path | None = None
    base_name: str | None = None
    pwd_style: str = "hex32"
    write_pwd_file: bool = True
    verify: bool = True
    level: int = 9
    sfx_target: str = "auto"
    sfx_console: bool = False
    zip_method: str = "AES256"
    overwrite: bool = False
    record_history: bool = True

    def clone(self) -> "JobOptions":
        return replace(self)


@dataclass
class Task:
    inputs: list[Path]
    options: JobOptions = field(default_factory=JobOptions)
    pw_text: str | None = None
    state: str = STATE_PENDING
    progress: float = 0.0
    stage: str = ""
    outputs: list[Path] = field(default_factory=list)
    entries: list[dict] = field(default_factory=list)
    pwd_file: Path | None = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    index: int = 0

    @property
    def name(self) -> str:
        if len(self.inputs) == 1:
            return self.inputs[0].name
        return f"{self.inputs[0].name} 等 {len(self.inputs)} 项"

    def to_dict(self) -> dict:
        return {
            "inputs": [str(p) for p in self.inputs],
            "outputs": [str(p) for p in self.outputs],
            "pwd_file": str(self.pwd_file) if self.pwd_file else None,
            "pw_text": self.pw_text,
            "state": self.state,
            "progress": round(self.progress, 4),
            "stage": self.stage,
            "error": self.error,
            "formats": list(self.options.formats),
        }


@dataclass
class Callbacks:
    log: Callable[[str], None] | None = None
    progress: Callable[[float, str], None] | None = None
    state: Callable[[Task], None] | None = None
    output: Callable[[Path], None] | None = None


def _notify_progress(task: Task, cb: Callbacks) -> None:
    if cb.progress is not None:
        cb.progress(task.progress, task.stage)


def _notify_state(task: Task, cb: Callbacks) -> None:
    if cb.state is not None:
        cb.state(task)


def _log(cb: Callbacks, line: str) -> None:
    if cb.log is not None:
        cb.log(line)


def _check_cancel(cancel: Event) -> None:
    if cancel is not None and cancel.is_set():
        raise OperationCancelled("已取消")


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child = child.resolve()
        parent = parent.resolve()
    except OSError:
        return False
    return child == parent or parent in child.parents


def unique_path(path: Path, overwrite: bool = False) -> Path:
    path = Path(path)
    if overwrite or not path.exists():
        return path
    for i in range(2, 10000):
        cand = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(f"同名文件过多：{path}")


def _sanitize_base(name: str) -> str:
    cleaned = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in name).strip().strip(".")
    return cleaned or "archive"


def default_base_name(inputs: list[Path]) -> str:
    items = [Path(p) for p in inputs]
    if len(items) == 1:
        item = items[0]
        return item.stem if item.is_file() else item.name
    parents = {p.parent for p in items}
    if len(parents) == 1:
        return next(iter(parents)).name or "archive"
    return "archive-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _archive_root_and_names(inputs: list[Path]) -> tuple[Path | None, list[str]]:
    """让归档里保存干净的相对路径：cwd 设为公共父目录，传相对名。"""
    items = [Path(p) for p in inputs]
    if len(items) == 1:
        return items[0].parent, [items[0].name]
    parents = [p.parent for p in items]
    try:
        root = Path(os.path.commonpath([str(p) for p in parents]))
    except ValueError:
        return None, [str(p) for p in items]
    names: list[str] = []
    for item in items:
        try:
            names.append(str(item.relative_to(root)))
        except ValueError:
            return None, [str(p) for p in items]
    return root, names


def _staging_dir(out_dir: Path, inputs: list[Path]) -> Path:
    """输出目录若落在被压缩的文件夹里，就改用系统临时目录，避免把半成品打进去。"""
    for item in inputs:
        if item.is_dir() and _is_within(out_dir, item):
            return Path(tempfile.mkdtemp(prefix="sealbox-"))
    staging = out_dir / ".sealbox-tmp"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def _move(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dest)
    except OSError:
        shutil.move(str(src), str(dest))


def _safe_unlink(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


def plan_task(inputs: list[Path], options: JobOptions | None = None) -> Task:
    items = [Path(p).expanduser() for p in inputs]
    return Task(inputs=items, options=(options or JobOptions()).clone())


def _entry_command(fmt: str, name: str) -> str:
    if fmt == "sfx":
        if sys.platform == "win32":
            return f"双击 {name}，输入密码解压"
        return f"双击/运行 {name}，输入密码解压"
    return f'7z x -p"密码" "{name}"'


def _fmt_label(fmt: str) -> str:
    if fmt == "7z":
        return "7z（AES-256，文件名加密：是）"
    if fmt == "zip":
        return "ZIP（AES-256，文件名不加密）"
    return "自解压（内含 7z / AES-256）"


def execute_task(
    task: Task,
    *,
    sz: SevenZip | None = None,
    cancel: Event | None = None,
    cb: Callbacks | None = None,
) -> Task:
    cb = cb or Callbacks()
    cancel = cancel or Event()
    task.state = STATE_RUNNING
    task.error = None
    task.outputs = []
    task.pwd_file = None
    task.progress = 0.0
    task.stage = "准备中"
    task.started_at = time.time()
    _notify_state(task, cb)
    _notify_progress(task, cb)

    inputs = [Path(p).expanduser().resolve() for p in task.inputs]
    if not inputs:
        return _fail(task, cb, "没有输入文件")
    missing = [p for p in inputs if not p.exists()]
    if missing:
        return _fail(task, cb, f"路径不存在：{missing[0]}")

    try:
        out_dir = (
            Path(task.options.output_dir).expanduser().resolve()
            if task.options.output_dir
            else inputs[0].parent
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        base = _sanitize_base(task.options.base_name or default_base_name(inputs))
        pw = task.pw_text or pw_mod.generate(task.options.pwd_style)
        task.pw_text = pw
        formats = [f for f in task.options.formats if f in FORMATS] or ["7z"]
        total = len(formats)
        root, names = _archive_root_and_names(inputs)
        if root is None:
            _log(cb, "提示：输入分散在不同磁盘，归档内将保留绝对路径。")
        staging = _staging_dir(out_dir, inputs)
    except Exception as exc:  # 准备阶段的错误
        return _fail(task, cb, f"{type(exc).__name__}: {exc}")

    entries: list[dict] = []
    try:
        sz = sz or SevenZip(find_sevenzip())
        _log(cb, f"使用 7-Zip {sz.version()}：{sz.exe}")

        for i, fmt in enumerate(formats):
            _check_cancel(cancel)
            label = FORMAT_LABELS[fmt]
            task.stage = f"{label}压缩中"
            _notify_progress(task, cb)

            if fmt == "sfx":
                suffix = sfx_mod.suffix_for(task.options.sfx_target)
            else:
                suffix = ".7z" if fmt == "7z" else ".zip"
            final = unique_path(out_dir / f"{base}{suffix}", task.options.overwrite)
            inner = staging / f"part{i}.7z"
            target = staging / f"part{i}{suffix}"
            build_fmt = "7z" if fmt == "sfx" else fmt
            local = [0.0]

            def on_line(line: str, i=i, local=local) -> None:
                if "%" in line:
                    pct = parse_percent(line, local[0])
                    local[0] = pct
                    task.progress = (i + 0.75 * pct) / total * 0.9
                    task.stage = f"{label}压缩中 {int(pct * 100)}%"
                    _notify_progress(task, cb)
                else:
                    _log(cb, line)

            args = add_args(
                build_fmt,
                inner if fmt == "sfx" else target,
                names,
                pw,
                level=task.options.level,
                zip_method=task.options.zip_method,
            )
            code, tail = sz.run(args, on_line=on_line, cancel=cancel, cwd=root)
            if code != 0:
                raise SevenZipError(tail[-1] if tail else "7z 返回失败")

            if fmt == "sfx":
                task.stage = "生成自解压"
                _notify_progress(task, cb)
                sfx_mod.build_sfx(
                    sz,
                    inner,
                    target,
                    target=task.options.sfx_target,
                    console=task.options.sfx_console,
                )
                _safe_unlink(inner)

            if task.options.verify:
                task.stage = "校验归档"
                _notify_progress(task, cb)
                ok, hint = verifier.test_archive(sz, target, pw, cancel=cancel)
                if not ok:
                    _safe_unlink(target)
                    raise SevenZipError(f"归档校验失败：{hint}")

            task.stage = "计算 SHA-256"
            _notify_progress(task, cb)
            digest = verifier.sha256_file(
                target,
                cancel=cancel,
                on_progress=lambda frac, i=i: _hash_progress(task, cb, i, total, frac),
            )
            _move(target, final)
            task.outputs.append(final)
            entries.append(
                {
                    "name": final.name,
                    "fmt_label": _fmt_label(fmt),
                    "size": final.stat().st_size,
                    "sha256": digest,
                    "command": _entry_command(fmt, final.name),
                }
            )
            if cb.output is not None:
                cb.output(final)
            task.progress = (i + 1) / total * 0.9
            _notify_progress(task, cb)

        if task.options.write_pwd_file and entries:
            task.stage = "写入密码 TXT"
            _notify_progress(task, cb)
            text = manifest_mod.render(task, entries)
            task.pwd_file = manifest_mod.write_text(
                unique_path(out_dir / f"{base}.密码.txt", task.options.overwrite), text
            )

        task.entries = entries
        task.state = STATE_DONE
        task.progress = 1.0
        task.stage = "完成"
        if task.options.record_history:
            history_mod.record(task)
        _log(cb, f"完成：{len(entries)} 个加密包")
    except OperationCancelled:
        task.state = STATE_CANCELLED
        task.error = "已取消"
    except (SevenZipError, OSError, ValueError) as exc:
        task.state = STATE_FAILED
        task.error = str(exc)
    except Exception as exc:  # 兜底，避免线程直接崩掉
        task.state = STATE_FAILED
        task.error = f"{type(exc).__name__}: {exc}"
    finally:
        task.entries = entries
        task.finished_at = time.time()
        shutil.rmtree(staging, ignore_errors=True)
        if task.state == STATE_FAILED and entries and task.options.write_pwd_file and not task.pwd_file:
            try:
                text = manifest_mod.render(task, entries)
                task.pwd_file = manifest_mod.write_text(
                    unique_path(out_dir / f"{base}.密码.txt", task.options.overwrite), text
                )
            except Exception:
                pass
        _notify_progress(task, cb)
        _notify_state(task, cb)
    return task


def _hash_progress(task: Task, cb: Callbacks, i: int, total: int, frac: float) -> None:
    task.progress = (i + 0.75 + 0.20 * frac) / total * 0.9
    _notify_progress(task, cb)


def _fail(task: Task, cb: Callbacks, message: str) -> Task:
    task.state = STATE_FAILED
    task.error = message
    task.stage = "失败"
    task.finished_at = time.time()
    _log(cb, message)
    _notify_state(task, cb)
    return task
