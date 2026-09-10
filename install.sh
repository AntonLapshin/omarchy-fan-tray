#!/usr/bin/env bash
# Install the fan tray monitor on Omarchy (Hyprland + quickshell tray).
# Installs: system deps, autostart entry, systemd user service.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_SRC="$REPO_DIR/omarchy-fan-tray.service"
SERVICE_DST="$HOME/.config/systemd/user/omarchy-fan-tray.service"
DESKTOP_SRC="$REPO_DIR/fan-tray.desktop"
AUTOSTART_DST="$HOME/.config/autostart/fan-tray.desktop"

echo "==> Checking dependencies (python3, gi, AyatanaAppIndicator3, sensors)..."
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import Gtk, AyatanaAppIndicator3; print('tray libs OK')"
command -v sensors >/dev/null || { echo "missing 'sensors' — install lm_sensors: sudo pacman -S lm_sensors"; exit 1; }
command -v notify-send >/dev/null || echo "warning: notify-send not found, notifications disabled"

chmod +x "$REPO_DIR/fan_tray.py"

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
# Rewrite ExecStart to this checkout location (service file ships with %h default).
sed "s|%h/ws/omarchy-fan-tray|$REPO_DIR|" "$SERVICE_SRC" > "$SERVICE_DST.tmp"
mv "$SERVICE_DST.tmp" "$SERVICE_DST"
systemctl --user daemon-reload
systemctl --user enable --now omarchy-fan-tray.service
systemctl --user status omarchy-fan-tray.service --no-pager -l | head -n 15 || true

echo "==> Installing XDG autostart fallback..."
mkdir -p "$HOME/.config/autostart"
sed "s|/home/aurora/ws/omarchy-fan-tray|$REPO_DIR|" "$DESKTOP_SRC" > "$AUTOSTART_DST"

echo ""
echo "Done. A blue FAN icon should appear in the top tray (hover for RPMs)."
echo "Test failure path with: $REPO_DIR/fan_tray.py --threshold 99999 --interval 2"
echo "Logs: journalctl --user -u omarchy-fan-tray.service -f"
