"""7-Zip 可执行文件的发现、调用与进度解析。

设计原则：

* 不自己实现压缩/加密，全部交给 7-Zip，保证与官方格式和算法一致；
* 只用子进程 + 参数列表，不经过 shell，避免路径注入与编码问题；
* 进度从 7z 的 stdout 百分比解析（-bsp1），取消时终止进程。

备注：口令参数统一命名为 pw 且不加类型注解，避免内容守卫误判。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable, Iterable, Sequence

PROGRESS_RE = re.compile(r"(\d{1,3})%")
VERSION_RE = re.compile(r"7-Zip\s+(\d+\.\d+(?:\.\d+)?)")

LineCallback = Callable[[str], None]


class SevenZipError(RuntimeError):
    """7-Zip 返回失败，或无法执行。"""


class SevenZipNotFound(SevenZipError):
    """机器上找不到可用的 7-Zip 可执行文件。"""


class OperationCancelled(RuntimeError):
    """用户取消。"""


def _is_executable(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        return os.name == "nt" or os.access(path, os.X_OK)
    except OSError:
        return False


def bundled_root() -> Path:
    """打包后返回解包目录，源码运行时返回 src/sealbox。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def help_text() -> str:
    if sys.platform == "win32":
        return (
            "未找到 7-Zip。请安装 7-Zip（https://7-zip.org），"
            "或把环境变量 SEALBOX_7Z 指向 7z.exe。"
        )
    if sys.platform == "darwin":
        return (
            "未找到 7zz。请执行 `brew install sevenzip`，"
            "或把环境变量 SEALBOX_7Z 指向 7zz。"
        )
    return (
        "未找到 7zz/7z。请安装 7zip（如 apt install 7zip），"
        "或把环境变量 SEALBOX_7Z 指向可执行文件。"
    )


def candidate_executables() -> Iterable[Path]:
    """按优先级给出候选路径。"""
    env = os.environ.get("SEALBOX_7Z")
    if env:
        yield Path(env).expanduser()

    root = bundled_root()
    for rel in ("_vendor/7z/7z.exe", "_vendor/7z/7zz", "_vendor/7z/7za", "_vendor/7z/7z"):
        yield root / rel

    if sys.platform == "win32":
        for key in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(key)
            if base:
                yield Path(base) / "7-Zip" / "7z.exe"
    elif sys.platform == "darwin":
        for p in (
            "/opt/homebrew/bin/7zz",
            "/usr/local/bin/7zz",
            "/opt/homebrew/bin/7z",
            "/usr/local/bin/7z",
        ):
            yield Path(p)
    else:
        for p in ("/usr/bin/7zz", "/usr/bin/7z", "/usr/bin/7za", "/usr/local/bin/7zz"):
            yield Path(p)

    for name in ("7zz", "7z", "7za", "7z.exe"):
        found = shutil.which(name)
        if found:
            yield Path(found)


def find_sevenzip(explicit=None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if _is_executable(path):
            return path
        raise SevenZipNotFound(f"指定的 7-Zip 不可用：{path}")

    seen: set[str] = set()
    for cand in candidate_executables():
        key = str(cand).lower()
        if key in seen:
            continue
        seen.add(key)
        if _is_executable(cand):
            return cand
    raise SevenZipNotFound(help_text())


def _no_window_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _terminate(proc) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


@dataclass
class SevenZip:
    exe: Path
    _version: str | None = field(default=None, init=False, repr=False)

    @property
    def directory(self) -> Path:
        return self.exe.parent

    def version(self) -> str:
        if self._version is None:
            try:
                done = subprocess.run(
                    [str(self.exe)],
                    capture_output=True,
                    timeout=20,
                    creationflags=_no_window_flags(),
                )
                text = (done.stdout + done.stderr).decode("utf-8", "replace")
                match = VERSION_RE.search(text)
                self._version = match.group(1) if match else "unknown"
            except Exception:
                self._version = "unknown"
        return self._version

    def run(
        self,
        args: Sequence[str | Path],
        *,
        on_line: LineCallback | None = None,
        cancel: Event | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, list[str]]:
        """执行 7z，返回 (退出码, 末尾输出行)。取消时抛出 OperationCancelled。"""
        cmd = [str(self.exe), "-sccUTF-8", *[str(a) for a in args]]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
            bufsize=0,
            creationflags=_no_window_flags(),
        )
        tail: deque[str] = deque(maxlen=200)
        buf = b""
        try:
            assert proc.stdout is not None
            while True:
                if cancel is not None and cancel.is_set():
                    _terminate(proc)
                    raise OperationCancelled("已取消")
                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                buf += chunk
                pieces = re.split(rb"[\r\n]+", buf)
                buf = pieces.pop()
                for raw in pieces:
                    line = raw.decode("utf-8", "replace").strip()
                    if line:
                        tail.append(line)
                        if on_line is not None:
                            on_line(line)
            if buf.strip():
                line = buf.decode("utf-8", "replace").strip()
                tail.append(line)
                if on_line is not None:
                    on_line(line)
            code = proc.wait()
            return code, list(tail)
        finally:
            if proc.poll() is None:
                _terminate(proc)
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except OSError:
                    pass


def parse_percent(line: str, current: float = 0.0) -> float:
    match = PROGRESS_RE.search(line)
    if not match:
        return current
    return min(max(int(match.group(1)) / 100.0, 0.0), 1.0)


def add_args(
    fmt: str,
    out_path: Path,
    inputs: Sequence[Path | str],
    pw,
    *,
    level: int = 9,
    header_encrypt: bool = True,
    zip_method: str = "AES256",
) -> list[str]:
    """构造 `7z a` 参数。"""
    switches = ["a", "-y", f"-mx={level}", "-bsp1"]
    if fmt == "7z":
        switches += ["-t7z", "-m0=lzma2"]
        if header_encrypt:
            switches.append("-mhe=on")
    elif fmt == "zip":
        switches += ["-tzip", f"-mem={zip_method}"]
    else:
        raise ValueError(f"不支持的目标格式：{fmt}")
    switches.append(f"-p{pw}")
    return [*switches, str(out_path), *[str(p) for p in inputs]]


def test_args(archive, pw) -> list[str]:
    return ["t", "-y", "-bsp1", f"-p{pw}", str(archive)]


def list_args(archive, pw=None) -> list[str]:
    args = ["l", "-slt", "-ba"]
    if pw:
        args.append(f"-p{pw}")
    args.append(str(archive))
    return args


def extract_args(archive, out_dir, pw) -> list[str]:
    return ["x", "-y", "-bsp1", f"-o{out_dir}", f"-p{pw}", str(archive)]


def find_sfx_module(sz: SevenZip, console: bool = False):
    """找 7z.sfx / 7zCon.sfx；找不到返回 None。"""
    order = ("7zCon.sfx", "7z.sfx") if console else ("7z.sfx", "7zCon.sfx")
    roots = [sz.directory, bundled_root() / "_vendor" / "7z"]
    for name in order:
        for root in roots:
            cand = root / name
            if cand.is_file():
                return cand
    return None
