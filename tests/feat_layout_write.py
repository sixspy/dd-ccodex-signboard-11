"""专项红测：室外屏正式上屏须绑定布局（写路径口径）。

甲路径：缺布局整笔拒写发布正式行。
乙路径：缺布局只许影子草案，正式零改，待绑布局升正。
两边不得混用；非室外分区不得被本专项误伤。
"""
from __future__ import annotations

import json
from pathlib import Path

from db import connect

ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = json.loads((ROOT / "fixtures" / "outdoor_layout_attempts.json").read_text(encoding="utf-8"))

OUTDOOR_SCREEN = "scr_yard_e1"
LAYOUT_CODE = "lay_split"
PLAYLIST_CODE = "pl_lift_loop"
WINDOW_CODE = "win_workday"


def _catalog(client, h):
    screens = {s["code"]: s for s in client.get("/api/screens", headers=h).json()["items"]}
    layouts = {x["code"]: x for x in client.get("/api/layouts", headers=h).json()["items"]}
    playlists = {p["code"]: p for p in client.get("/api/playlists", headers=h).json()["items"]}
    windows = {w["code"]: w for w in client.get("/api/windows", headers=h).json()["items"]}
    return screens, layouts, playlists, windows


def _prepare_outdoor(client, h):
    screens, layouts, playlists, windows = _catalog(client, h)
    yard = screens[OUTDOOR_SCREEN]
    if yard["status"] != "online":
        r = client.patch(f"/api/screens/{yard['id']}", headers=h, json={"status": "online"})
        assert r.status_code == 200, r.text
    return yard, layouts[LAYOUT_CODE], playlists[PLAYLIST_CODE], windows[WINDOW_CODE]


def _official_rows(screen_id):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE screen_id=? AND official=1", (screen_id,)
        ).fetchall()


def _shadow_rows():
    with connect() as conn:
        return conn.execute("SELECT * FROM publish_shadows ORDER BY id").fetchall()


def _history_count(action):
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) c FROM change_history WHERE action=?", (action,)
        ).fetchone()["c"]


def _payload(screen, playlist, window, **extra):
    body = {
        "screen_id": screen["id"],
        "playlist_id": playlist["id"],
        "window_id": window["id"],
        "summary": "室外立柱发布",
    }
    body.update(extra)
    return body


def test_attempt_fixture_heads_with_outdoor_no_layout():
    """夹具复现「室外屏无布局发布尝试」打头。"""
    first = ATTEMPTS[0]
    assert first["case"] == "室外屏无布局发布尝试"
    assert first["zone_type"] == "outdoor"
    assert first["layout_code"] is None
    assert first["expect"]["official_rows_delta"] == 0
    assert first["expect"]["shadow_allowed"] is True
    assert first["expect"]["promote_allowed"] is False


def test_official_outdoor_without_layout_is_whole_rejection(client, admin_h):
    """失败测甲：无布局仍插入正式发布。"""
    yard, layout, playlist, window = _prepare_outdoor(client, admin_h)
    history_before = _history_count("publish_official")
    r = client.post(
        "/api/publish/official", headers=admin_h, json=_payload(yard, playlist, window)
    )
    assert r.status_code == 409, r.text
    assert "布局" in r.json()["detail"]
    assert _official_rows(yard["id"]) == [], "缺布局不得落地任何正式发布行"
    assert _shadow_rows() == [], "甲路径不得改走影子草案（两边不得混用）"
    assert _history_count("publish_official") == history_before, "整笔拒写不得留升版历史"


def test_official_outdoor_with_unknown_layout_rejected(client, admin_h):
    yard, layout, playlist, window = _prepare_outdoor(client, admin_h)
    r = client.post(
        "/api/publish/official",
        headers=admin_h,
        json=_payload(yard, playlist, window, layout_id=99999),
    )
    assert r.status_code in (404, 409), r.text
    assert _official_rows(yard["id"]) == []


def test_official_outdoor_with_layout_lands_same_source(client, admin_h):
    """绑定后发布与布局同源：正式行的 layout_id 必须就是本次联查校验的那条布局。"""
    yard, layout, playlist, window = _prepare_outdoor(client, admin_h)
    r = client.post(
        "/api/publish/official",
        headers=admin_h,
        json=_payload(yard, playlist, window, layout_id=layout["id"]),
    )
    assert r.status_code == 200, r.text
    rows = _official_rows(yard["id"])
    assert len(rows) == 1
    assert rows[0]["layout_id"] == layout["id"]
    assert rows[0]["version"] == 1
    assert _shadow_rows() == [], "甲路径不得顺带写影子（两边不得混用）"

    listed = client.get("/api/publish/official", headers=admin_h).json()["items"]
    mine = next(x for x in listed if x["screen_id"] == yard["id"])
    assert mine["layout_code"] == LAYOUT_CODE
    assert mine["zone_type"] == "outdoor"


def test_shadow_outdoor_without_layout_only_draft_then_promote_after_bind(client, admin_h):
    """失败测乙（写路径侧）：缺布局只许影子草案，正式零改待绑布局升正。"""
    yard, layout, playlist, window = _prepare_outdoor(client, admin_h)
    sh = client.post(
        "/api/publish/shadow", headers=admin_h, json=_payload(yard, playlist, window)
    )
    assert sh.status_code == 200, sh.text
    sid = sh.json()["id"]
    assert sh.json()["status"] == "open"
    assert _official_rows(yard["id"]) == [], "影子草案阶段正式区必须零改"

    blocked = client.post(f"/api/publish/shadow/{sid}/promote", headers=admin_h, json={})
    assert blocked.status_code == 409, blocked.text
    assert _official_rows(yard["id"]) == [], "缺布局升正必须整笔拒写"
    with connect() as conn:
        status = conn.execute(
            "SELECT status FROM publish_shadows WHERE id=?", (sid,)
        ).fetchone()["status"]
    assert status == "open", "被拒升正的影子须保持待升正"

    bound = client.patch(
        f"/api/publish/shadow/{sid}/layout",
        headers=admin_h,
        json={"layout_id": layout["id"]},
    )
    assert bound.status_code == 200, bound.text

    promoted = client.post(f"/api/publish/shadow/{sid}/promote", headers=admin_h, json={})
    assert promoted.status_code == 200, promoted.text
    rows = _official_rows(yard["id"])
    assert len(rows) == 1
    assert rows[0]["layout_id"] == layout["id"], "升正后的正式行须与影子绑定布局同源"


def test_non_outdoor_without_layout_still_publishes(client, admin_h):
    """本专项只管室外：非室外分区缺布局不得被误伤。"""
    screens, layouts, playlists, windows = _catalog(client, admin_h)
    side = screens["scr_lobby_side"]
    r = client.post(
        "/api/publish/official",
        headers=admin_h,
        json=_payload(side, playlists[PLAYLIST_CODE], windows[WINDOW_CODE]),
    )
    assert r.status_code == 200, r.text
    rows = _official_rows(side["id"])
    assert len(rows) == 1
    assert rows[0]["layout_id"] is None
