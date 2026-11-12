"""macOS 右键入口（实验性，待实机验证）。

macOS 没有注册表式右键菜单，这里用 Finder 的「快速操作」(Quick Action)
实现：在 ~/Library/Services 下放一个 .workflow，内部执行 SealBox 启动器。

注意：需要用户在「系统设置 → 键盘 → 服务 / 快速操作」中勾选一次。
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

SERVICE_NAME = "SealBox 加密"


def _services_dir() -> Path:
    return Path.home() / "Library" / "Services"


def _launcher_shell() -> str:
    import shlex

    from ..win.shellmenu import launcher  # 复用同一套启动器解析

    parts = launcher()
    if getattr(sys, "frozen", False):
        return shlex.join(parts)
    return shlex.join(parts)


def _workflow_dir() -> Path:
    return _services_dir() / f"{SERVICE_NAME}.workflow"


def _document_plist(command: str) -> bytes:
    """生成一个最小可用的 Automator「运行 Shell 脚本」工作流。"""
    action = {
        "action": {
            "AMAccepts": {
                "Container": "List",
                "Optional": True,
                "Types": ["com.apple.cocoa.string"],
            },
            "AMActionVersion": "2.0.3",
            "AMParameterProperties": {},
            "AMProvides": {
                "Container": "List",
                "Types": ["com.apple.cocoa.string"],
            },
            "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
            "ActionName": "Run Shell Script",
            "ActionParameters": {
                "COMMAND_STRING": command,
                "CheckedForUserDefaultShell": True,
                "inputMethod": 1,
                "shell": "/bin/bash",
                "source": "",
            },
            "BundleIdentifier": "com.apple.RunShellScript",
            "CFBundleVersion": "2.0.3",
            "CanShowSelectedItemsWhenRun": False,
            "CanShowWhenRun": True,
            "Category": ["AMCategoryUtilities"],
            "Class Name": "RunShellScriptAction",
            "InputUUID": "6E7A0B3A-2C4F-4F7B-9C3E-9F1A2B3C4D5E",
            "OutputUUID": "7F8B1C4B-3D5A-4A8C-8D4F-0A2B3C4D5E6F",
            "UUID": "8A9C2D5C-4E6B-4B9D-9E5A-1B3C4D5E6F70",
            "UnlocalizedApplications": ["com.apple.finder"],
            "isViewVisible": True,
        }
    }
    document = {
        "AMApplicationBuild": "521",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [action],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDs": ["com.apple.finder"],
            "applicationNames": [],
            "applicationTypes": ["com.apple.finder"],
            "inputTypeIdentifier": "com.apple.cocoa.string",
            "outputTypeIdentifier": "com.apple.cocoa.string",
            "presentationMode": 1,
            "processInput": 1,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceInputTypeIdentifier": "com.apple.cocoa.string",
            "serviceOutputTypeIdentifier": "com.apple.cocoa.string",
            "serviceProcessInput": 1,
            "serviceUseSelectedFiles": 1,
            "useSelectedFiles": 1,
        },
    }
    return plistlib.dumps(document)


def install_menu() -> list[str]:
    if sys.platform != "darwin":
        raise NotImplementedError("Quick Action 仅支持 macOS。")
    workflow = _workflow_dir()
    contents = workflow / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    command = f'"{_launcher_shell()}" --seal --gui "$@"'
    with open(contents / "document.wflow", "wb") as fh:
        fh.write(_document_plist(command))
    info = {
        "CFBundleIdentifier": "local.sealbox.quickaction",
        "CFBundleName": SERVICE_NAME,
        "CFBundlePackageType": "BNDL",
    }
    with open(contents / "Info.plist", "wb") as fh:
        plistlib.dump(info, fh)
    _refresh_services()
    return [
        f"已安装快速操作：{workflow}",
        "首次使用前，请在「系统设置 → 键盘 → 服务 / 快速操作」中勾选。",
        "Finder 中选中文件/文件夹 → 右键 → 快速操作 → SealBox 加密。",
        "说明：macOS 部分尚未在实机验证，如不生效请按 README 手动创建。",
    ]


def uninstall_menu() -> list[str]:
    workflow = _workflow_dir()
    if workflow.is_dir():
        shutil.rmtree(workflow, ignore_errors=True)
        _refresh_services()
        return [f"已移除快速操作：{workflow}"]
    return ["没有找到已安装的快速操作。"]


def _refresh_services() -> None:
    try:
        subprocess.run(["killall", "Finder"], capture_output=True, timeout=10)
    except Exception:
        pass


def status() -> dict:
    return {"installed": _workflow_dir().is_dir(), "path": str(_workflow_dir())}
