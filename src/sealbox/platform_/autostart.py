"""开机自启动（登录自启）。

* Windows：HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
* macOS：~/Library/LaunchAgents/local.sealbox.agent.plist
* Linux：~/.config/autostart/sealbox.desktop

自启时以 --tray 参数静默驻留托盘，不弹主窗口。
"""

from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SealBox"


def launcher_parts() -> list[str]:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        gui = exe.with_name("SealBox.exe")
        return [str(gui if gui.exists() else exe)]
    root = Path(__file__).resolve().parents[3]
    script = root / "sealbox_gui.py"
    if sys.platform == "win32":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            return [str(pythonw), str(script)]
    return [sys.executable, str(script)]


def _command(tray: bool = True) -> str:
    parts = [f'"{part}"' if " " in part else part for part in launcher_parts()]
    if tray:
        parts.append("--tray")
    return " ".join(parts)


def _winreg():
    import winreg

    return winreg


def is_enabled() -> bool:
    if sys.platform == "win32":
        winreg = _winreg()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
                winreg.QueryValueEx(key, VALUE_NAME)
                return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _plist_path().is_file()
    return _desktop_path().is_file()


def enable() -> list[str]:
    if sys.platform == "win32":
        winreg = _winreg()
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
        return ["已启用开机自启动（登录后静默驻留托盘）。", f"命令：{_command()}"]

    if sys.platform == "darwin":
        path = _plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": "local.sealbox.agent",
            "ProgramArguments": [*launcher_parts(), "--tray"],
            "RunAtLoad": True,
            "ProcessType": "Interactive",
            "StandardOutPath": str(Path.home() / "Library" / "Logs" / "sealbox.log"),
            "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "sealbox.log"),
        }
        with open(path, "wb") as fh:
            plistlib.dump(payload, fh)
        return [f"已创建 LaunchAgent：{path}", "下次登录时生效。如需立即生效：launchctl load -w " + str(path)]

    path = _desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=SealBox\n"
        "Comment=一次性 UUID 密码加密文件\n"
        f"Exec={_command()}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n"
    )
    path.write_text(content, encoding="utf-8")
    return [f"已创建自启动项：{path}"]


def disable() -> list[str]:
    if sys.platform == "win32":
        winreg = _winreg()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
            return ["已关闭开机自启动。"]
        except OSError:
            return ["开机自启动本来就没有开启。"]
    if sys.platform == "darwin":
        path = _plist_path()
    else:
        path = _desktop_path()
    if path.is_file():
        path.unlink()
        return [f"已删除自启动项：{path}"]
    return ["开机自启动本来就没有开启。"]


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "local.sealbox.agent.plist"


def _desktop_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "sealbox.desktop"


def status() -> dict:
    return {"enabled": is_enabled(), "command": _command(), "platform": sys.platform}
