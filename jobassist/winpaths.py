"""Full paths to built-in Windows tools.

Some PCs have a damaged PATH (other installers edited it), so calling "powershell" or "schtasks" by
name fails with "not recognized". Windows always keeps these tools in fixed folders, so use those.
"""
from __future__ import annotations

import os
import shutil

_ROOT = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"


def system32(name: str) -> str:
    """Full path of a System32 tool (falls back to the bare name if it isn't there)."""
    p = os.path.join(_ROOT, "System32", name)
    return p if os.path.exists(p) else (shutil.which(name) or name)


def powershell() -> str:
    """Windows PowerShell 5.1, else PowerShell 7 (pwsh)."""
    p = os.path.join(_ROOT, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.exists(p):
        return p
    return shutil.which("powershell") or shutil.which("pwsh") or "powershell"
