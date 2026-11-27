"""写入短锁，防并发双写。"""
from __future__ import annotations

import time
from fastapi import APIRouter, Header, HTTPException

from auth import current_user, require_writer
from db import connect

router = APIRouter(prefix="/api/locks", tags=["locks"])


def acquire(lock_key: str, holder: str, ttl_sec: int = 20) -> None:
    """原子抢锁：仅当无未过期锁时才写成功，同账号并发亦不得双成。"""
    now = time.time()
    with connect() as conn:
        conn.execute("DELETE FROM write_locks WHERE lock_key=? AND expires_at<=?", (lock_key, now))
        cur = conn.execute(
            "INSERT INTO write_locks(lock_key,holder,expires_at) VALUES(?,?,?) "
            "ON CONFLICT(lock_key) DO NOTHING",
            (lock_key, holder, now + ttl_sec),
        )
        won = cur.rowcount == 1
        conn.commit()
        if not won:
            row = conn.execute(
                "SELECT holder FROM write_locks WHERE lock_key=?", (lock_key,)
            ).fetchone()
            raise HTTPException(409, f"资源锁定中：{row['holder'] if row else '未知'}")


def current_holder(lock_key: str) -> str | None:
    """返回未过期锁的持锁人；无人持锁返回 None。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT holder, expires_at FROM write_locks WHERE lock_key=?",
            (lock_key,),
        ).fetchone()
    if row and row["expires_at"] > time.time():
        return row["holder"]
    return None


def record_contention(
    lock_key: str, screen_id: int | None, holder: str, contender: str, action: str
) -> None:
    """争用痕：败方只留痕，不落任何正式行。"""
    with connect() as conn:
        conn.execute(
            "INSERT INTO lock_contention(lock_key,screen_id,holder,contender,action,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (lock_key, screen_id, holder, contender, action, time.time()),
        )
        conn.commit()


def acquire_outdoor_layout(lock_key: str, holder: str, screen_id: int, action: str) -> None:
    """「室外屏布局绑定互斥」：抢锁失败即记争用痕，绝不放行双成。"""
    try:
        acquire(lock_key, holder)
    except HTTPException as exc:
        blocker = current_holder(lock_key) or "未知"
        record_contention(lock_key, screen_id, blocker, holder, action)
        raise HTTPException(
            409, f"室外屏布局绑定互斥：{blocker} 正在操作，后到者只留争用痕"
        ) from exc


def screen_write_lock_key(screen_id: int, zone_type: str) -> str:
    """同屏幕写互斥键：室外屏归入「室外屏布局绑定互斥」，其余沿用发布锁。"""
    return f"outdoor_layout:{screen_id}" if zone_type == "outdoor" else f"publish:{screen_id}"


def acquire_screen_write(screen_id: int, zone_type: str, holder: str, action: str) -> str:
    """发布/撤屏等同一屏幕的写路径共用一把锁；室外路径败方留争用痕。"""
    key = screen_write_lock_key(screen_id, zone_type)
    if zone_type == "outdoor":
        acquire_outdoor_layout(key, holder, screen_id, action)
    else:
        acquire(key, holder)
    return key


def release(lock_key: str, holder: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM write_locks WHERE lock_key=? AND holder=?",
            (lock_key, holder),
        )
        conn.commit()


@router.post("/acquire")
def api_acquire(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    key = (body.get("lock_key") or "").strip()
    if not key:
        raise HTTPException(400, "缺少 lock_key")
    acquire(key, user["username"], int(body.get("ttl_sec") or 20))
    return {"ok": True, "lock_key": key, "holder": user["username"]}


@router.post("/release")
def api_release(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    key = (body.get("lock_key") or "").strip()
    release(key, user["username"])
    return {"ok": True}
