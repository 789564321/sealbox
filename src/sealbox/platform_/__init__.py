"""平台适配入口：按当前系统返回对应的右键菜单实现。"""

from __future__ import annotations

import sys


def backend():
    if sys.platform == "win32":
        from .win import shellmenu

        return shellmenu
    if sys.platform == "darwin":
        from .mac import services

        return services
    from .linux import filemanager

    return filemanager
