"""T0 對齊、餐後 5 指標、資料排除規則。

臨床定義見專案 ../README.md §5、§6。全程單位 mg/dL、時間以分鐘（相對 T0）計。
本模組不做任何 I/O，方便單元測試與醫師 code review。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

TZ = "Asia/Taipei"

# ---- 參數（與 README §5/§6 對齊，可由 config 覆寫）--------------------------------
BASELINE_WINDOW_MIN = 15          # 餐前基準取樣窗
BASELINE_MIN_READINGS = 2         # 基準最少有效讀值數
POSTPRANDIAL_MIN = 180            # 觀察窗（3 小時）
RECOVERY_THRESHOLD_MGDL = 10      # 回到 baseline + 10 視為恢復
RECOVERY_SUSTAIN_MIN = 15         # 需持續此時間
GAP_MAX_MIN = 20                  # 觀察窗內容許最大資料斷點
SENSOR_WARMUP_HOURS = 24          # 感測器暖機排除
CONTAMINATION_MIN = 180           # 前後隔離窗
MIN_CLEAN_EXPOSURES = 3           # 進排行的最少乾淨曝光數
NET_CARB_MIN_FOR_NORM = 5.0       # 低於此不做每 15g 標準化


@dataclass
class MealMetrics:
    meal_id: str
    t0: pd.Timestamp
    baseline: Optional[float] = None
    delta_peak: Optional[float] = None
    time_to_peak: Optional[float] = None
    iauc: Optional[float] = None
    time_to_recovery: Optional[float] = None
    delta_peak_per15: Optional[float] = None
    n_readings: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.flags

    def to_dict(self) -> dict:
        d = asdict(self)
        d["t0"] = self.t0.isoformat()
        d["flags"] = ",".join(self.flags)
        d["is_clean"] = self.is_clean
        return d


# ---- 時區 -------------------------------------------------------------------------
def ensure_tz(s: pd.Series, tz: str = TZ) -> pd.Series:
    """把時間欄轉成帶時區的 Timestamp（naive 視為 tz 當地時間）。"""
    out = pd.to_datetime(s, errors="coerce")
    if getattr(out.dt, "tz", None) is None:
        out = out.dt.tz_localize(tz)
    else:
        out = out.dt.tz_convert(tz)
    return out


# ---- 單項指標 -------------------------------------------------------------------
def compute_baseline(cgm: pd.DataFrame, t0: pd.Timestamp,
                     window_min: int = BASELINE_WINDOW_MIN,
                     min_readings: int = BASELINE_MIN_READINGS
                     ) -> tuple[Optional[float], bool]:
    """[T0-window, T0] 內 CGM 讀值平均。回傳 (baseline, valid)。"""
    lo = t0 - timedelta(minutes=window_min)
    m = (cgm["ts"] >= lo) & (cgm["ts"] <= t0)
    vals = cgm.loc[m, "glucose_mgdl"].dropna()
    if len(vals) < min_readings:
        return (float(vals.mean()) if len(vals) else None, False)
    return float(vals.mean()), True


def postprandial(cgm: pd.DataFrame, t0: pd.Timestamp,
                 minutes: int = POSTPRANDIAL_MIN) -> pd.DataFrame:
    """回傳觀察窗內的 CGM，並附上相對分鐘欄 `min`。"""
    hi = t0 + timedelta(minutes=minutes)
    w = cgm[(cgm["ts"] >= t0) & (cgm["ts"] <= hi)].copy()
    w = w.sort_values("ts")
    w["min"] = (w["ts"] - t0).dt.total_seconds() / 60.0
    return w


def delta_peak(window: pd.DataFrame, baseline: float) -> tuple[Optional[float], Optional[float]]:
    """峰值增幅與達峰時間（分鐘）。"""
    if window.empty or baseline is None:
        return None, None
    i = window["glucose_mgdl"].idxmax()
    peak = float(window.loc[i, "glucose_mgdl"])
    return peak - baseline, float(window.loc[i, "min"])


def incremental_auc(window: pd.DataFrame, baseline: float) -> Optional[float]:
    """iAUC（mg/dL·min），梯形法，僅計 baseline 以上面積（Wolever 法）。

    線段跨越 baseline 時，只取在 baseline 之上的三角形面積。
    """
    if window.empty or baseline is None or len(window) < 2:
        return None
    t = window["min"].to_numpy(dtype=float)
    g = window["glucose_mgdl"].to_numpy(dtype=float) - baseline  # 相對基準
    area = 0.0
    for k in range(len(t) - 1):
        dt = t[k + 1] - t[k]
        if dt <= 0:
            continue
        a, b = g[k], g[k + 1]
        if a >= 0 and b >= 0:
            area += 0.5 * (a + b) * dt
        elif a <= 0 and b <= 0:
            continue
        else:  # 跨越 baseline
            if a > 0:  # 由正轉負
                frac = a / (a - b)
                area += 0.5 * a * (dt * frac)
            else:      # 由負轉正
                frac = b / (b - a)
                area += 0.5 * b * (dt * frac)
    return float(area)


def time_to_recovery(window: pd.DataFrame, baseline: float,
                     threshold: float = RECOVERY_THRESHOLD_MGDL,
                     sustain_min: int = RECOVERY_SUSTAIN_MIN) -> Optional[float]:
    """回到 baseline+threshold 以內且持續 sustain_min 的時間（分鐘）。

    觀察窗內找不到（含資料不足以確認持續）→ None（呼叫端記 not_recovered_3h）。
    """
    if window.empty or baseline is None:
        return None
    ceil = baseline + threshold
    rows = window[["min", "glucose_mgdl"]].to_numpy(dtype=float)
    for k in range(len(rows)):
        t_k, g_k = rows[k]
        if g_k > ceil:
            continue
        # 檢查 [t_k, t_k + sustain] 內所有讀值都 <= ceil
        seg = rows[(rows[:, 0] >= t_k) & (rows[:, 0] <= t_k + sustain_min)]
        if seg[:, 0].max() < t_k + sustain_min:
            # 資料未涵蓋整個持續窗，無法確認
            return None
        if (seg[:, 1] <= ceil).all():
            return float(t_k)
    return None


# ---- 排除規則 -----------------------------------------------------------------
def exclusion_flags(meal_id: str, t0: pd.Timestamp, baseline_valid: bool,
                    window: pd.DataFrame, meals: pd.DataFrame, cgm: pd.DataFrame
                    ) -> list[str]:
    flags: list[str] = []

    if not baseline_valid:
        flags.append("baseline_invalid")

    # 餐次污染：前後 CONTAMINATION_MIN 內有其他餐
    lo = t0 - timedelta(minutes=CONTAMINATION_MIN)
    hi = t0 + timedelta(minutes=CONTAMINATION_MIN)
    others = meals[(meals["t0"] >= lo) & (meals["t0"] <= hi) & (meals["meal_id"] != meal_id)]
    if not others.empty:
        flags.append("contaminated")

    # 感測器暖機：t0 距該 session 起始 < 24h
    if not window.empty and "sensor_session" in window:
        sess = window["sensor_session"].dropna().unique()
        for s in sess:
            start = cgm.loc[cgm["sensor_session"] == s, "ts"].min()
            if pd.notna(start) and t0 < start + timedelta(hours=SENSOR_WARMUP_HOURS):
                flags.append("warmup")
                break

    # 資料斷點：觀察窗內最大間隔 > GAP_MAX_MIN
    if len(window) >= 2:
        gaps = window["min"].diff().dropna()
        if (gaps > GAP_MAX_MIN).any():
            flags.append("gap")
    elif len(window) < 2:
        flags.append("gap")

    return flags


# ---- 主流程 -----------------------------------------------------------------
def analyze_meal(meal_row: pd.Series, meals: pd.DataFrame, cgm: pd.DataFrame) -> MealMetrics:
    t0 = meal_row["t0"]
    mm = MealMetrics(meal_id=str(meal_row["meal_id"]), t0=t0)

    baseline, baseline_valid = compute_baseline(cgm, t0)
    mm.baseline = baseline
    win = postprandial(cgm, t0)
    mm.n_readings = len(win)

    mm.flags = exclusion_flags(mm.meal_id, t0, baseline_valid, win, meals, cgm)

    if baseline is not None and not win.empty:
        dp, ttp = delta_peak(win, baseline)
        mm.delta_peak = _round(dp)
        mm.time_to_peak = _round(ttp)
        if "gap" not in mm.flags:
            mm.iauc = _round(incremental_auc(win, baseline))
        ttr = time_to_recovery(win, baseline)
        mm.time_to_recovery = _round(ttr)
        if ttr is None:
            mm.flags.append("not_recovered_3h")

        net_carb = meal_row.get("net_carb_g")
        if (mm.delta_peak is not None and net_carb is not None
                and float(net_carb) >= NET_CARB_MIN_FOR_NORM):
            mm.delta_peak_per15 = _round(mm.delta_peak * 15.0 / float(net_carb))

    return mm


def analyze_all(meals: pd.DataFrame, cgm: pd.DataFrame) -> pd.DataFrame:
    """對所有餐計算指標。回傳每餐一列的 DataFrame。"""
    meals = meals.copy()
    cgm = cgm.copy()
    meals["t0"] = ensure_tz(meals["t0"])
    cgm["ts"] = ensure_tz(cgm["ts"])
    cgm = cgm.sort_values("ts")
    if "sensor_session" not in cgm:
        cgm["sensor_session"] = "unknown"

    rows = [analyze_meal(r, meals, cgm).to_dict() for _, r in meals.iterrows()]
    return pd.DataFrame(rows)


def food_ranking(analyzed: pd.DataFrame, meals: pd.DataFrame,
                 min_exposures: int = MIN_CLEAN_EXPOSURES) -> pd.DataFrame:
    """以每 15g 碳水標準化的 ΔPeak 對食物排行。

    只納入 flags 為空（乾淨）的餐；同一 `food_key` 需 >= min_exposures 筆。
    `food_key` 由呼叫端在 meals 中提供（例如品項名或餐型標籤）；此處以 `note` 佔位。
    """
    df = analyzed[analyzed["is_clean"]].merge(
        meals[["meal_id", "note"]].rename(columns={"note": "food_key"}),
        on="meal_id", how="left",
    )
    df = df.dropna(subset=["delta_peak_per15"])
    grp = df.groupby("food_key")["delta_peak_per15"]
    out = grp.agg(["count", "mean", "std"]).reset_index()
    out["provisional"] = out["count"] < min_exposures
    return out.sort_values("mean", ascending=False)


def _round(x: Optional[float], nd: int = 1) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)
