#!/usr/bin/env python3
"""Start/stop clock for a legal-description run.

Replaces the old `date -u ... > /tmp/legal_desc_start.txt` shell idiom, which
only worked on a POSIX shell. Python is already a hard dependency of this
plugin, so using it here costs nothing and works identically on Windows,
macOS, and Linux.

The timestamp is written to the OS temp directory and never leaves this
machine.

Usage:
    python run_clock.py start
    python run_clock.py end
"""
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(tempfile.gettempdir()) / "ma_registry_legal_desc_run.json"


def _now():
    return datetime.now(timezone.utc), time.time()


def start():
    dt, epoch = _now()
    iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    STATE.write_text(json.dumps({"start_iso": iso, "start_epoch": epoch}),
                     encoding="utf-8")
    print(f"Start: {iso} ({epoch:.0f})")
    print(f"State: {STATE}")


def end():
    dt, epoch = _now()
    iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not STATE.exists():
        print(f"End:   {iso} ({epoch:.0f})")
        print("NOTE: no start file found — run `run_clock.py start` first. "
              "Elapsed time unavailable.")
        return
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        start_iso = data["start_iso"]
        elapsed_min = (epoch - float(data["start_epoch"])) / 60.0
    except (ValueError, KeyError) as e:
        print(f"End:   {iso} ({epoch:.0f})")
        print(f"NOTE: start file unreadable ({e}). Elapsed time unavailable.")
        return
    print(f"Start:   {start_iso}")
    print(f"End:     {iso}")
    print(f"Elapsed: {elapsed_min:.1f} minutes")


if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if cmd == "start":
        start()
    elif cmd == "end":
        end()
    else:
        print(__doc__)
        sys.exit(2)
