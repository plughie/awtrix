"""Register (or unregister) an autostart task that starts the visualizer
at user login.

Supports macOS (launchd) and Windows (Task Scheduler).

Usage:
    python install_autostart.py              # install the autostart entry
    python install_autostart.py --remove     # remove it
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

TASK_NAME = "AwtrixMusicVisualizer"
LAUNCHD_LABEL = "com.awtrix.music-visualizer"
PROJECT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# macOS — launchd
# ---------------------------------------------------------------------------

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _install_macos() -> int:
    # Prefer the project venv if it exists, otherwise fall back to sys.executable
    venv_python = PROJECT_DIR / ".venv" / "bin" / "python3"
    python = str(venv_python) if venv_python.exists() else sys.executable
    config = str(PROJECT_DIR / "config.toml")
    plist_path = _launchd_plist_path()

    plist = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [python, "-m", "visualizer", "--config", config],
        "WorkingDirectory": str(PROJECT_DIR),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(PROJECT_DIR / "visualizer.log"),
        "StandardErrorPath": str(PROJECT_DIR / "visualizer.log"),
    }

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    # Load the agent (unload first in case it already exists)
    subprocess.run(["launchctl", "unload", str(plist_path)],
                   capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist_path)],
                            capture_output=True, text=True)

    if result.returncode == 0:
        print(f"LaunchAgent '{LAUNCHD_LABEL}' installed.")
        print(f"  The visualizer will start on login.")
        print(f"  To run now:   launchctl start {LAUNCHD_LABEL}")
        print(f"  To stop:      launchctl stop {LAUNCHD_LABEL}")
        print(f"  To remove:    python install_autostart.py --remove")
        print(f"  Plist:        {plist_path}")
        print(f"  Log:          {PROJECT_DIR / 'visualizer.log'}")
    else:
        print("Failed to load agent:", result.stderr.strip(), file=sys.stderr)
        return 1
    return 0


def _remove_macos() -> int:
    plist_path = _launchd_plist_path()
    if not plist_path.exists():
        print(f"LaunchAgent '{LAUNCHD_LABEL}' is not installed.")
        return 1

    subprocess.run(["launchctl", "unload", str(plist_path)],
                   capture_output=True)
    plist_path.unlink()
    print(f"LaunchAgent '{LAUNCHD_LABEL}' removed.")
    return 0


# ---------------------------------------------------------------------------
# Windows — Task Scheduler
# ---------------------------------------------------------------------------

def _install_windows() -> int:
    python = sys.executable
    config = PROJECT_DIR / "config.toml"

    xml = f"""\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Hidden>true</Hidden>
    <AllowStartOnDemand>true</AllowStartOnDemand>
  </Settings>
  <Actions>
    <Exec>
      <Command>{python}</Command>
      <Arguments>-m visualizer --config "{config}"</Arguments>
      <WorkingDirectory>{PROJECT_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    xml_path = PROJECT_DIR / "_task.xml"
    xml_path.write_text(xml, encoding="utf-16")

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
        capture_output=True,
        text=True,
    )
    xml_path.unlink()

    if result.returncode == 0:
        print(f"Task '{TASK_NAME}' created. The visualizer will start on login.")
        print(f"  To run now:   schtasks /Run /TN {TASK_NAME}")
        print(f"  To stop:      schtasks /End /TN {TASK_NAME}")
        print(f"  To remove:    python install_autostart.py --remove")
    else:
        print("Failed to create task:", result.stderr.strip(), file=sys.stderr)
        return 1
    return 0


def _remove_windows() -> int:
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"Task '{TASK_NAME}' removed.")
    else:
        print("Failed to remove task:", result.stderr.strip(), file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def install() -> int:
    if sys.platform == "darwin":
        return _install_macos()
    elif sys.platform == "win32":
        return _install_windows()
    else:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        return 1


def remove() -> int:
    if sys.platform == "darwin":
        return _remove_macos()
    elif sys.platform == "win32":
        return _remove_windows()
    else:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Install/remove autostart task")
    parser.add_argument("--remove", action="store_true", help="remove the task")
    args = parser.parse_args()
    raise SystemExit(remove() if args.remove else install())


if __name__ == "__main__":
    main()
