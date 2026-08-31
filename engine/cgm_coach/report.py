"""週報產出：Markdown + 疊圖 PNG（骨架，Markdown 已可用）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


def _fmt(x, nd=1):
    return "—" if x is None or (isinstance(x, float) and pd.isna(x)) else f"{x:.{nd}f}"


def build_markdown(analyzed: pd.DataFrame, ranking: pd.DataFrame,
                   flex: dict, safety: pd.DataFrame,
                   since: str, until: str) -> str:
    lines: list[str] = []
    lines.append(f"# CGM Coach 週報 · {since} — {until}")
    lines.append(f"\n_產生時間：{datetime.now().isoformat(timespec='seconds')}_\n")

    # 1. 安全提示
    lines.append("## ⚠️ 安全提示")
    if safety.empty:
        lines.append("本週無低血糖事件（< 70 mg/dL）。")
    else:
        n2 = int((safety["level"] == "level2_lt54").sum())
        lines.append(f"本週偵測 {len(safety)} 筆低血糖讀值，其中 Level 2（< 54 mg/dL）{n2} 筆。")
        for _, r in safety.head(10).iterrows():
            lines.append(f"- {r['ts']} · {r['glucose_mgdl']:.0f} mg/dL · {r['level']}")
    flags_txt = []
    if flex.get("cv_pct") is not None and not flex.get("cv_stable", True):
        flags_txt.append(f"CV {flex['cv_pct']}% ≥ 36%（血糖波動偏大）")
    if flex.get("tir_70_180_pct", 100) < 70:
        flags_txt.append(f"TIR {flex.get('tir_70_180_pct')}% < 70%")
    if flags_txt:
        lines.append("\n**建議與新陳代謝科醫師討論：** " + "；".join(flags_txt))

    # 2. 代謝彈性面板
    lines.append("\n## 血糖反應彈性面板")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    for k, label in [
        ("mean_glucose_mgdl", "平均血糖 (mg/dL)"),
        ("gmi_pct", "GMI 估算 A1c (%)"),
        ("cv_pct", "CV%（< 36% 為穩定）"),
        ("tir_70_180_pct", "TIR 70–180 (%)"),
        ("tbr_lt70_pct", "TBR < 70 (%)"),
        ("tar_gt180_pct", "TAR > 180 (%)"),
        ("overnight_mean_mgdl", "隔夜平均 (mg/dL)"),
        ("overnight_cv_pct", "隔夜 CV%"),
    ]:
        lines.append(f"| {label} | {_fmt(flex.get(k))} |")

    # 3. 食物反應排行
    lines.append("\n## 個人化食物反應排行（每 15 g 碳水的 ΔPeak）")
    if ranking.empty:
        lines.append("尚無足夠乾淨資料點。")
    else:
        lines.append("| 食物／餐型 | 曝光數 | ΔPeak/15g mean | SD | 備註 |")
        lines.append("|---|---|---|---|---|")
        for _, r in ranking.iterrows():
            note = "初步觀察" if r["provisional"] else ""
            lines.append(f"| {r['food_key']} | {int(r['count'])} | {_fmt(r['mean'])} | {_fmt(r['std'])} | {note} |")

    # 4. 意外峰值清單
    lines.append("\n## 「意外峰值」清單")
    clean = analyzed[analyzed["is_clean"]]
    if "delta_peak" in clean and not clean.empty:
        hi = clean.sort_values("delta_peak", ascending=False).head(5)
        for _, r in hi.iterrows():
            lines.append(f"- {r['t0']} · ΔPeak {_fmt(r['delta_peak'])} mg/dL · 達峰 {_fmt(r['time_to_peak'])} min · iAUC {_fmt(r['iauc'])}")
    else:
        lines.append("本週無乾淨餐次可分析。")

    # 5. 資料品質
    lines.append("\n## 資料品質")
    total = len(analyzed)
    clean_n = int(analyzed["is_clean"].sum()) if "is_clean" in analyzed else 0
    lines.append(f"- 總餐次：{total}，乾淨餐次：{clean_n}")
    if "flags" in analyzed:
        exploded = analyzed["flags"].fillna("").str.split(",").explode()
        counts = exploded[exploded != ""].value_counts()
        for flag, c in counts.items():
            lines.append(f"- `{flag}`：{int(c)} 筆")

    lines.append("\n---\n_本報告為飲食型態觀察，非醫療診斷或建議。_")
    return "\n".join(lines)


def plot_overlays(analyzed: pd.DataFrame, cgm: pd.DataFrame, out_dir: Path, top_n: int = 5) -> list[Path]:
    """對 ΔPeak 最高的 top_n 餐畫餐後 0–180 分鐘疊圖。

    TODO: 實作 matplotlib 疊圖（x = 分鐘, y = glucose, 標 baseline 與 peak）。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    return []  # 骨架：先回傳空清單


def write_report(md: str, out_dir: str | Path, name: str = "weekly-report.md") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    path.write_text(md, encoding="utf-8")
    return path
