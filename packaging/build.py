"""跨平台构建脚本：准备内置 7-Zip、生成图标、调用 PyInstaller。

产物（目录版，启动无需解包）：
    dist/SealBox/       GUI 目录（SealBox.exe + _internal/）
    dist/SealBoxCLI/    CLI 目录
    dist/SealBox.app    macOS（BUNDLE 生成，ad-hoc 签名）
    dist/SealBox-<平台>.zip  便携压缩包

用法（PyInstaller 不能交叉编译，需在各平台本机执行）：
    python packaging/build.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "_vendor" / "7z"
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"


def _copy_if_missing(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file():
        shutil.copy2(src, dest)
    return True


def prepare_vendor() -> None:
    """把当前平台的 7-Zip 可执行文件放进 vendor，打包后离线可用。"""
    VENDOR.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        base = Path(r"C:\Program Files\7-Zip")
        if not base.is_dir():
            base = Path(r"C:\Program Files (x86)\7-Zip")
        names = ("7z.exe", "7z.dll", "7z.sfx", "7zCon.sfx", "License.txt")
        copied = [name for name in names if _copy_if_missing(base / name, VENDOR / name)]
        if "7z.exe" not in copied and not (VENDOR / "7z.exe").is_file():
            print("警告：没找到 7-Zip，产物将依赖目标机器已安装的 7-Zip。")
        else:
            print(f"内置 7-Zip：{VENDOR}")
        return

    if sys.platform == "darwin":
        candidates = [
            shutil.which("7zz"),
            shutil.which("7z"),
            "/opt/homebrew/bin/7zz",
            "/usr/local/bin/7zz",
        ]
    else:
        candidates = [
            shutil.which("7zz"),
            shutil.which("7z"),
            shutil.which("7za"),
            "/usr/bin/7zz",
            "/usr/bin/7z",
        ]
    for item in candidates:
        if item and Path(item).is_file():
            _copy_if_missing(Path(item), VENDOR / "7zz")
            print(f"内置 7-Zip：{item} -> {VENDOR / '7zz'}")
            return
    print("警告：没找到 7zz/7z，产物将依赖目标机器已安装的 7-Zip。")


def prepare_notice() -> None:
    src = ROOT / "packaging" / "7zip-NOTICE.txt"
    if src.is_file():
        VENDOR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, VENDOR / "NOTICE.txt")


def make_icon() -> None:
    sys.path.insert(0, str(ROOT / "packaging"))
    import make_icon as icon_tool

    icon_tool.main()


def run_pyinstaller() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORK),
        str(ROOT / "packaging" / "sealbox.spec"),
    ]
    print("运行：", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))


def finalize_macos() -> Path | None:
    app = DIST / "SealBox.app"
    if not app.is_dir():
        return None
    if shutil.which("codesign"):
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app)],
            check=False,
        )
    # .app 里已包含完整运行目录，删掉重复的裸目录
    shutil.rmtree(DIST / "SealBox", ignore_errors=True)
    return app


def platform_label() -> str:
    if sys.platform == "win32":
        return "win64"
    if sys.platform == "darwin":
        return "macos"
    return "linux-x64"


def make_zip() -> Path | None:
    targets = [
        item
        for item in ("SealBox", "SealBoxCLI", "SealBox.app")
        if (DIST / item).exists()
    ]
    if not targets:
        return None
    archive = DIST / f"SealBox-{platform_label()}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name in targets:
            base = DIST / name
            if base.is_file():
                zf.write(base, name)
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(DIST))
    return archive


def summary() -> None:
    print("\n构建产物：")
    for item in sorted(DIST.iterdir()):
        if item.is_dir():
            size = sum(p.stat().st_size for p in item.rglob("*") if p.is_file())
        else:
            size = item.stat().st_size
        print(f"  {item.name:28s} {size / 1024 / 1024:8.1f} MB")


def main() -> int:
    print(f"平台：{sys.platform}")
    prepare_vendor()
    prepare_notice()
    make_icon()
    run_pyinstaller()
    if sys.platform == "darwin":
        app = finalize_macos()
        if app:
            print(f"已生成 {app}")
    archive = make_zip()
    if archive:
        print(f"便携包：{archive}")
    summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
