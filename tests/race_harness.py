"""专项并发对打入口：race_outdoor_layout。

赢家先持「室外屏布局绑定互斥」锁，败方并发触发布上屏；
后到者只许留争用痕，不得双成，不得落任何正式行。
"""
from __future__ import annotations

import threading


def outdoor_lock_key(screen_id: int) -> str:
    return f"outdoor_layout:{screen_id}"


def race_outdoor_layout(client, holder_headers, contender_headers, screen_id, payload, ttl_sec=30):
    """并发对打：holder 持锁，多个 contender 同时打正式发布。

    返回 contender 的响应列表（与 contender_headers 同序）；结束后释放锁。
    """
    key = outdoor_lock_key(screen_id)
    held = client.post(
        "/api/locks/acquire",
        headers=holder_headers,
        json={"lock_key": key, "ttl_sec": ttl_sec},
    )
    assert held.status_code == 200, held.text

    barrier = threading.Barrier(len(contender_headers))
    results = [None] * len(contender_headers)
    errors = [None] * len(contender_headers)

    def worker(idx, headers):
        try:
            barrier.wait(timeout=10)
            results[idx] = client.post("/api/publish/official", headers=headers, json=payload())
        except Exception as exc:  # noqa: BLE001 - 交回测试判定
            errors[idx] = exc

    threads = [
        threading.Thread(target=worker, args=(i, h), daemon=True)
        for i, h in enumerate(contender_headers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    released = client.post(
        "/api/locks/release", headers=holder_headers, json={"lock_key": key}
    )
    assert released.status_code == 200, released.text
    assert not any(errors), errors
    assert all(r is not None for r in results), "并发对打未全部返回"
    return results
