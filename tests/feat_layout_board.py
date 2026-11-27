"""专项红测：布局页与发布册脱节、多区画布缺失、总览齐套口径（旁路口径）。

总览不得把「室外正式发布但未绑布局」刷成齐套；布局页须给出版式槽位与占用；
发布册须露出布局绑定与分区类型。
"""
from __future__ import annotations

from db import connect

OUTDOOR_SCREEN = "scr_yard_e1"
LAYOUT_CODE = "lay_split"
PLAYLIST_CODE = "pl_lift_loop"
WINDOW_CODE = "win_workday"


def _ids(client, h):
    screens = {s["code"]: s for s in client.get("/api/screens", headers=h).json()["items"]}
    layouts = {x["code"]: x for x in client.get("/api/layouts", headers=h).json()["items"]}
    playlists = {p["code"]: p for p in client.get("/api/playlists", headers=h).json()["items"]}
    windows = {w["code"]: w for w in client.get("/api/windows", headers=h).json()["items"]}
    return screens, layouts, playlists, windows


def _seed_rogue_outdoor_publication(client, h):
    """模拟历史脏账：室外屏已有正式发布行但 layout_id 为空。"""
    screens, _layouts, playlists, windows = _ids(client, h)
    yard = screens[OUTDOOR_SCREEN]
    with connect() as conn:
        conn.execute(
            "INSERT INTO publications(screen_id,playlist_id,window_id,layout_id,version,summary,status,official,published_at,published_by) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                yard["id"],
                playlists[PLAYLIST_CODE]["id"],
                windows[WINDOW_CODE]["id"],
                None,
                1,
                "历史无布局室外发布",
                "published",
                1,
                0.0,
                "legacy",
            ),
        )
        conn.commit()
    return yard


def test_dashboard_does_not_paint_unbound_outdoor_as_ready(client, admin_h):
    """失败测乙：总览把无布局室外发布刷成齐套。"""
    _seed_rogue_outdoor_publication(client, admin_h)
    d = client.get("/api/dashboard", headers=admin_h).json()
    assert d["outdoor_unbound_publications"] == 1
    assert d["outdoor_publications"] >= 1
    assert d["outdoor_layout_ready"] is False, "室外缺布局不得被总览判为齐套"


def test_dashboard_ready_after_outdoor_publish_with_layout(client, admin_h):
    screens, layouts, playlists, windows = _ids(client, admin_h)
    yard = screens[OUTDOOR_SCREEN]
    client.patch(f"/api/screens/{yard['id']}", headers=admin_h, json={"status": "online"})
    r = client.post(
        "/api/publish/official",
        headers=admin_h,
        json={
            "screen_id": yard["id"],
            "playlist_id": playlists[PLAYLIST_CODE]["id"],
            "window_id": windows[WINDOW_CODE]["id"],
            "layout_id": layouts[LAYOUT_CODE]["id"],
            "summary": "室外立柱正式发布",
        },
    )
    assert r.status_code == 200, r.text
    d = client.get("/api/dashboard", headers=admin_h).json()
    assert d["outdoor_unbound_publications"] == 0
    assert d["outdoor_layout_ready"] is True


def test_official_register_exposes_layout_and_zone(client, admin_h):
    items = client.get("/api/publish/official", headers=admin_h).json()["items"]
    assert items, "种子正式发布册不应为空"
    lobby = next(x for x in items if x["screen_code"] == "scr_lobby_main")
    assert lobby["layout_code"] == LAYOUT_CODE
    assert lobby["layout_title"]
    assert lobby["zone_type"] == "lobby"
    assert all("layout_code" in x and "zone_type" in x for x in items)


def test_layouts_list_exposes_canvas_and_usage(client, admin_h):
    """布局页与发布册同源：槽位画布 + 被正式发布占用数。"""
    items = client.get("/api/layouts", headers=admin_h).json()["items"]
    by_code = {x["code"]: x for x in items}
    split = by_code[LAYOUT_CODE]
    assert split["slots"], "布局页缺多区画布槽位"
    assert split["publication_count"] >= 1
    assert split["slot_count"] == len(split["slots"]) == 2

    created = client.post(
        "/api/layouts",
        headers=admin_h,
        json={
            "code": "lay_empty_probe",
            "title": "空载探针布局",
            "slots": [
                {"name": "left", "x": 0, "y": 0, "w": 50, "h": 100},
                {"name": "right", "x": 50, "y": 0, "w": 50, "h": 100},
            ],
        },
    )
    assert created.status_code == 200, created.text
    items = client.get("/api/layouts", headers=admin_h).json()["items"]
    probe = next(x for x in items if x["code"] == "lay_empty_probe")
    assert probe["publication_count"] == 0
    assert probe["slot_count"] == 2
