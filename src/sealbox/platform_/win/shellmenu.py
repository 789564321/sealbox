"""Windows 资源管理器右键菜单（HKCU，免管理员）。

注册三处入口：文件、文件夹、文件夹空白处；子菜单给出 7z / ZIP / 自解压 / 全部。
另在「发送到」放一个多选入口（资源管理器会把全部选中项一次性作为参数传入）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows
    winreg = None  # type: ignore[assignment]

ROOT = r"Software\Classes"
MENU_KEY = "SealBox.Menu"
VERBS = {
    "file": r"*\shell\SealBox",
    "dir": r"Directory\shell\SealBox",
    "background": r"Directory\Background\shell\SealBox",
}
ITEMS = (
    ("01-7z", "加密为 7z（推荐）", "--format 7z"),
    ("02-zip", "加密为 ZIP", "--format zip"),
    ("03-sfx", "生成自解压", "--format sfx"),
    ("04-all", "三种同时生成", "--format all"),
    ("05-extract", "解压 / 校验…", "--extract"),
)


def _require() -> None:
    if winreg is None or sys.platform != "win32":
        raise NotImplementedError("右键菜单仅支持 Windows。")


def launcher() -> list[str]:
    """启动命令前缀：打包后是 exe 本身；源码运行用 pythonw + 启动脚本。"""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        gui = exe.with_name("SealBox.exe")
        return [str(gui if gui.exists() else exe)]
    root = Path(__file__).resolve().parents[4]
    script = root / "sealbox_gui.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return [str(exe), str(script)]


def _quote(part: str) -> str:
    return f'"{part}"' if " " in part else part


def _command(extra: str, target: str) -> str:
    prefix = " ".join(_quote(part) for part in launcher())
    return f"{prefix} {extra} {target}"


def _full(key_path: str) -> str:
    return f"{ROOT}\\{key_path}"


def _set_values(key_path: str, values: dict[str, str]) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _delete_tree(key_path: str) -> bool:
    existed = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
            existed = True
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(key_path + "\\" + child)
    except FileNotFoundError:
        return False
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        return existed
    except OSError:
        return existed


def is_installed() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _full(VERBS["file"])):
            return True
    except OSError:
        return False


def _write_menu() -> None:
    icon = launcher()[0]
    for key_path in VERBS.values():
        _set_values(
            _full(key_path),
            {
                "MUIVerb": "SealBox 封印盒",
                "Icon": icon,
                "SubCommands": "",
                "ExtendedSubCommandsKey": MENU_KEY,
            },
        )

    for item_id, label, extra in ITEMS:
        targets = {
            "file": '"%1"',
            "dir": '"%1"',
            "background": '"%V"',
        }
        for kind, target in targets.items():
            key_path = f"{ROOT}\\{MENU_KEY}\\shell\\{item_id}-{kind}"
            _set_values(key_path, {"MUIVerb": label, "Icon": icon})
            _set_values(key_path + r"\command", {"": _command(extra, target)})


def _sendto_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "SendTo"


def _write_sendto() -> Path:
    """发送到入口：资源管理器会把全部选中项一次性作为参数传入。"""
    folder = _sendto_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "SealBox 加密.vbs"
    prefix = " ".join(_quote(part) for part in launcher())
    script = (
        "Option Explicit\n"
        "Dim sh, cmd, a\n"
        'Set sh = CreateObject("WScript.Shell")\n'
        f'cmd = "{prefix} --seal --gui"\n'
        "For Each a In WScript.Arguments\n"
        '  cmd = cmd & " " & Chr(34) & a & Chr(34)\n'
        "Next\n"
        "sh.Run cmd, 0, False\n"
    )
    target.write_text(script, encoding="utf-8")
    return target


def _remove_sendto() -> bool:
    target = _sendto_dir() / "SealBox 加密.vbs"
    try:
        if target.is_file():
            target.unlink()
            return True
    except OSError:
        pass
    return False


def install_menu() -> list[str]:
    _require()
    _write_menu()
    sendto = _write_sendto()
    return [
        "已注册右键菜单（仅当前用户，免管理员）：",
        "  文件 / 文件夹 / 文件夹空白处 → 「SealBox 封印盒」",
        f"  多选入口：{sendto}",
        "提示：资源管理器已打开时无需重启，直接右键即可看到。",
    ]


def uninstall_menu() -> list[str]:
    _require()
    removed = [kind for kind, key in VERBS.items() if _delete_tree(_full(key))]
    _delete_tree(f"{ROOT}\\{MENU_KEY}")
    _remove_sendto()
    if removed:
        return [f"已移除右键菜单（{len(removed)} 处入口）与发送到快捷方式。"]
    return ["没有找到已注册的右键菜单。"]


def status() -> dict:
    return {"installed": is_installed(), "launcher": launcher()}
