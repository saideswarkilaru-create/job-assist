"""Call Claude through the headless CLI (`claude -p`), so no API key is needed.

The prompt goes in on stdin, tools are disabled, and the call runs in an empty folder so no
project files or CLAUDE.md are pulled into context.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from . import paths


class ClaudeError(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("claude") is not None


def ask(prompt: str, *, model: str = "haiku", timeout: int = 240) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeError("Claude CLI not found. Install Claude Code and make sure `claude` works in a terminal.")
    paths.ensure_dirs()
    cmd = [exe, "-p", "--output-format", "json", "--model", model, "--tools", "", "--no-session-persistence"]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout, cwd=str(paths.CLAUDE_WORKDIR),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"Claude did not answer within {timeout}s") from e
    if proc.returncode != 0:
        raise ClaudeError((proc.stderr or proc.stdout or "unknown error").strip()[:500])
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.stdout.strip()
    if envelope.get("is_error"):
        raise ClaudeError(str(envelope.get("result"))[:500])
    return str(envelope.get("result", "")).strip()


def ask_json(prompt: str, **kw) -> dict:
    text = ask(prompt, **kw)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ClaudeError(f"Expected JSON, got: {text[:300]}")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ClaudeError(f"Could not parse Claude's JSON: {e}") from e
