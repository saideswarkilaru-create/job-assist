"""Run by Windows Task Scheduler once a day (Settings > Daily schedule). Can also be run by hand:
    .venv\\Scripts\\python.exe scheduled_run.py

Searches all enabled profiles (then scores and tailors as usual) and shows a desktop notification.
Also starts the app in the background (if it isn't running) so clicking the notification opens it.
"""
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def _app_running(port: str) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=2)
        return True
    except Exception:
        return False


def main() -> int:
    from jobassist import runner

    port = os.environ.get("JOBASSIST_PORT", "8770")
    if not _app_running(port):
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        subprocess.Popen([exe if os.path.exists(exe) else sys.executable, os.path.join(ROOT, "run.py"), "--no-browser"],
                         cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                         getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
    return runner.main(["search", "--trigger", "schedule"])


if __name__ == "__main__":
    sys.exit(main())
