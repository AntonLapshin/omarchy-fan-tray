#!/usr/bin/env python3
"""Omarchy fan tray monitor.

Shows a "fan" text icon in the top tray (Omarchy StatusNotifier tray):
  - GRAY text  -> all fans >= threshold (healthy, matches tray icon tone)
  - RED/YELLOW flashing text -> any fan below threshold / stopped / unreadable

RPM for every fan (parsed from `sensors`) is shown in the tooltip and the
right-click menu. A critical desktop notification fires on OK -> FAIL
transitions (e.g. after hibernate when fans don't spin back up).

Usage:
    python3 fan_tray.py [--threshold 500] [--interval 2]
    python3 fan_tray.py --once --verbose   # print status, no tray (for testing)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

APP_ID = "omarchy-fan-tray"
APP_TITLE = "Fan Monitor"

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_OK = os.path.join(HERE, "icons", "fan-ok.png")
ICON_FAIL = os.path.join(HERE, "icons", "fan-fail.png")
ICON_ALERT = os.path.join(HERE, "icons", "fan-alert.png")

# Theme-installed names (preferred: resolves reliably in the quickshell
# SystemTray; absolute file paths are the fallback).
THEME_DIR = os.path.expanduser("~/.local/share/icons/hicolor/64x64/apps")
THEME_BASE = os.path.expanduser("~/.local/share/icons")
THEME_NAMES = {
    "ok": "omarchy-fan-tray-ok",
    "fail": "omarchy-fan-tray-fail",
    "alert": "omarchy-fan-tray-alert",
}
THEME_FILES = {
    "ok": ("fan-ok.png", "omarchy-fan-tray-ok.png"),
    "fail": ("fan-fail.png", "omarchy-fan-tray-fail.png"),
    "alert": ("fan-alert.png", "omarchy-fan-tray-alert.png"),
}


def ensure_theme_icons() -> dict[str, str]:
    """Copy icons into the hicolor theme so the tray resolves them by name.

    Returns {state: icon_ref} where icon_ref is a theme name on success,
    else the absolute PNG path fallback.
    """
    refs = {"ok": ICON_OK, "fail": ICON_FAIL, "alert": ICON_ALERT}
    try:
        os.makedirs(THEME_DIR, exist_ok=True)
        import shutil as _shutil

        for state, (src_name, dst_name) in THEME_FILES.items():
            src = os.path.join(HERE, "icons", src_name)
            dst = os.path.join(THEME_DIR, dst_name)
            if os.path.exists(src) and (
                not os.path.exists(dst)
                or os.path.getsize(src) != os.path.getsize(dst)
            ):
                _shutil.copyfile(src, dst)
        # all three present -> use theme names
        if all(
            os.path.exists(os.path.join(THEME_DIR, dst))
            for _, dst in THEME_FILES.values()
        ):
            return {s: THEME_NAMES[s] for s in THEME_NAMES}
    except Exception:
        pass
    return refs

# Matches `sensors` fan lines, e.g.:
#   fan1:        1993 RPM
#   CPU Fan:                 1993 RPM
FAN_N_RE = re.compile(r"^\s*(fan\d+)\s*:\s*(\d+)\s*RPM", re.IGNORECASE)
ANY_FAN_RE = re.compile(r"^\s*(.+?fan.*?)\s*:\s*(\d+)\s*RPM", re.IGNORECASE)


def run_sensors(sensors_bin: str = "sensors") -> str:
    """Run `sensors` and return stdout. Raises on failure."""
    out = subprocess.run(
        [sensors_bin], capture_output=True, text=True, timeout=10
    )
    if out.returncode != 0:
        raise RuntimeError(f"sensors exited {out.returncode}: {out.stderr.strip()}")
    return out.stdout


def parse_fans(text: str) -> list[tuple[str, int]]:
    """Parse fan name -> RPM from `sensors` output.

    Prefers `fanN:` lines (dedupes Dell machines where dell_smm and
    dell_ddv report the same physical fans twice). Falls back to any
    `*Fan*: N RPM` line on machines without `fanN` labels.
    """
    numbered: list[tuple[str, int]] = []
    for line in text.splitlines():
        m = FAN_N_RE.match(line)
        if m:
            numbered.append((m.group(1).strip(), int(m.group(2))))
    if numbered:
        # de-dupe repeated labels, keep first occurrence, stable order
        seen: set[str] = set()
        uniq: list[tuple[str, int]] = []
        for name, rpm in numbered:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                uniq.append((name, rpm))
        return uniq

    generic: list[tuple[str, int]] = []
    for line in text.splitlines():
        m = ANY_FAN_RE.match(line)
        if m:
            generic.append((m.group(1).strip(), int(m.group(2))))
    return generic


def check_fans(fans: list[tuple[str, int]], threshold: int) -> list[tuple[str, int]]:
    """Return the subset of fans below threshold (failed/stopped)."""
    return [(name, rpm) for name, rpm in fans if rpm < threshold]


def status_line(
    fans: list[tuple[str, int]], failed: list[tuple[str, int]], threshold: int
) -> str:
    if not fans:
        return "FAN ? — no fans found in `sensors` output"
    if failed:
        bad = ", ".join(f"{n}: {r} RPM" for n, r in failed)
        return f"FAN FAIL (<{threshold} RPM: {bad})"
    detail = ", ".join(f"{n}: {r} RPM" for n, r in fans)
    return f"FAN OK — {detail}"


def tooltip_text(
    fans: list[tuple[str, int]], failed: list[tuple[str, int]], threshold: int
) -> str:
    if not fans:
        return "Fan Monitor\nNo fans found — is `sensors` configured?\n(run `sudo sensors-detect`)"
    header = (
        f"FAN FAIL — {len(failed)}/{len(fans)} below {threshold} RPM"
        if failed
        else f"FAN OK — {len(fans)}/{len(fans)} >= {threshold} RPM"
    )
    lines = [header] + [f"{n}: {r} RPM" for n, r in fans]
    return "\n".join(lines)


def send_notification(summary: str, body: str) -> None:
    """Best-effort critical notification (async, never raises)."""
    try:
        subprocess.Popen(
            ["notify-send", "-u", "critical", "-a", APP_TITLE, summary, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def poll_once(threshold: int, sensors_bin: str, verbose: bool = False):
    """Single poll used by --once and by the tray loop."""
    try:
        text = run_sensors(sensors_bin)
    except Exception as exc:  # sensors missing / failing counts as unknown->failed
        if verbose:
            print(f"sensors error: {exc}", file=sys.stderr)
        return [], [], f"sensors error: {exc}"
    fans = parse_fans(text)
    failed = check_fans(fans, threshold)
    if verbose:
        print(status_line(fans, failed, threshold))
        for name, rpm in fans:
            mark = "FAIL" if rpm < threshold else "ok"
            print(f"  {name}: {rpm} RPM [{mark}]")
    return fans, failed, None


# ---------------------------------------------------------------- tray (Gtk) --
def run_tray(args) -> int:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
    from gi.repository import Gtk, GLib

    state = {
        "fans": [],
        "failed": [],
        "was_failing": False,
        "flash_on": False,
        "error": None,
    }

    icons = ensure_theme_icons()

    indicator = AppIndicator.Indicator.new(
        APP_ID, icons["ok"], AppIndicator.IndicatorCategory.HARDWARE
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    indicator.set_title(APP_TITLE)
    try:
        # Lets the shell resolve the icon names above via the hicolor theme.
        indicator.set_icon_theme_path(THEME_BASE)
    except Exception:
        pass

    menu = Gtk.Menu()

    def rebuild_menu():
        for child in menu.get_children():
            menu.remove(child)
        if state["error"]:
            item = Gtk.MenuItem(label=f"sensors error: {state['error']}")
            item.set_sensitive(False)
            menu.append(item)
        elif not state["fans"]:
            item = Gtk.MenuItem(label="No fans found in `sensors` output")
            item.set_sensitive(False)
            menu.append(item)
        else:
            for name, rpm in state["fans"]:
                ok = rpm >= args.threshold
                item = Gtk.MenuItem(
                    label=f"{name}: {rpm} RPM  {'✓' if ok else '✗ FAIL'}"
                )
                item.set_sensitive(False)
                menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        info = Gtk.MenuItem(
            label=f"Threshold: {args.threshold} RPM   Interval: {args.interval}s"
        )
        info.set_sensitive(False)
        menu.append(info)
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()

    def apply_state():
        fans, failed, error = state["fans"], state["failed"], state["error"]
        if error or not fans:
            icon = icons["fail"] if state["flash_on"] else icons["alert"]
            indicator.set_icon_full(icon, "no fan data")
        elif failed:
            icon = icons["fail"] if state["flash_on"] else icons["alert"]
            indicator.set_icon_full(icon, "fan failure")
        else:
            indicator.set_icon_full(icons["ok"], "fans ok")
        try:
            tip = tooltip_text(fans, failed, args.threshold)
            # Title feeds the StatusNotifier tooltip shown by omarchy.tray.
            indicator.set_title(f"{APP_TITLE}\n{tip}")
            # Label is shown by panels that support it (harmless if ignored).
            if fans and not failed:
                lo = min(r for _, r in fans)
                indicator.set_label(f"{lo} RPM", "")
            elif failed:
                indicator.set_label("FAN FAIL", "")
            else:
                indicator.set_label("FAN ?", "")
        except Exception:
            pass
        rebuild_menu()

    def refresh() -> bool:
        fans, failed, error = [], [], None
        try:
            text = run_sensors(args.sensors_bin)
            fans = parse_fans(text)
            failed = check_fans(fans, args.threshold)
        except Exception as exc:
            error = str(exc)[:160]
            failed = [("sensors", -1)]
        state.update(fans=fans, failed=failed, error=error)
        failing = bool(error or not fans or failed)
        if failing and not state["was_failing"] and not args.no_notify:
            if error:
                send_notification(
                    "Fan Monitor: no fan data",
                    f"Could not read fans ({error}). Check `sensors`.",
                )
            elif not fans:
                send_notification(
                    "Fan Monitor: no fans found",
                    "No fan lines in `sensors` output. Run `sudo sensors-detect`.",
                )
            else:
                bad = ", ".join(f"{n} {r} RPM" for n, r in failed)
                send_notification(
                    "Fan Monitor: FAN FAILURE",
                    f"{len(failed)} fan(s) below {args.threshold} RPM: {bad}",
                )
        state["was_failing"] = failing
        if args.verbose:
            print(status_line(fans, failed, args.threshold), flush=True)
        apply_state()
        return True  # keep GLib timeout alive

    def flash() -> bool:
        # Blink red/yellow while failing so a stopped fan is unmissable.
        if state["was_failing"] and not args.no_flash:
            state["flash_on"] = not state["flash_on"]
            apply_state()
        elif state["flash_on"]:
            state["flash_on"] = False
            apply_state()
        return True

    indicator.set_menu(menu)
    refresh()
    GLib.timeout_add_seconds(max(1, args.interval), refresh)
    GLib.timeout_add(500, flash)
    Gtk.main()
    return 0


def acquire_single_instance_lock():
    """Exit quietly if another tray instance is already running.

    Prevents duplicate tray icons when more than one launcher fires
    (e.g. systemd service + XDG autostart). Uses an abstract-free lock
    file; the FD is kept open for the process lifetime.
    Returns the lock file object, or None if already locked.
    """
    import fcntl

    os.makedirs(os.path.expanduser("~/.cache"), exist_ok=True)
    lock_path = os.path.expanduser("~/.cache/omarchy-fan-tray.lock")
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="'fan' tray monitor: gray when all fans OK, flashing red/yellow when any fan is below threshold."
    )
    p.add_argument("--threshold", type=int, default=500,
                   help="RPM below which a fan counts as failed (default: 500)")
    p.add_argument("--interval", type=int, default=2,
                   help="poll interval in seconds (default: 2)")
    p.add_argument("--sensors-bin", default="sensors",
                   help="path to sensors binary (default: sensors)")
    p.add_argument("--no-notify", action="store_true",
                   help="disable critical desktop notifications")
    p.add_argument("--no-flash", action="store_true",
                   help="disable red/yellow flashing, use steady red on failure")
    p.add_argument("--once", action="store_true",
                   help="print one status line and exit (no tray icon)")
    p.add_argument("--verbose", action="store_true", help="print each poll to stdout")
    args = p.parse_args(argv)

    if shutil.which(args.sensors_bin) is None and not args.once:
        print(
            f"error: `{args.sensors_bin}` not found. Install lm_sensors.",
            file=sys.stderr,
        )
        return 2

    if args.once:
        fans, failed, error = poll_once(args.threshold, args.sensors_bin, verbose=True)
        if error or not fans or failed:
            return 1
        return 0

    for icon in (ICON_OK, ICON_FAIL, ICON_ALERT):
        if not os.path.exists(icon):
            print(f"error: missing icon {icon}", file=sys.stderr)
            return 2
    lock = acquire_single_instance_lock()
    if lock is None:
        print("another fan_tray instance is already running, exiting", file=sys.stderr)
        return 0
    return run_tray(args)


if __name__ == "__main__":
    raise SystemExit(main())
