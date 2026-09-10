#!/usr/bin/env bash
# Install the fan tray monitor on Omarchy (Hyprland + quickshell tray).
# Single autostart mechanism: systemd user service (the app itself also
# refuses to run twice via a lock file, so duplicates are impossible).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_SRC="$REPO_DIR/omarchy-fan-tray.service"
SERVICE_DST="$HOME/.config/systemd/user/omarchy-fan-tray.service"
AUTOSTART_DST="$HOME/.config/autostart/fan-tray.desktop"

echo "==> Checking dependencies (python3, gi, AyatanaAppIndicator3, sensors)..."
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import Gtk, AyatanaAppIndicator3; print('tray libs OK')"
command -v sensors >/dev/null || { echo "missing 'sensors' — install lm_sensors: sudo pacman -S lm_sensors"; exit 1; }
command -v notify-send >/dev/null || echo "warning: notify-send not found, notifications disabled"

chmod +x "$REPO_DIR/fan_tray.py"

echo "==> Installing icons into hicolor theme..."
THEME_DIR="$HOME/.local/share/icons/hicolor/64x64/apps"
mkdir -p "$THEME_DIR"
cp -f "$REPO_DIR/icons/fan-ok.png" "$THEME_DIR/omarchy-fan-ok.png"
cp -f "$REPO_DIR/icons/fan-fail.png" "$THEME_DIR/omarchy-fan-fail.png"
cp -f "$REPO_DIR/icons/fan-alert.png" "$THEME_DIR/omarchy-fan-alert.png"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
# Rewrite ExecStart to this checkout location (service file ships with %h default).
sed "s|%h/ws/omarchy-fan-tray|$REPO_DIR|" "$SERVICE_SRC" > "$SERVICE_DST.tmp"
mv "$SERVICE_DST.tmp" "$SERVICE_DST"
systemctl --user daemon-reload
systemctl --user enable --now omarchy-fan-tray.service
systemctl --user status omarchy-fan-tray.service --no-pager -l | head -n 15 || true

echo "==> Removing legacy XDG autostart entry (systemd is the only launcher now)..."
rm -f "$AUTOSTART_DST"

echo "==> Pinning FAN icon so it is always visible (not in the hover drawer)..."
python3 - <<'PY' || echo "warning: could not pin tray item — right-click the tray chevron and pin omarchy-fan-tray manually"
import json
p = "$HOME/.config/omarchy/shell.json".replace("$HOME", __import__("os").environ["HOME"])
d = json.load(open(p))
for e in d["bar"]["layout"]["right"]:
    if isinstance(e, dict) and e.get("id") == "omarchy.tray":
        e["pinned"] = ["omarchy-fan-tray"]
json.dump(d, open(p, "w"), indent=2)
print("tray pinned")
PY

echo ""
echo "Done. A gray 'fan' label should appear in the top tray (hover for RPMs)."
echo "Test failure path with: $REPO_DIR/fan_tray.py --threshold 99999 --interval 2"
echo "Logs: journalctl --user -u omarchy-fan-tray.service -f"
