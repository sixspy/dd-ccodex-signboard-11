# 楼宇数字标牌编排（signboard）

**所属领域：应用开发 · 子方向：全栈开发**

全栈产品：素材入库 → 屏幕台账 → 播放清单 → 时段窗 → 发布上屏 → 紧急撤屏 → 单屏覆盖 → 变更历史 → 在线求值。

## 骨架一句话

楼宇屏幕按清单与时段窗编排内容，发布须版本落库才能上屏，紧急撤屏与变更历史同源。

## H3 切口候选（写路径互斥 · 须择一）

1. **发布上屏**：同事务写入正式播放配置并升版本锁旧版，或只写影子发布草案、升正时原子落正式区（正式区升正前零改）。
2. **紧急撤屏**：同事务立即写正式空屏并记变更，或影子撤屏草案确认后原子撤屏。
3. **单屏覆盖**：同事务写正式覆盖条目，或影子覆盖草案升正。

正确性口径只能走甲乙中的一种且两边不得混用。

## 专项 signboard-11「室外屏正式上屏须绑定布局」

- **甲路径**：室外屏正式发布缺布局 → **整笔拒写**，不插任何正式行、不升版本、不留升版历史；
  布局与分区类型在同一事务内跨表联查，落库的 `layout_id` 即校验通过的那条布局（发布与布局同源）。
- **乙路径**：缺布局**只许影子草案**，正式区零改；`PATCH /api/publish/shadow/{id}/layout`
  补绑布局后再 `promote` 才原子落正式区；缺布局升正整笔拒写且影子保持 `open`。
- 两边不得混用：甲不得改走影子，乙未升正前不得触碰正式区。
- 非室外分区不受本专项约束，缺布局照常发布。
- **同资源互斥「室外屏布局绑定互斥」**：室外屏的发布 / 影子升正 / 撤屏共用
  `outdoor_layout:{screen_id}` 锁；后到者只许留争用痕（`lock_contention`），绝不双成。
- 齐套口径：总览 `outdoor_layout_ready` 仅当所有室外正式发布都绑了布局才为真；
  布局页、分区页、屏幕页、发布册同源露出 `layout_id` / 槽位画布 / 占用数。

夹具复现：`fixtures/outdoor_layout_attempts.json`（「室外屏无布局发布尝试」打头）。

分文件红测：

| 文件 | 口径 |
| --- | --- |
| `tests/feat_layout_write.py` | 写路径甲/乙整笔拒写、同源绑定、非室外不误伤 |
| `tests/feat_layout_board.py` | 总览齐套、发布册布局列、布局页画布与占用 |
| `tests/feat_layout_race.py` | 「室外屏布局绑定互斥」双发不双成、败方只痕 |

并发对打入口：`tests/race_harness.py::race_outdoor_layout`。三红未齐拒合入。

## 一键起环境

```bash
docker compose up -d --build
```

浏览器：http://localhost:11730

- `admin` / `admin123`（管理员）
- `writer` / `writer123`（编排员）
- `viewer` / `viewer123`（只读）

## 本地开发

```powershell
cd projects/18-signboard
$env:PYTHONPATH="backend"
python -m uvicorn app:app --app-dir backend --reload --port 8030
python -m pytest
python scripts/count_loc.py
```

## 空桩

- 远程推屏桥（`remote_push`）
- 媒资中台桥接（`media_bridge`）

接口固定返回 501，题面可点名。
