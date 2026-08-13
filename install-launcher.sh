#!/bin/bash
# Generates traffic-monitor.desktop with an absolute path to this checkout,
# and installs it into the XFCE application menu.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

sed "s|__INSTALL_DIR__|$DIR|" "$DIR/traffic-monitor.desktop.template" > "$DIR/traffic-monitor.desktop"
chmod +x "$DIR/traffic-monitor.desktop" "$DIR/run.sh"

mkdir -p ~/.local/share/applications
cp "$DIR/traffic-monitor.desktop" ~/.local/share/applications/traffic-monitor.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo "Launcher installed. Find \"Network Traffic Monitor\" in your application menu,"
echo "or double-click $DIR/traffic-monitor.desktop in Thunar."
