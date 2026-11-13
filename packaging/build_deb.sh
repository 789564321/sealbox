#!/usr/bin/env bash
# 构建 Linux 安装包（.deb）：在 Linux 本机或 CI 上执行
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="0.1.0"
ARCH="amd64"
PKG="dist/deb/sealbox_${VERSION}_${ARCH}"

if [ ! -x "dist/SealBox/SealBox" ]; then
  echo "未找到 dist/SealBox/SealBox，请先运行 python3 packaging/build.py" >&2
  exit 1
fi

rm -rf dist/deb
mkdir -p "$PKG/DEBIAN" \
         "$PKG/usr/lib/sealbox" \
         "$PKG/usr/bin" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps" \
         "$PKG/usr/share/doc/sealbox"

cp -R dist/SealBox "$PKG/usr/lib/sealbox/"
cp -R dist/SealBoxCLI "$PKG/usr/lib/sealbox/"
cp packaging/sealbox-256.png "$PKG/usr/share/icons/hicolor/256x256/apps/sealbox.png"
cp README.md LICENSE "$PKG/usr/share/doc/sealbox/"

cat > "$PKG/usr/bin/sealbox" <<'EOF'
#!/bin/sh
exec "/usr/lib/sealbox/SealBox/SealBox" "$@"
EOF
chmod 0755 "$PKG/usr/bin/sealbox"

cat > "$PKG/usr/share/applications/sealbox.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=SealBox
Comment=一次性 UUID 密码加密文件
Exec=/usr/bin/sealbox %F
Icon=sealbox
Terminal=false
Categories=Utility;Security;
MimeType=application/zip;application/x-7z-compressed;
EOF

cat > "$PKG/DEBIAN/control" <<EOF
Package: sealbox
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: SealBox <noreply@example.com>
Installed-Size: $(du -sk "$PKG" | cut -f1)
Depends: libegl1, libgl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libdbus-1-3
Description: SealBox 封印盒
 用一次性 UUID 密码把文件/文件夹加密成 ZIP / 7z / 自解压程序，
 同时生成密码 TXT。
EOF

dpkg-deb --build --root-owner-group "$PKG" "dist/sealbox_${VERSION}_${ARCH}.deb"
echo "DEB: dist/sealbox_${VERSION}_${ARCH}.deb"
sha256sum "dist/sealbox_${VERSION}_${ARCH}.deb"
