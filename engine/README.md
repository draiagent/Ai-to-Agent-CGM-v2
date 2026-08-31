# 週報引擎（Python）

方案一分析層：讀 Google Sheets → 以 T0 對齊 CGM → 算 5 指標 + 排除規則 → 產出週報。

## 安裝

```bash
cd engine
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.yaml config.yaml                  # 填入 sheet_id 與服務帳號金鑰路徑
```

Google 服務帳號：在 GCP 建服務帳號 → 下載 JSON 金鑰 → 把 Sheets 試算表「共用」給該服務帳號 email（檢視或編輯權限）。

## 使用

```bash
# 匯入一份 LibreView 匯出 CSV 到 cgm 分頁
python -m cgm_coach import-libre ~/Downloads/LibreView_export.csv

# 產出指定期間週報（寫到 report_out_dir）
python -m cgm_coach weekly-report --since 2026-08-25 --until 2026-09-01
```

## 模組

| 檔案 | 狀態 | 內容 |
|------|------|------|
| `cgm_coach/align.py` | ✅ 已實作 | `compute_baseline` / `delta_peak` / `incremental_auc`（Wolever）/ `time_to_recovery` / `exclusion_flags` / `analyze_all` / `food_ranking` |
| `cgm_coach/flexibility.py` | ✅ 已實作 | `panel`（Mean/GMI/CV%/TIR/TBR/TAR/隔夜）、`safety_events`（低血糖清單） |
| `cgm_coach/report.py` | 🟡 Markdown 可用 | `build_markdown` 完整；`plot_overlays` 待補 matplotlib 疊圖 |
| `cgm_coach/libre.py` | 🟡 骨架 | LibreView CSV 解析；日期格式 `dayfirst` 需依帳號地區確認 |
| `cgm_coach/sheets.py` | 🟡 骨架 | gspread 讀寫；`append_cgm` 去重待補 |
| `cgm_coach/config.py` / `cli.py` | ✅ | YAML 設定與進入點 |

## 測試

```bash
python -m pytest -q
```

`tests/test_align.py` 用合成血糖曲線驗證：乾淨餐指標、`contaminated` / `not_recovered_3h` 旗標、iAUC 的 Wolever 截負值行為。

## 待補（TODO）

- `report.plot_overlays`：對 ΔPeak 前 5 名的餐畫餐後 0–180 分鐘疊圖（標 baseline / peak）。
- `context` 分頁餵入排除規則：睡眠不足、壓力高的餐次加註（目前只讀不用）。
- `align.food_ranking` 的 `food_key`：目前用 `note` 佔位，應改為品項名或餐型標籤。
- `sheets.append_cgm` 去重；大量資料改批次讀寫。
- 指標參數從 `config.overrides` 實際覆寫 `align` 模組常數。
