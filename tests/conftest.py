import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """A fresh, fully migrated database in a temp folder (never touches data/)."""
    from jobassist import db, paths

    monkeypatch.setattr(paths, "DATA", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "test.db")
    for name in ("CLAUDE_WORKDIR", "RESUMES", "TAILORED", "BROWSER_PROFILE", "LOGS", "ADAPTERS", "CONFIG"):
        monkeypatch.setattr(paths, name, tmp_path / name.lower())
    db.init_db()
    c = db.connect()
    yield c
    c.close()


@pytest.fixture
def fake_keyring():
    """In-memory keyring so tests never write to the real Windows Credential Manager."""
    import keyring
    from keyring.backend import KeyringBackend

    class Memory(KeyringBackend):
        priority = 1
        store: dict = {}

        def set_password(self, service, username, password):
            self.store[(service, username)] = password

        def get_password(self, service, username):
            return self.store.get((service, username))

        def delete_password(self, service, username):
            self.store.pop((service, username), None)

    old = keyring.get_keyring()
    mem = Memory()
    mem.store = {}
    keyring.set_keyring(mem)
    yield mem
    keyring.set_keyring(old)
