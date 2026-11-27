"""总览。"""
from __future__ import annotations

from fastapi import APIRouter, Header

from auth import current_user
from db import PRODUCT_META, connect

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        screens = conn.execute("SELECT COUNT(*) c FROM screens").fetchone()["c"]
        online = conn.execute("SELECT COUNT(*) c FROM screens WHERE status='online'").fetchone()["c"]
        assets = conn.execute("SELECT COUNT(*) c FROM assets WHERE status='ready'").fetchone()["c"]
        pubs = conn.execute(
            "SELECT COUNT(*) c FROM publications WHERE official=1 AND status='published'"
        ).fetchone()["c"]
        shadows = conn.execute(
            "SELECT COUNT(*) c FROM publish_shadows WHERE status='open'"
        ).fetchone()["c"]
        panics = conn.execute("SELECT COUNT(*) c FROM panic_events").fetchone()["c"]
        overrides = conn.execute(
            "SELECT COUNT(*) c FROM overrides WHERE official=1 AND active=1"
        ).fetchone()["c"]
        # 室外齐套口径：正式发布过的室外屏必须逐块绑定布局，缺一块即不齐套。
        outdoor = conn.execute(
            """
            SELECT COUNT(p.id) total,
                   SUM(CASE WHEN p.layout_id IS NULL THEN 1 ELSE 0 END) unbound
            FROM publications p
            JOIN screens s ON s.id=p.screen_id
            JOIN zones z ON z.id=s.zone_id
            WHERE p.official=1 AND p.status='published' AND z.zone_type='outdoor'
            """
        ).fetchone()
        contention = conn.execute("SELECT COUNT(*) c FROM lock_contention").fetchone()["c"]
    outdoor_total = outdoor["total"] or 0
    outdoor_unbound = outdoor["unbound"] or 0
    return {
        "product": PRODUCT_META["name"],
        "domain": PRODUCT_META["domain"],
        "sub": PRODUCT_META["sub"],
        "skeleton": PRODUCT_META["skeleton"],
        "screens": screens,
        "online_screens": online,
        "ready_assets": assets,
        "official_publications": pubs,
        "open_shadows": shadows,
        "panic_events": panics,
        "active_overrides": overrides,
        "outdoor_publications": outdoor_total,
        "outdoor_unbound_publications": outdoor_unbound,
        "outdoor_layout_ready": outdoor_unbound == 0,
        "lock_contentions": contention,
    }
