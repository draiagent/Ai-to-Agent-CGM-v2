"""個人常吃食物表覆蓋（personal_food_table 分頁）。

與 n8n「Build meals Row」節點邏輯一致，供批次重新處理與測試使用：
Gemini 給品項與份量 → 對表中 name / aliases 比對（正規化完全比對 → 別名 → 子字串包含）
→ 命中則以 per-100g 值 × portion_g 重算該品項營養素，標 source='personal_table'
→ 重算 totals；已知 GI 涵蓋 >= 80% 淨碳水時以碳水加權算 gi_est。
"""

from __future__ import annotations

import re
from typing import Any, Optional

_SPLIT = re.compile(r"[,、;；]")
_WS = re.compile(r"\s+")

PER100_FIELDS = {
    "carb_g": "carb_per_100g",
    "net_carb_g": "net_carb_per_100g",
    "protein_g": "protein_per_100g",
    "fat_g": "fat_per_100g",
    "fiber_g": "fiber_per_100g",
}


def _norm(s: Any) -> str:
    return _WS.sub("", str(s or "").strip().lower())


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # 過濾 NaN


def _r1(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x, 1)


def build_index(rows: list[dict]) -> list[dict]:
    """把 personal_food_table 各列轉成 {keys, row}。"""
    idx = []
    for row in rows:
        keys = [_norm(row.get("name"))]
        keys += [_norm(a) for a in _SPLIT.split(str(row.get("aliases") or ""))]
        idx.append({"keys": [k for k in keys if k], "row": row})
    return idx


def lookup(index: list[dict], name: str) -> Optional[dict]:
    n = _norm(name)
    if not n:
        return None
    for e in index:                       # 完全 / 別名
        if n in e["keys"]:
            return e["row"]
    for e in index:                       # 子字串包含
        if any(n in k or k in n for k in e["keys"]):
            return e["row"]
    return None


def apply_overrides(estimate: dict, table_rows: list[dict]) -> dict:
    """回傳覆蓋後的 estimate（不修改輸入）。

    estimate 形狀同 Gemini 輸出：items[]、totals、gi_est、gl_est、eating_order…
    """
    index = build_index(table_rows or [])
    items_out: list[dict] = []

    for it in estimate.get("items", []):
        hit = lookup(index, it.get("name", ""))
        if hit is None:
            items_out.append({**it, "source": "gemini"})
            continue
        g = _num(it.get("portion_g")) or _num(hit.get("default_portion_g")) or 0.0
        new = {**it, "portion_g": g, "source": "personal_table", "gi_known": _num(hit.get("gi"))}
        for out_field, col in PER100_FIELDS.items():
            per = _num(hit.get(col))
            if per is not None:
                new[out_field] = _r1(per * g / 100.0)
        if _num(hit.get("net_carb_per_100g")) is None and _num(hit.get("carb_per_100g")) is not None:
            new["net_carb_g"] = new.get("carb_g")
        items_out.append(new)

    def _sum(field: str) -> float:
        return round(sum((_num(it.get(field)) or 0.0) for it in items_out), 1)

    totals = {f: _sum(f) for f in ("carb_g", "net_carb_g", "protein_g", "fat_g", "fiber_g")}

    total_net = sum((_num(it.get("net_carb_g")) or 0.0) for it in items_out)
    with_gi = [it for it in items_out
               if _num(it.get("gi_known")) is not None and (_num(it.get("net_carb_g")) or 0) > 0]
    gi_est = _r1(_num(estimate.get("gi_est")))
    gi_source = "gemini"
    if with_gi and total_net > 0:
        covered = sum(_num(it["net_carb_g"]) for it in with_gi)
        if covered / total_net >= 0.8:
            gi_est = round(sum(_num(it["gi_known"]) * _num(it["net_carb_g"]) for it in with_gi) / covered)
            gi_source = "personal_table"
    gl_est = (round(gi_est * totals["net_carb_g"] / 100.0)
              if gi_est is not None and totals["net_carb_g"] is not None
              else _r1(_num(estimate.get("gl_est"))))

    overridden = sum(1 for it in items_out if it.get("source") == "personal_table")

    return {
        **estimate,
        "items": items_out,
        "totals": totals,
        "gi_est": gi_est,
        "gl_est": gl_est,
        "gi_source": gi_source,
        "overridden_items": overridden,
    }
