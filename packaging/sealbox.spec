# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包描述：目录版（onedir）GUI + CLI，内置 7-Zip。

产物：
    dist/SealBox/        GUI（SealBox.exe + _internal/）
    dist/SealBoxCLI/     CLI（SealBoxCLI.exe + _internal/）
    dist/SealBox.app     macOS 由 BUNDLE 生成
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821

datas = []
vendor = ROOT / "_vendor" / "7z"
if vendor.is_dir():
    datas.append((str(vendor), "_vendor/7z"))

icon_path = ROOT / "packaging" / "sealbox.ico"
icon = str(icon_path) if icon_path.exists() else None

a = Analysis(
    [str(ROOT / "sealbox_gui.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "test"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SealBox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll_gui = COLLECT(
    exe_gui,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SealBox",
)

exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SealBoxCLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll_cli = COLLECT(
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SealBoxCLI",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll_gui,
        name="SealBox.app",
        icon=icon,
        bundle_identifier="local.sealbox.app",
        info_plist={
            "CFBundleName": "SealBox",
            "CFBundleDisplayName": "SealBox 封印盒",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
