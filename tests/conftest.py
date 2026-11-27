"""专项红测共享夹具：临时库 + 登录。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

import db as dbmod  # noqa: E402
from app import app  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """每个用例独立临时库，避免污染 data/app.db。"""
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(dbmod, "DATA", tmp_path)
    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    dbmod.init_db()
    yield db_path


@pytest.fixture()
def client(fresh_db):
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin_h(client):
    return _login(client, "admin", "admin123")


@pytest.fixture()
def writer_h(client):
    return _login(client, "writer", "writer123")
