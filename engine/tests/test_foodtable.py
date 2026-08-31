"""foodtable.py 覆蓋邏輯測試。"""

from cgm_coach import foodtable

TABLE = [
    {"name": "白飯", "aliases": "白米飯、steamed rice、飯",
     "carb_per_100g": 28, "net_carb_per_100g": 27.6, "protein_per_100g": 2.7,
     "fat_per_100g": 0.3, "fiber_per_100g": 0.4, "gi": 73, "default_portion_g": 180},
    {"name": "無糖豆漿", "aliases": "豆漿、soy milk",
     "carb_per_100g": 1.8, "net_carb_per_100g": 1.3, "protein_per_100g": 3.6,
     "fat_per_100g": 1.6, "fiber_per_100g": 0.5, "gi": 34, "default_portion_g": 260},
]


def test_exact_and_alias_match_overrides_macros():
    est = {
        "items": [
            {"name": "白飯", "portion_g": 200, "portion_confidence": 0.5,
             "carb_g": 70, "net_carb_g": 69, "protein_g": 5, "fat_g": 1, "fiber_g": 1},
            {"name": "soy milk", "portion_g": 250, "portion_confidence": 0.6,
             "carb_g": 8, "net_carb_g": 7, "protein_g": 8, "fat_g": 4, "fiber_g": 1},
        ],
        "gi_est": 60, "gl_est": 40,
    }
    out = foodtable.apply_overrides(est, TABLE)

    rice, soy = out["items"]
    assert rice["source"] == "personal_table"
    assert rice["carb_g"] == 56.0            # 28 * 200 / 100
    assert rice["net_carb_g"] == 55.2        # 27.6 * 200 / 100
    assert soy["source"] == "personal_table"
    assert soy["carb_g"] == 4.5              # 1.8 * 250 / 100

    # totals 重算
    assert out["totals"]["carb_g"] == 60.5
    assert out["overridden_items"] == 2

    # 兩項都有已知 GI 且涵蓋 100% 淨碳水 → 碳水加權
    # (73*55.2 + 34*3.25) / 58.45 ≈ 70.8 → 71
    assert out["gi_source"] == "personal_table"
    assert 69 <= out["gi_est"] <= 72
    assert out["gl_est"] == round(out["gi_est"] * out["totals"]["net_carb_g"] / 100)


def test_no_match_keeps_gemini_values():
    est = {
        "items": [{"name": "牛肉麵", "portion_g": 500, "carb_g": 80,
                   "net_carb_g": 78, "protein_g": 30, "fat_g": 20, "fiber_g": 4}],
        "gi_est": 55, "gl_est": 43,
    }
    out = foodtable.apply_overrides(est, TABLE)
    assert out["items"][0]["source"] == "gemini"
    assert out["items"][0]["carb_g"] == 80
    assert out["gi_source"] == "gemini"
    assert out["gi_est"] == 55
    assert out["overridden_items"] == 0


def test_default_portion_used_when_missing():
    est = {"items": [{"name": "白飯", "carb_g": 40}], "gi_est": 70}
    out = foodtable.apply_overrides(est, TABLE)
    # portion_g 缺 → 用 default_portion_g 180 → carb 28*180/100 = 50.4
    assert out["items"][0]["portion_g"] == 180
    assert out["items"][0]["carb_g"] == 50.4


def test_partial_gi_coverage_falls_back_to_gemini_gi():
    table = [{"name": "白飯", "carb_per_100g": 28, "gi": 73}]  # 只有白飯有 GI
    est = {
        "items": [
            {"name": "白飯", "portion_g": 100, "net_carb_g": 27},
            {"name": "炸雞", "portion_g": 200, "net_carb_g": 40},  # 無表、無 GI
        ],
        "gi_est": 50,
    }
    out = foodtable.apply_overrides(est, table)
    # 已知 GI 只涵蓋 27 / 67 ≈ 40% < 80% → 沿用 Gemini gi_est
    assert out["gi_source"] == "gemini"
    assert out["gi_est"] == 50
