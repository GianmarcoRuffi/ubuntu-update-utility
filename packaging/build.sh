#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/DEBIAN" "$stage/usr/lib/ubuntu-update-utility" "$stage/usr/share/applications"
cp packaging/helper "$stage/usr/lib/ubuntu-update-utility/helper"
chmod 755 "$stage/usr/lib/ubuntu-update-utility/helper"
mkdir -p "$stage/usr/share/polkit-1/actions"
cp packaging/it.local.UbuntuUpdateUtility.policy "$stage/usr/share/polkit-1/actions/"
cp ubuntu_update/*.py "$stage/usr/lib/ubuntu-update-utility/"
cat > "$stage/DEBIAN/control" <<EOF
Package: ubuntu-update-utility
Version: 0.3.0
Architecture: all
Maintainer: Local User <local@localhost>
Depends: python3 (>= 3.12), apt, snapd, flatpak, fwupd, ubuntu-drivers-common, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pkexec
Description: Utility grafica conservativa per aggiornamenti Ubuntu
EOF
cat > "$stage/usr/share/applications/ubuntu-update-utility.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Ubuntu Update Utility
Exec=/usr/bin/python3 /usr/lib/ubuntu-update-utility/app.py
Icon=system-software-update
Terminal=false
Categories=System;
EOF
mkdir -p "$stage/usr/share/doc/ubuntu-update-utility"
cp README.md "$stage/usr/share/doc/ubuntu-update-utility/"
mkdir -p dist
dpkg-deb --root-owner-group --build "$stage" dist/ubuntu-update-utility_0.3.0_all.deb
