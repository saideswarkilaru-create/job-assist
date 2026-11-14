"""Start Job Assist:  python run.py   (add --no-browser to skip opening the browser tab).

Serves the API and the built Angular UI at http://127.0.0.1:8770 (set JOBASSIST_PORT to change).
- If Job Assist is already running, it just opens the page.
- If requirements.txt changed (after an update), it installs the new libraries first.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

PORT = int(os.environ.get("JOBASSIST_PORT", "8770"))
URL = f"http://127.0.0.1:{PORT}"


def already_running() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/meta", timeout=2) as r:
            return "job_statuses" in json.loads(r.read().decode("utf-8"))
    except Exception:
        return False


def ensure_requirements() -> None:
    req = os.path.join(ROOT, "requirements.txt")
    stamp = os.path.join(ROOT, ".venv", "requirements.hash")
    with open(req, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest().upper()
    try:
        with open(stamp, encoding="utf-8-sig") as f:
            if f.read().strip().upper() == digest:
                return
    except FileNotFoundError:
        pass
    print("Updating app libraries, one moment...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", req])
    os.makedirs(os.path.dirname(stamp), exist_ok=True)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(digest)


def main() -> None:
    open_browser = "--no-browser" not in sys.argv
    if already_running():
        print(f"Job Assist is already running at {URL}")
        if open_browser:
            webbrowser.open(URL)
        return
    ensure_requirements()
    import uvicorn

    print(f"Job Assist is running at {URL}")
    print("Keep this window open while you use the app. Close it to stop.")
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(URL)).start()
    uvicorn.run("jobassist.api:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
