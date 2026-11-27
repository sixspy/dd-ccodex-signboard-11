"""变更历史。"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import connect, rows_to_list

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def list_history(limit: int = 100, authorization: str | None = Header(default=None)):
    """历史页同时露出争用痕，败方留痕可追溯。"""
    current_user(authorization)
    cap = max(1, min(limit, 300))
    with connect() as conn:
        rows = rows_to_list(
            conn.execute(
                "SELECT * FROM change_history ORDER BY id DESC LIMIT ?", (cap,)
            ).fetchall()
        )
        contentions = rows_to_list(
            conn.execute(
                "SELECT * FROM lock_contention ORDER BY id DESC LIMIT ?", (cap,)
            ).fetchall()
        )
    return {"items": rows, "contentions": contentions}
