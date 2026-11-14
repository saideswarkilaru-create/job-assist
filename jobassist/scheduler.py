"""Daily run through Windows Task Scheduler (a normal per-user task, no admin rights).

The task runs scheduled_run.py with pythonw (no console window) at the chosen time, only while you are
signed in (the browser must be visible for captchas / logins). If the laptop was asleep or off at that
time, it runs as soon as possible afterwards. Turn it off any time from Settings.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from . import paths, winpaths

TASK_NAME = "JobAssist Daily Search"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return w if w.exists() else exe


def _script() -> Path:
    return paths.ROOT / "scheduled_run.py"


def manual_command(time: str) -> str:
    """The exact command, to paste into PowerShell or Command Prompt yourself if you prefer."""
    return (f'schtasks /Create /F /SC DAILY /ST {time} /TN "{TASK_NAME}" '
            f'/TR "\\"{_pythonw()}\\" \\"{_script()}\\""')


def task_xml(time: str) -> str:
    hh, mm = time.split(":")
    start = f"{date.today().isoformat()}T{int(hh):02d}:{int(mm):02d}:00"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Job Assist: search all enabled profiles once a day.</Description></RegistrationInfo>
  <Triggers><CalendarTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled>
    <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(str(_pythonw()))}</Command>
    <Arguments>"{escape(str(_script()))}"</Arguments><WorkingDirectory>{escape(str(paths.ROOT))}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _schtasks(*args) -> subprocess.CompletedProcess:
    return subprocess.run([winpaths.system32("schtasks.exe"), *args], capture_output=True, text=True, timeout=30,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def enable(time: str, name: str = TASK_NAME) -> None:
    if sys.platform != "win32":
        raise RuntimeError("The daily schedule uses Windows Task Scheduler.")
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(task_xml(time))
        xml_path = f.name
    try:
        r = _schtasks("/Create", "/F", "/TN", name, "/XML", xml_path)
    finally:
        Path(xml_path).unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or "Task Scheduler refused the task.")


def disable(name: str = TASK_NAME) -> None:
    r = _schtasks("/Delete", "/F", "/TN", name)
    if r.returncode != 0 and "cannot find" not in (r.stderr + r.stdout).lower():
        raise RuntimeError((r.stderr or r.stdout).strip())


def status(name: str = TASK_NAME) -> dict:
    if sys.platform != "win32":
        return {"enabled": False, "supported": False}
    r = _schtasks("/Query", "/TN", name, "/FO", "LIST", "/V")
    if r.returncode != 0:
        return {"enabled": False, "supported": True}
    info = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition(":")
        info[k.strip().lower()] = v.strip()
    return {"enabled": True, "supported": True, "next_run": info.get("next run time", ""),
            "last_run": info.get("last run time", ""), "last_result": info.get("last result", ""),
            "state": info.get("status", "")}


def valid_time(t: str) -> bool:
    return bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t or ""))
