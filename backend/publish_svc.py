"""发布上屏：甲=同事务正式落库；乙=影子草案升正。

专项 signboard-11「室外屏正式上屏须绑定布局」：
- 甲路径缺布局整笔拒写，不得插入任何正式行；
- 乙路径缺布局只许影子草案（正式零改），待绑定布局后再升正；
- 两边不得混用；非室外分区不受本专项约束。
室外屏写入走「室外屏布局绑定互斥」，后到者只留争用痕。
"""
from __future__ import annotations

import time
from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_audit, write_history
from auth import current_user, require_writer
from db import connect, rows_to_list
from locks import acquire_screen_write, release
from policies import (
    assert_outdoor_layout_bound,
    assert_playlist_ready,
    assert_screen_online,
    assert_window_open,
)
from validators import require_positive_int, require_title

router = APIRouter(prefix="/api/publish", tags=["publish"])


def _publication_select(where: str) -> str:
    return f"""
        SELECT p.*, s.code screen_code, s.title screen_title,
               pl.code playlist_code, w.code window_code,
               z.zone_type zone_type, z.title zone_title,
               l.code layout_code, l.title layout_title, l.slots_json layout_slots_json
        FROM publications p
        JOIN screens s ON s.id=p.screen_id
        JOIN zones z ON z.id=s.zone_id
        JOIN playlists pl ON pl.id=p.playlist_id
        JOIN time_windows w ON w.id=p.window_id
        LEFT JOIN layouts l ON l.id=p.layout_id
        {where}
        ORDER BY p.id DESC
    """


@router.get("/official")
def list_official(authorization: str | None = Header(default=None)):
    """发布册：与布局同源露出 layout_id/layout_code 与分区类型。"""
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(conn.execute(_publication_select("WHERE p.official=1")).fetchall())
    return {"items": rows}


@router.get("/shadows")
def list_shadows(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                """
                SELECT sh.*, s.code screen_code, pl.code playlist_code, w.code window_code,
                       z.zone_type zone_type, l.code layout_code, l.title layout_title
                FROM publish_shadows sh
                JOIN screens s ON s.id=sh.screen_id
                JOIN zones z ON z.id=s.zone_id
                JOIN playlists pl ON pl.id=sh.playlist_id
                JOIN time_windows w ON w.id=sh.window_id
                LEFT JOIN layouts l ON l.id=sh.layout_id
                ORDER BY sh.id DESC
                """
            ).fetchall()
        )
    return {"items": rows}


@router.get("/contention")
def list_contention(screen_id: int | None = None, authorization: str | None = Header(default=None)):
    """争用痕：室外布局绑定互斥下败方留下的记录。"""
    current_user(authorization)
    with connect() as conn:
        if screen_id:
            rows = rows_to_list(
                conn.execute(
                    "SELECT * FROM lock_contention WHERE screen_id=? ORDER BY id",
                    (screen_id,),
                ).fetchall()
            )
        else:
            rows = rows_to_list(
                conn.execute("SELECT * FROM lock_contention ORDER BY id").fetchall()
            )
    return {"items": rows}


def _zone_type_of(conn, screen_id: int) -> str:
    row = conn.execute(
        "SELECT z.zone_type FROM screens s JOIN zones z ON z.id=s.zone_id WHERE s.id=?",
        (screen_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "屏幕不存在")
    return row["zone_type"]


def _load_refs(conn, screen_id, playlist_id, window_id):
    """同事务跨表账实：屏幕→分区→清单→时段窗。"""
    screen = conn.execute(
        """
        SELECT s.*, z.zone_type zone_type, z.title zone_title
        FROM screens s JOIN zones z ON z.id=s.zone_id
        WHERE s.id=?
        """,
        (screen_id,),
    ).fetchone()
    playlist = conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,)).fetchone()
    window = conn.execute("SELECT * FROM time_windows WHERE id=?", (window_id,)).fetchone()
    if not screen or not playlist or not window:
        raise HTTPException(404, "屏幕/清单/时段窗不存在")
    assert_screen_online(screen["status"])
    assert_playlist_ready(playlist["status"])
    assert_window_open(window["status"])
    return screen, playlist, window


def _layout_id_from_body(body: dict) -> int | None:
    layout_id = body.get("layout_id")
    if layout_id in (None, ""):
        return None
    return require_positive_int(layout_id, "布局编号", 1, 2**31 - 1)


def _load_layout(conn, layout_id):
    """布局必须已存在；与发布同事务联查，保证账实一致。"""
    if layout_id is None:
        return None
    row = conn.execute("SELECT * FROM layouts WHERE id=?", (layout_id,)).fetchone()
    if not row:
        raise HTTPException(404, "布局不存在")
    return row


def _write_official(conn, screen, playlist_id, window_id, layout, summary, user):
    """正式行落库 + 升版本；调用方已做布局绑定校验。"""
    prev = conn.execute(
        "SELECT version FROM publications WHERE screen_id=? AND official=1",
        (screen["id"],),
    ).fetchone()
    version = (prev["version"] + 1) if prev else 1
    conn.execute("DELETE FROM publications WHERE screen_id=? AND official=1", (screen["id"],))
    cur = conn.execute(
        "INSERT INTO publications(screen_id,playlist_id,window_id,layout_id,version,summary,status,official,published_at,published_by) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            screen["id"],
            playlist_id,
            window_id,
            layout["id"] if layout else None,
            version,
            summary,
            "published",
            1,
            time.time(),
            user["username"],
        ),
    )
    return cur.lastrowid, version


@router.post("/official")
def publish_official(body: dict, authorization: str | None = Header(default=None)):
    """甲路径：同事务写入正式发布并升版本；室外缺布局整笔拒写。"""
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    playlist_id = require_positive_int(body.get("playlist_id"), "清单编号")
    window_id = require_positive_int(body.get("window_id"), "时段编号")
    summary = require_title(body.get("summary") or "正式发布", "发布摘要")
    layout_id = _layout_id_from_body(body)
    with connect() as conn:
        zone_type = _zone_type_of(conn, screen_id)
    lock_key = acquire_screen_write(screen_id, zone_type, user["username"], "publish_official")
    try:
        with connect() as conn:
            screen, _playlist, _window = _load_refs(conn, screen_id, playlist_id, window_id)
            layout = _load_layout(conn, layout_id)
            assert_outdoor_layout_bound(screen["zone_type"], layout)
            pid, version = _write_official(
                conn, screen, playlist_id, window_id, layout, summary, user
            )
            conn.commit()
        write_history("publication", pid, "publish_official", summary, user["username"])
        write_audit(user["username"], "publish.official", {"id": pid, "version": version})
        return {"id": pid, "version": version, "path": "official"}
    finally:
        release(lock_key, user["username"])


@router.post("/shadow")
def create_shadow(body: dict, authorization: str | None = Header(default=None)):
    """乙路径第一步：只写影子草案，正式区零改。缺布局也允许（仅草案）。"""
    user = current_user(authorization)
    require_writer(user)
    screen_id = require_positive_int(body.get("screen_id"), "屏幕编号")
    playlist_id = require_positive_int(body.get("playlist_id"), "清单编号")
    window_id = require_positive_int(body.get("window_id"), "时段编号")
    summary = require_title(body.get("summary") or "影子发布草案", "发布摘要")
    layout_id = _layout_id_from_body(body)
    with connect() as conn:
        _load_refs(conn, screen_id, playlist_id, window_id)
        if layout_id is not None:
            _load_layout(conn, layout_id)
        cur = conn.execute(
            "INSERT INTO publish_shadows(screen_id,playlist_id,window_id,layout_id,summary,status,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)",
            (
                screen_id,
                playlist_id,
                window_id,
                layout_id,
                summary,
                "open",
                time.time(),
                user["username"],
            ),
        )
        sid = cur.lastrowid
        conn.commit()
    write_history("publish_shadow", sid, "create", summary, user["username"])
    return {"id": sid, "path": "shadow", "status": "open", "layout_id": layout_id}


@router.patch("/shadow/{shadow_id}/layout")
def bind_shadow_layout(shadow_id: int, body: dict, authorization: str | None = Header(default=None)):
    """给待升正影子补绑布局；正式区仍零改。"""
    user = current_user(authorization)
    require_writer(user)
    layout_id = require_positive_int(body.get("layout_id"), "布局编号")
    with connect() as conn:
        sh = conn.execute("SELECT * FROM publish_shadows WHERE id=?", (shadow_id,)).fetchone()
        if not sh:
            raise HTTPException(404, "影子不存在")
        if sh["status"] != "open":
            raise HTTPException(409, "影子不可改绑布局")
        _load_layout(conn, layout_id)
        conn.execute(
            "UPDATE publish_shadows SET layout_id=? WHERE id=?", (layout_id, shadow_id)
        )
        conn.commit()
    write_history("publish_shadow", shadow_id, "bind_layout", f"绑定布局 {layout_id}", user["username"])
    return {"id": shadow_id, "layout_id": layout_id}


@router.post("/shadow/{shadow_id}/promote")
def promote_shadow(shadow_id: int, authorization: str | None = Header(default=None)):
    """乙路径升正：原子落正式区；室外缺布局整笔拒写且影子保持待升正。"""
    user = current_user(authorization)
    require_writer(user)
    with connect() as conn:
        sh = conn.execute("SELECT * FROM publish_shadows WHERE id=?", (shadow_id,)).fetchone()
        if not sh:
            raise HTTPException(404, "影子不存在")
        if sh["status"] != "open":
            raise HTTPException(409, "影子不可升正")
        screen_id = sh["screen_id"]
        zone_type = _zone_type_of(conn, screen_id)
    lock_key = acquire_screen_write(screen_id, zone_type, user["username"], "promote_shadow")
    try:
        with connect() as conn:
            sh = conn.execute("SELECT * FROM publish_shadows WHERE id=?", (shadow_id,)).fetchone()
            if sh["status"] != "open":
                raise HTTPException(409, "影子不可升正")
            screen, _playlist, _window = _load_refs(
                conn, sh["screen_id"], sh["playlist_id"], sh["window_id"]
            )
            layout = _load_layout(conn, sh["layout_id"])
            assert_outdoor_layout_bound(screen["zone_type"], layout)
            pid, version = _write_official(
                conn, screen, sh["playlist_id"], sh["window_id"], layout, sh["summary"], user
            )
            conn.execute("UPDATE publish_shadows SET status='promoted' WHERE id=?", (shadow_id,))
            conn.commit()
        write_history("publication", pid, "promote_shadow", f"升正影子 {shadow_id}", user["username"])
        write_audit(user["username"], "publish.promote", {"shadow_id": shadow_id, "id": pid})
        return {"id": pid, "version": version, "path": "shadow_promote"}
    finally:
        release(lock_key, user["username"])
