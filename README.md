# omarchy-fan-tray

FAN monitor for the Omarchy top tray (Hyprland + quickshell `omarchy.tray`, which shows StatusNotifier / AppIndicator items).

- **Blue `FAN` icon** — every fan from `sensors` is at or above the threshold.
- **Flashing red/yellow `FAN` icon + critical notification** — any fan is below the threshold, reads 0 RPM (e.g. fans not spinning back up after hibernate), or `sensors` gives no fan data.
- **RPM for every fan** — hover the icon for the tooltip, or right-click for the menu listing each fan.

Built for the case where hibernate/resume leaves fans stopped and the CPU overheats — one glance at the top bar tells you.

## How fan parsing works

Parses `sensors` output:

```
dell_smm-virtual-0
fan1:        1993 RPM
fan2:         683 RPM
...
```

- If `fanN:` lines exist, only those are used (this dedupes Dell machines where `dell_smm` and `dell_ddv` report the same physical fans twice).
- Otherwise any `*Fan*: N RPM` line is used (generic boards).
- A fan counts as failed when `RPM < threshold` (default **500**).

## Requirements (Omarchy / Arch)

```bash
sudo pacman -S python-gobject libayatana-appindicator lm_sensors libnotify
```

No pip packages needed at runtime — icons are pre-rendered PNGs in `icons/`.

If `sensors` shows no fans, run `sudo sensors-detect` and reboot.

## Run

```bash
./fan_tray.py --threshold 500 --interval 2
./fan_tray.py --once --verbose        # print status, no tray (for testing)
./fan_tray.py --threshold 99999       # force the red/fail path
```

Options: `--threshold RPM` (default 500), `--interval SEC` (default 2),
`--no-notify`, `--no-flash`, `--sensors-bin PATH`.

## Install (autostart on login)

```bash
./install.sh
```

This enables a systemd user service (`omarchy-fan-tray.service`) plus an
XDG autostart fallback (`~/.config/autostart/fan-tray.desktop`).

```bash
journalctl --user -u omarchy-fan-tray.service -f   # logs
systemctl --user restart omarchy-fan-tray.service  # after threshold change
```

To change the threshold permanently, edit the `ExecStart` line in
`~/.config/systemd/user/omarchy-fan-tray.service`, then restart.

## Pin the icon

The tray lives in the `omarchy.tray` drawer — hover the chevron to reveal it,
then right-click the tray → pin `omarchy-fan-tray` so the FAN icon is always visible.

## Files

| File | Purpose |
|---|---|
| `fan_tray.py` | Monitor (sensors parsing + AppIndicator tray) |
| `icons/fan-ok.png` | Blue FAN (healthy) |
| `icons/fan-fail.png` | Red FAN (failure frame 1) |
| `icons/fan-alert.png` | Yellow FAN (failure frame 2, flashing) |
| `omarchy-fan-tray.service` | systemd user unit template |
| `fan-tray.desktop` | XDG autostart template |
| `install.sh` | Installer |

## License

MIT — see `LICENSE`.
