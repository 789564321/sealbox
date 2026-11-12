"""命令行入口。

默认（带路径且未指定 --cli/--json）会打开窗口并预置任务 —— 这样把文件
拖到 exe / 快捷方式上时，系统传入的路径会直接变成待处理任务。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import APP_DISPLAY, __version__
from .core import job, manifest, password, verifier
from .core.sevenzip import SevenZip, SevenZipNotFound, find_sevenzip, find_sfx_module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sealbox",
        description=f"{APP_DISPLAY}：用一次性 UUID 密码加密文件，产出加密包与密码 TXT。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  sealbox 报告.docx 资料/           打开窗口并预置这些输入\n"
            "  sealbox --seal --cli 报告.docx    直接命令行加密为 ZIP（默认）\n"
            "  sealbox --seal --cli --format zip,sfx 资料/\n"
            "  sealbox --extract --cli 备份.7z --pwd <密码>\n"
            "  sealbox --install-menu           注册右键菜单\n"
        ),
    )
    parser.add_argument("paths", nargs="*", help="文件 / 文件夹 / 压缩包")
    parser.add_argument("--seal", action="store_true", help="加密模式")
    parser.add_argument("--extract", action="store_true", help="解压模式")
    parser.add_argument("--verify", action="store_true", help="仅校验归档")
    parser.add_argument("--format", default="zip", help="7z / zip / sfx，逗号分隔；all = 三种")
    parser.add_argument("--out", help="输出目录")
    parser.add_argument("--name", help="输出文件名（不含扩展名）")
    parser.add_argument("--pwd", help="指定密码；省略则自动生成")
    parser.add_argument(
        "--pwd-file",
        default="auto",
        help="auto（默认，写 <名称>.密码.txt）/ none（不写）/ 自定义路径",
    )
    parser.add_argument("--pwd-style", default="short22", choices=list(password.STYLES))
    parser.add_argument("--sfx-target", default="auto", choices=("auto", "windows", "unix"))
    parser.add_argument("--sfx-console", action="store_true", help="Windows 自解压用控制台版")
    parser.add_argument("--level", type=int, default=9, help="压缩级别 0-9，默认 9")
    parser.add_argument("--no-verify", action="store_true", help="跳过生成后校验")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖同名文件")
    parser.add_argument("--verbose", action="store_true", help="输出 7z 原始日志")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出（隐含 --cli）")
    parser.add_argument("--cli", action="store_true", help="无窗口命令行模式")
    parser.add_argument("--gui", action="store_true", help="强制打开窗口（默认行为）")
    parser.add_argument("--install-menu", action="store_true", help="注册文件/文件夹右键菜单")
    parser.add_argument("--uninstall-menu", action="store_true", help="移除右键菜单")
    parser.add_argument(
        "--autostart",
        choices=("enable", "disable", "status"),
        help="开机自启动：enable / disable / status",
    )
    parser.add_argument("--tray", action="store_true", help="启动后只驻留系统托盘，不显示主窗口")
    parser.add_argument("--check", action="store_true", help="检查环境")
    parser.add_argument("--version", action="version", version=f"{APP_DISPLAY} {__version__}")
    return parser


def _parse_formats(spec: str) -> tuple[str, ...]:
    text = (spec or "zip").strip().lower()
    if text == "all":
        return job.FORMATS
    formats: list[str] = []
    for part in text.replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        if item not in job.FORMATS:
            raise ValueError(f"未知格式：{item}（可选 7z / zip / sfx / all）")
        if item not in formats:
            formats.append(item)
    return tuple(formats) or ("zip",)


def _action(args: argparse.Namespace) -> str:
    if args.extract:
        return "extract"
    if args.verify:
        return "verify"
    if args.seal:
        return "seal"
    return "auto"


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        return _check()
    if args.autostart:
        return _autostart(args.autostart)
    if args.install_menu:
        return _menu(install=True)
    if args.uninstall_menu:
        return _menu(install=False)

    paths = [str(p) for p in args.paths]
    wants_gui = args.gui or (not args.cli and not args.json)

    if wants_gui:
        try:
            from .gui.app import run_gui
        except Exception as exc:  # Qt 缺失时退化为命令行
            print(f"无法启动窗口（{exc}），改用命令行。", file=sys.stderr)
        else:
            return run_gui(
                paths=paths,
                action=_action(args),
                formats=_safe_formats(args.format),
                out_dir=args.out,
                pwd_style=args.pwd_style,
                pwd_text=args.pwd,
                tray_only=args.tray,
            )

    if not paths:
        parser.print_help()
        return 1
    if args.extract:
        return _cli_extract(args, paths)
    if args.verify:
        return _cli_verify(args, paths)
    return _cli_seal(args, paths)


def _safe_formats(spec: str) -> tuple[str, ...]:
    try:
        return _parse_formats(spec)
    except ValueError:
        return ("zip",)


def _cli_seal(args: argparse.Namespace, paths: list[str]) -> int:
    try:
        formats = _parse_formats(args.format)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    options = job.JobOptions(
        formats=formats,
        output_dir=Path(args.out).expanduser() if args.out else None,
        base_name=args.name,
        pwd_style=args.pwd_style,
        write_pwd_file=args.pwd_file != "none",
        verify=not args.no_verify,
        level=max(0, min(9, args.level)),
        sfx_target=args.sfx_target,
        sfx_console=args.sfx_console,
        overwrite=args.overwrite,
    )
    task = job.plan_task([Path(p) for p in paths], options)
    task.pw_text = args.pwd

    last = {"stage": ""}

    def on_progress(frac: float, stage: str) -> None:
        if stage != last["stage"]:
            last["stage"] = stage
            print(f"[{frac * 100:5.1f}%] {stage}", flush=True)

    cb = job.Callbacks(
        progress=None if args.json else on_progress,
        log=(lambda line: print(f"    {line}")) if (args.verbose and not args.json) else None,
    )

    try:
        sz = SevenZip(find_sevenzip())
    except SevenZipNotFound as exc:
        print(exc, file=sys.stderr)
        return 2

    job.execute_task(task, sz=sz, cb=cb)

    if args.pwd_file not in ("auto", "none") and task.pwd_file is not None:
        target = Path(args.pwd_file).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task.pwd_file), str(target))
        task.pwd_file = target

    if args.json:
        print(json.dumps({"ok": task.state == job.STATE_DONE, "task": task.to_dict()},
                         ensure_ascii=False, indent=2))
    else:
        if task.state == job.STATE_DONE:
            print(f"\n完成：{len(task.outputs)} 个加密包")
            for out in task.outputs:
                print(f"  加密包：{out}")
            if task.pwd_file:
                print(f"  密码TXT：{task.pwd_file}")
            print(f"  密码：{task.pw_text}")
        else:
            print(f"\n失败：{task.error}", file=sys.stderr)
    return 0 if task.state == job.STATE_DONE else 3


def _resolve_pw(args: argparse.Namespace, archive: Path) -> str | None:
    if args.pwd is not None:
        return args.pwd
    found = manifest.find_sibling_pw_file(archive)
    if found is not None:
        value = manifest.read_pw_file(found)
        if value:
            print(f"已从 {found.name} 读取密码。")
            return value
    return None


def _cli_extract(args: argparse.Namespace, paths: list[str]) -> int:
    archive = Path(paths[0]).expanduser().resolve()
    if not archive.is_file():
        print(f"不是文件：{archive}", file=sys.stderr)
        return 1
    pw = _resolve_pw(args, archive)
    if not pw:
        print("缺少密码：用 --pwd 指定，或把 <名称>.密码.txt 放在归档旁。", file=sys.stderr)
        return 1
    out_dir = Path(args.out).expanduser() if args.out else archive.parent / archive.stem
    try:
        sz = SevenZip(find_sevenzip())
    except SevenZipNotFound as exc:
        print(exc, file=sys.stderr)
        return 2
    ok, hint = verifier.extract_archive(sz, archive, out_dir, pw)
    if args.json:
        print(json.dumps({"ok": ok, "hint": hint, "out": str(out_dir)}, ensure_ascii=False))
    else:
        print(("解压完成：" if ok else "解压失败：") + str(out_dir if ok else hint))
    return 0 if ok else 4


def _cli_verify(args: argparse.Namespace, paths: list[str]) -> int:
    archive = Path(paths[0]).expanduser().resolve()
    pw = _resolve_pw(args, archive)
    if not pw:
        print("缺少密码：用 --pwd 指定，或把 <名称>.密码.txt 放在归档旁。", file=sys.stderr)
        return 1
    try:
        sz = SevenZip(find_sevenzip())
    except SevenZipNotFound as exc:
        print(exc, file=sys.stderr)
        return 2
    ok, hint = verifier.test_archive(sz, archive, pw)
    if args.json:
        print(json.dumps({"ok": ok, "hint": hint}, ensure_ascii=False))
    else:
        print(("校验通过：" if ok else "校验失败：") + (str(archive) if ok else hint))
    return 0 if ok else 4


def _check() -> int:
    print(f"{APP_DISPLAY} {__version__}")
    print(f"平台：{sys.platform}")
    print(f"Python：{sys.version.split()[0]}")
    try:
        sz = SevenZip(find_sevenzip())
    except SevenZipNotFound as exc:
        print(f"7-Zip：不可用（{exc}）")
        return 2
    print(f"7-Zip：{sz.version()} → {sz.exe}")
    sfx_module = find_sfx_module(sz)
    print(f"自解压模块：{sfx_module if sfx_module else '未找到（.exe 自解压不可用）'}")
    try:
        import PySide6  # noqa: F401

        print(f"Qt：PySide6 {PySide6.__version__}")
    except Exception:
        print("Qt：未安装（只能用 --cli）")
    return 0


def _autostart(action: str) -> int:
    try:
        from .platform_ import autostart
    except Exception as exc:
        print(f"当前平台不支持：{exc}", file=sys.stderr)
        return 1
    try:
        if action == "status":
            state = autostart.status()
            print("已启用" if state["enabled"] else "未启用")
            print(f"命令：{state['command']}")
            return 0
        messages = autostart.enable() if action == "enable" else autostart.disable()
    except Exception as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1
    for line in messages:
        print(line)
    return 0


def _menu(install: bool) -> int:
    try:
        from .platform_ import backend

        mod = backend()
        if install:
            messages = mod.install_menu()
        else:
            messages = mod.uninstall_menu()
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1
    for line in messages:
        print(line)
    return 0
