"""Windows desktop notifications (toasts) with no extra installs.

Uses the Windows notification API through PowerShell. Clicking the notification opens the app page
given in `url`. Fails silently (returns False) on non-Windows or if notifications are turned off.
"""
from __future__ import annotations

import os
import subprocess
import sys
from xml.sax.saxutils import escape

APP_URL = f"http://127.0.0.1:{os.environ.get('JOBASSIST_PORT', '8770')}"
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_PS = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
       "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
       "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:JA_TOAST);"
       "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
       f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_APP_ID}').Show($t)")


def toast_xml(title: str, body: str, url: str | None = None) -> str:
    quoted = escape(url or "", {'"': "&quot;"})
    launch = f' activationType="protocol" launch="{quoted}"' if url else ""
    return (f"<toast{launch}><visual><binding template=\"ToastGeneric\">"
            f"<text>{escape(title)}</text><text>{escape(body)}</text></binding></visual></toast>")


def toast(title: str, body: str, path: str = "/today") -> bool:
    if sys.platform != "win32":
        return False
    env = {**os.environ, "JA_TOAST": toast_xml(title, body, APP_URL + path)}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", _PS],
                           env=env, capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False
