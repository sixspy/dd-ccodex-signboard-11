"""专项红测：同资源互斥「室外屏布局绑定互斥」下的并发对打（锁口径）。

失败测：两路室外正式发布对打时，无锁双成且无争用痕。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import connect  # noqa: E402
from race_harness import outdoor_lock_key, race_outdoor_layout  # noqa: E402

OUTDOOR_SCREEN = "scr_yard_e1"
LAYOUT_CODE = "lay_split"
PLAYLIST_CODE = "pl_lift_loop"
WINDOW_CODE = "win_workday"


def _setup(client, h):
    screens = {s["code"]: s for s in client.get("/api/screens", headers=h).json()["items"]}
    layouts = {x["code"]: x for x in client.get("/api/layouts", headers=h).json()["items"]}
    playlists = {p["code"]: p for p in client.get("/api/playlists", headers=h).json()["items"]}
    windows = {w["code"]: w for w in client.get("/api/windows", headers=h).json()["items"]}
    yard = screens[OUTDOOR_SCREEN]
    if yard["status"] != "online":
        r = client.patch(f"/api/screens/{yard['id']}", headers=h, json={"status": "online"})
        assert r.status_code == 200, r.text
    payload = {
        "screen_id": yard["id"],
        "playlist_id": playlists[PLAYLIST_CODE]["id"],
        "window_id": windows[WINDOW_CODE]["id"],
        "layout_id": layouts[LAYOUT_CODE]["id"],
        "summary": "室外立柱并发发布",
    }
    return yard["id"], payload


def _official_rows(screen_id):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE screen_id=? AND official=1", (screen_id,)
        ).fetchall()


def _traces(client, h, screen_id):
    r = client.get(
        "/api/publish/contention", headers=h, params={"screen_id": screen_id}
    )
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_race_entry_exists():
    assert callable(race_outdoor_layout)
    assert outdoor_lock_key(7) == "outdoor_layout:7"


def test_late_contenders_only_leave_trace(client, admin_h, writer_h):
    """失败测：两路「室外屏布局绑定互斥」无锁双成。"""
    screen_id, payload = _setup(client, admin_h)
    results = race_outdoor_layout(
        client, writer_h, [admin_h, admin_h], screen_id, lambda: payload
    )
    codes = [r.status_code for r in results]
    assert codes == [409, 409], f"后到者不得双成：{codes} / {[r.text for r in results]}"

    assert _official_rows(screen_id) == [], "争用败方不得落正式发布行"

    traces = _traces(client, admin_h, screen_id)
    assert len(traces) == 2, "争用败方须各留一条痕"
    assert {t["lock_key"] for t in traces} == {outdoor_lock_key(screen_id)}
    assert all(t["holder"] == "writer" for t in traces)
    assert all(t["contender"] == "admin" for t in traces)


def test_after_release_publish_lands_without_new_trace(client, admin_h, writer_h):
    screen_id, payload = _setup(client, admin_h)
    results = race_outdoor_layout(
        client, writer_h, [admin_h, admin_h], screen_id, lambda: payload
    )
    assert [r.status_code for r in results] == [409, 409]
    before = len(_traces(client, admin_h, screen_id))

    ok = client.post("/api/publish/official", headers=admin_h, json=payload)
    assert ok.status_code == 200, ok.text
    rows = _official_rows(screen_id)
    assert len(rows) == 1
    assert rows[0]["layout_id"] == payload["layout_id"]
    assert len(_traces(client, admin_h, screen_id)) == before, "正常发布不得新增争用痕"


def _assert_double_fire_invariants(client, h, screen_id, payload, results):
    """双发不变量：正式行恒为 1 条；每个被拒者恰好留一条争用痕。"""
    codes = [r.status_code for r in results]
    assert set(codes) <= {200, 409}, [r.text for r in results]
    assert 200 in codes, f"至少一路应成功：{[r.text for r in results]}"
    rows = _official_rows(screen_id)
    assert len(rows) == 1, "同屏正式行不得双成"
    assert rows[0]["layout_id"] == payload["layout_id"]
    rejected = codes.count(409)
    traces = _traces(client, h, screen_id)
    assert len(traces) == rejected, "每个被拒的后到者须恰好留一条争用痕"


def test_simultaneous_double_fire_never_double_wins(client, admin_h, writer_h):
    """真并发双发：无论先后，室外屏正式行恒为 1 条，被拒者留痕。"""
    import threading

    screen_id, payload = _setup(client, admin_h)
    headers_pair = [admin_h, writer_h]
    barrier = threading.Barrier(2)
    results = [None, None]

    def fire(idx):
        barrier.wait(timeout=10)
        results[idx] = client.post("/api/publish/official", headers=headers_pair[idx], json=payload)

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    _assert_double_fire_invariants(client, admin_h, screen_id, payload, results)


def test_same_actor_double_fire_never_double_wins(client, admin_h):
    """同账号并发双发同样不得双成：互斥不按人放行。"""
    import threading

    screen_id, payload = _setup(client, admin_h)
    barrier = threading.Barrier(2)
    results = [None, None]

    def fire(idx):
        barrier.wait(timeout=10)
        results[idx] = client.post("/api/publish/official", headers=admin_h, json=payload)

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    _assert_double_fire_invariants(client, admin_h, screen_id, payload, results)

