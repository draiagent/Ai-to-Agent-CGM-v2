"""align.py 核心指標的合成資料測試。"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from cgm_coach import align

TZ = "Asia/Taipei"


def _make_cgm(t0, curve, session="S1", step_min=5, pre_min=30):
    """curve: list[(minute_from_t0, glucose)]，會線性內插到每 step_min 一點。"""
    minutes = np.arange(-pre_min, curve[-1][0] + step_min, step_min)
    xs = [m for m, _ in curve]
    ys = [g for _, g in curve]
    g = np.interp(minutes, xs, ys, left=ys[0], right=ys[-1])
    rows = [
        {"ts": (t0 + timedelta(minutes=int(m))).isoformat(),
         "glucose_mgdl": float(v), "sensor_session": session}
        for m, v in zip(minutes, g)
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def t0():
    return pd.Timestamp(datetime(2026, 8, 25, 12, 40), tz=TZ)


def test_clean_meal_metrics(t0):
    # baseline 100 → 峰 160 @ 45min → 回 105 @ 150min
    cgm = _make_cgm(t0, [(-30, 100), (0, 100), (45, 160), (150, 105), (180, 103)])
    # 讓 session 起始遠早於 t0，避免 warmup flag
    cgm.loc[0, "ts"] = (t0 - timedelta(hours=48)).isoformat()
    meals = pd.DataFrame([{"meal_id": t0.isoformat(), "t0": t0.isoformat(), "net_carb_g": 45}])

    out = align.analyze_all(meals, cgm)
    r = out.iloc[0]

    assert r["is_clean"], r["flags"]
    assert r["baseline"] == pytest.approx(100, abs=1)
    assert r["delta_peak"] == pytest.approx(60, abs=2)
    assert r["time_to_peak"] == pytest.approx(45, abs=6)
    assert r["iauc"] > 0
    # 每 15g 碳水標準化：60 * 15 / 45 = 20
    assert r["delta_peak_per15"] == pytest.approx(20, abs=1.5)
    assert r["time_to_recovery"] is not None


def test_contaminated_flag(t0):
    cgm = _make_cgm(t0, [(-30, 100), (0, 100), (45, 150), (180, 110)])
    cgm.loc[0, "ts"] = (t0 - timedelta(hours=48)).isoformat()
    meals = pd.DataFrame([
        {"meal_id": t0.isoformat(), "t0": t0.isoformat(), "net_carb_g": 40},
        {"meal_id": "snack", "t0": (t0 + timedelta(minutes=90)).isoformat(), "net_carb_g": 15},
    ])
    out = align.analyze_all(meals, cgm)
    assert "contaminated" in out.iloc[0]["flags"]


def test_not_recovered_flag(t0):
    # 血糖一路走高不回落
    cgm = _make_cgm(t0, [(-30, 110), (0, 110), (60, 190), (180, 185)])
    cgm.loc[0, "ts"] = (t0 - timedelta(hours=48)).isoformat()
    meals = pd.DataFrame([{"meal_id": t0.isoformat(), "t0": t0.isoformat(), "net_carb_g": 60}])
    out = align.analyze_all(meals, cgm)
    assert "not_recovered_3h" in out.iloc[0]["flags"]
    assert out.iloc[0]["time_to_recovery"] is None


def test_iauc_wolever_clips_below_baseline(t0):
    # 對稱：先上到 +40 再下到 -40，Wolever iAUC 只算上半部
    cgm = _make_cgm(t0, [(-30, 100), (0, 100), (30, 140), (90, 60), (180, 100)])
    cgm.loc[0, "ts"] = (t0 - timedelta(hours=48)).isoformat()
    meals = pd.DataFrame([{"meal_id": t0.isoformat(), "t0": t0.isoformat(), "net_carb_g": 30}])
    out = align.analyze_all(meals, cgm)
    iauc = out.iloc[0]["iauc"]
    # 只有 baseline 以上面積：約略在 0 與「整段正梯形」之間，且為正
    assert iauc is not None and iauc > 0
