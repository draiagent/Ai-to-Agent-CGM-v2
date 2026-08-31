"""CGM 共識指標面板（2019 International Consensus on Time in Range）。

不使用「代謝彈性」一詞；輸出可辯護的血糖變異與範圍指標。定義見 ../README.md §7。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .align import ensure_tz

# 目標範圍（一般非孕成人；糖尿病前期/自我追蹤同樣適用作參考）
TIR_LOW, TIR_HIGH = 70, 180
TBR_LEVEL1, TBR_LEVEL2 = 70, 54
TAR_LEVEL1, TAR_LEVEL2 = 180, 250
CV_STABLE_THRESHOLD = 36.0  # %
OVERNIGHT_START_H, OVERNIGHT_END_H = 0, 6


def gmi(mean_glucose_mgdl: float) -> float:
    """Glucose Management Indicator（估算 A1c, %）。Bergenstal 2018。"""
    return round(3.31 + 0.02392 * mean_glucose_mgdl, 2)


def _pct(mask: pd.Series) -> float:
    return round(100.0 * mask.mean(), 1) if len(mask) else 0.0


def panel(cgm: pd.DataFrame) -> dict:
    """回傳一份面板 dict。cgm 需含 `ts`, `glucose_mgdl`。"""
    df = cgm.copy()
    df["ts"] = ensure_tz(df["ts"])
    g = df["glucose_mgdl"].astype(float).dropna()
    if g.empty:
        return {"error": "no_data"}

    mean_g = float(g.mean())
    sd = float(g.std(ddof=1)) if len(g) > 1 else 0.0
    cv = round(100.0 * sd / mean_g, 1) if mean_g else None

    hours_span = (df["ts"].max() - df["ts"].min()).total_seconds() / 3600.0
    overnight = df[(df["ts"].dt.hour >= OVERNIGHT_START_H) & (df["ts"].dt.hour < OVERNIGHT_END_H)]
    on_g = overnight["glucose_mgdl"].astype(float).dropna()

    return {
        "n_readings": int(len(g)),
        "span_hours": round(hours_span, 1),
        "mean_glucose_mgdl": round(mean_g, 1),
        "gmi_pct": gmi(mean_g),
        "sd_mgdl": round(sd, 1),
        "cv_pct": cv,
        "cv_stable": (cv is not None and cv < CV_STABLE_THRESHOLD),
        "tir_70_180_pct": _pct((g >= TIR_LOW) & (g <= TIR_HIGH)),
        "tbr_lt70_pct": _pct(g < TBR_LEVEL1),
        "tbr_lt54_pct": _pct(g < TBR_LEVEL2),
        "tar_gt180_pct": _pct(g > TAR_LEVEL1),
        "tar_gt250_pct": _pct(g > TAR_LEVEL2),
        "overnight_mean_mgdl": round(float(on_g.mean()), 1) if not on_g.empty else None,
        "overnight_cv_pct": (
            round(100.0 * on_g.std(ddof=1) / on_g.mean(), 1)
            if len(on_g) > 1 and on_g.mean() else None
        ),
    }


def safety_events(cgm: pd.DataFrame) -> pd.DataFrame:
    """低血糖事件清單（Level 1 <70、Level 2 <54），供週報頂端提示。"""
    df = cgm.copy()
    df["ts"] = ensure_tz(df["ts"])
    df = df.sort_values("ts")
    g = df["glucose_mgdl"].astype(float)
    df["level"] = np.select(
        [g < TBR_LEVEL2, g < TBR_LEVEL1],
        ["level2_lt54", "level1_lt70"],
        default="",
    )
    return df[df["level"] != ""][["ts", "glucose_mgdl", "level"]].reset_index(drop=True)
