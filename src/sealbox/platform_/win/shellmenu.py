"""Windows 资源管理器右键菜单（HKCU，免管理员）。

采用**单层动词**：右键 →「SealBox 加密 / 解压…」→ 打开窗口并预置路径。
不再使用级联子菜单，因此：

* Windows 10 / 11 行为一致（级联菜单在部分 Win10 版本上不显示）；
* 不会出现"每个选项重复三份"（旧实现把 file/dir/background 三套命令
  塞进同一个 ExtendedSubCommandsKey，Windows 会把 15 项全部列出）。
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # 非 Windows
    winreg = None  # type: ignore[assignment]

ROOT = r"Software\Classes"
MENU_TEXT = "SealBox 加密 / 解压…"
SENDTO_NAME = "SealBox 加密.vbs"

VERBS = {
    "file": r"*\shell\SealBox",
    "dir": r"Directory\shell\SealBox",
    "background": r"Directory\Background\shell\SealBox",
}

# 旧版本（级联菜单）留下的键，安装/卸载时全部清掉。
LEGACY = (
    r"*\shell\SealBox",
    r"Directory\shell\SealBox",
    r"Directory\Background\shell\SealBox",
    r"AllFilesystemObjects\shell\SealBox",
    r"Folder\shell\SealBox",
    r"Drive\shell\SealBox",
    r"SealBox.Menu",
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


def _command(target: str) -> str:
    prefix = " ".join(_quote(part) for part in launcher())
    return f"{prefix} --gui {target}"


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


def _notify_shell() -> None:
    """通知资源管理器刷新关联，避免 Win10 需要重启。"""
    try:
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        SHCNF_FLUSH = 0x1000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSH, None, None
        )
    except Exception:
        pass


def is_installed() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _full(VERBS["file"])):
            return True
    except OSError:
        return False


def _sendto_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "SendTo"


def _write_sendto() -> Path:
    """发送到入口：资源管理器会把全部选中项一次性作为参数传入。"""
    folder = _sendto_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / SENDTO_NAME
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
    target = _sendto_dir() / SENDTO_NAME
    try:
        if target.is_file():
            target.unlink()
            return True
    except OSError:
        pass
    return False


def install_menu() -> list[str]:
    _require()
    # 先清掉旧结构（含级联菜单的 15 个重复项）
    for key in LEGACY:
        _delete_tree(_full(key))
    icon = launcher()[0]
    targets = {"file": '"%1"', "dir": '"%1"', "background": '"%V"'}
    for kind, key_path in VERBS.items():
        _set_values(_full(key_path), {"MUIVerb": MENU_TEXT, "Icon": icon})
        _set_values(_full(key_path) + r"\command", {"": _command(targets[kind])})
    sendto = _write_sendto()
    _notify_shell()
    return [
        "已注册右键菜单（仅当前用户，免管理员）：",
        "  文件 / 文件夹 / 文件夹空白处 → 「SealBox 加密 / 解压…」",
        f"  多选入口：{sendto}",
        "已通知资源管理器刷新；若仍未显示，注销后重新登录即可。",
    ]


def uninstall_menu() -> list[str]:
    _require()
    removed = [key for key in LEGACY if _delete_tree(_full(key))]
    _remove_sendto()
    _notify_shell()
    if removed:
        return [f"已移除右键菜单（{len(removed)} 个键）与发送到快捷方式。"]
    return ["没有找到已注册的右键菜单。"]


def status() -> dict:
    info: dict[str, object] = {"installed": is_installed(), "launcher": launcher()}
    keys: dict[str, object] = {}
    for kind, key_path in VERBS.items():
        value = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _full(key_path)) as key:
                value = winreg.QueryValueEx(key, "MUIVerb")[0]
        except OSError:
            value = None
        keys[kind] = value
    info["keys"] = keys
    info["sendto"] = str(_sendto_dir() / SENDTO_NAME)
    return info


def doctor() -> list[str]:
    """给 Win10/11 排障用的自检输出。"""
    _require()
    lines = ["SealBox 右键菜单自检："]
    exe = Path(launcher()[0])
    lines.append(f"  启动器：{exe}（存在：{exe.exists()}）")
    for kind, key_path in VERBS.items():
        full = _full(key_path)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, full) as key:
                verb = winreg.QueryValueEx(key, "MUIVerb")[0]
            command = ""
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, full + r"\command") as ckey:
                    command = winreg.QueryValueEx(ckey, "")[0]
            except OSError:
                command = "（缺少 command）"
            lines.append(f"  [{kind}] 已注册：{verb}")
            lines.append(f"        {command}")
        except OSError:
            lines.append(f"  [{kind}] 未注册：{full}")
    sendto = _sendto_dir() / SENDTO_NAME
    lines.append(f"  发送到：{sendto}（存在：{sendto.is_file()}）")
    lines.append("  提示：若 Win10 未显示，执行 --uninstall-menu 再 --install-menu，或重启资源管理器。")
    return lines
