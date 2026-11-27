"""屏幕布局槽位。"""
from __future__ import annotations

import json
from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_history
from auth import current_user, require_writer
from db import connect, rows_to_list
from validators import require_code, require_title

router = APIRouter(prefix="/api/layouts", tags=["layouts"])


def _enrich(row: dict, count: int) -> dict:
    try:
        slots = json.loads(row["slots_json"])
    except json.JSONDecodeError:
        slots = []
    row["slots"] = slots
    row["slot_count"] = len(slots)
    row["publication_count"] = count
    row["bound"] = count > 0
    return row


@router.get("")
def list_layouts(authorization: str | None = Header(default=None)):
    """布局页与发布册同源：槽位画布 + 正式发布占用数。"""
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM layouts ORDER BY id").fetchall())
        usage = {
            r["layout_id"]: r["c"]
            for r in conn.execute(
                "SELECT layout_id, COUNT(*) c FROM publications "
                "WHERE official=1 AND layout_id IS NOT NULL GROUP BY layout_id"
            ).fetchall()
        }
    return {"items": [_enrich(r, usage.get(r["id"], 0)) for r in rows]}


@router.post("")
def create_layout(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    code = require_code(body.get("code"), "布局编码")
    title = require_title(body.get("title"), "布局标题")
    slots = body.get("slots") or []
    if not isinstance(slots, list) or not slots:
        raise HTTPException(400, "布局至少包含一个槽位")
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO layouts(code,title,slots_json,note) VALUES(?,?,?,?)",
                (code, title, json.dumps(slots, ensure_ascii=False), body.get("note") or ""),
            )
            lid = cur.lastrowid
            conn.commit()
        except Exception as exc:
            raise HTTPException(409, f"布局编码冲突: {exc}") from exc
    write_history("layout", lid, "create", f"创建布局 {code}", user["username"])
    return {"id": lid, "code": code}
