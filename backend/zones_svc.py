"""楼宇分区。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from audit_svc import write_history
from auth import current_user, require_writer
from db import connect, rows_to_list
from models import RISK_LEVELS, ZONE_TYPE_LABEL
from policies import assert_zone_risk_for_outdoor
from validators import require_code, require_positive_int, require_title, require_zone_type

router = APIRouter(prefix="/api/zones", tags=["zones"])


def _enrich(row: dict) -> dict:
    row["zone_type_label"] = ZONE_TYPE_LABEL.get(row["zone_type"], row["zone_type"])
    row["risk_label"] = RISK_LEVELS.get(row["risk_level"], str(row["risk_level"]))
    return row


@router.get("")
def list_zones(authorization: str | None = Header(default=None)):
    """分区页露出室外屏布局绑定缺口，避免与发布册脱节。"""
    current_user(authorization)
    with connect() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM zones ORDER BY id").fetchall())
        gaps = {
            r["zone_id"]: r
            for r in conn.execute(
                """
                SELECT s.zone_id,
                       SUM(CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END) AS published,
                       SUM(CASE WHEN p.id IS NOT NULL AND p.layout_id IS NULL THEN 1 ELSE 0 END) AS unbound
                FROM screens s
                LEFT JOIN publications p
                  ON p.screen_id=s.id AND p.official=1 AND p.status='published'
                GROUP BY s.zone_id
                """
            ).fetchall()
        }
    items = []
    for r in rows:
        g = gaps.get(r["id"]) or {"unbound": 0, "published": 0}
        r = _enrich(r)
        r["published_screens"] = g["published"]
        r["unbound_publish_screens"] = g["unbound"]
        r["layout_gap"] = r["zone_type"] == "outdoor" and g["unbound"] > 0
        items.append(r)
    return {"items": items}


@router.post("")
def create_zone(body: dict, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    code = require_code(body.get("code"), "分区编码")
    title = require_title(body.get("title"), "分区标题")
    zone_type = require_zone_type(body.get("zone_type"))
    risk = require_positive_int(body.get("risk_level", 2), "风险等级", 1, 5)
    assert_zone_risk_for_outdoor(zone_type, risk)
    floor_label = (body.get("floor_label") or "").strip()
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO zones(code,title,zone_type,risk_level,floor_label) VALUES(?,?,?,?,?)",
                (code, title, zone_type, risk, floor_label),
            )
            zid = cur.lastrowid
            conn.commit()
        except Exception as exc:
            raise HTTPException(409, f"分区编码冲突: {exc}") from exc
    write_history("zone", zid, "create", f"创建分区 {code}", user["username"])
    return {"id": zid, "code": code}
