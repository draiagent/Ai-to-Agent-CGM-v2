# n8n 工作流設定

匯入 `cgm-coach.workflow.json` 後，需完成以下設定才能啟用。

## 1. 憑證（Credentials）

| 憑證 | 用途 | 設定 |
|------|------|------|
| Google Drive OAuth2 | 歸檔餐點照片、讀取 CGM CSV | n8n → Credentials → Google Drive OAuth2 API |
| Google Sheets OAuth2 | 寫入 `meals` / `cgm` 分頁 | 同上，Google Sheets OAuth2 API |

匯入後，3 個標記 `"id": "REPLACE"` 的節點需在 UI 重新綁定上述憑證。

## 2. 環境變數（Settings → Variables 或部署環境）

| 變數 | 說明 |
|------|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API channel access token |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `GEMINI_MODEL` | 選填，預設 `gemini-2.5-flash` |
| `SHEET_ID` | Google Sheets 試算表 ID |
| `DRIVE_MEALS_FOLDER_ID` | 照片歸檔資料夾 ID |
| `DRIVE_CGM_FOLDER_ID` | 放 LibreView 匯出 CSV 的資料夾 ID |

## 3. LINE 設定

1. LINE Developers → Messaging API channel。
2. Webhook URL 設為 n8n webhook 的 production URL：`https://<你的 n8n>/webhook/line-webhook`
3. 開啟 "Use webhook"，關閉自動回覆訊息。

## 4. Google Sheets 分頁

先手動建立試算表，三個分頁與標題列（順序需與 `../README.md` §9 一致）：

- `meals`：`meal_id, t0, note, items_json, carb_g, net_carb_g, protein_g, fat_g, fiber_g, gi_est, gl_est, eating_order, post_meal_activity, confidence, user_confirmed, image_url, source_user`
- `cgm`：`ts, glucose_mgdl, sensor_session, source`
- `context`：`date, sleep_hours, stress_subjective, hrv, notes`

## 5. 工作流結構

**照片路徑（webhook 觸發）**

```
LINE Webhook → Parse LINE Event → Is Image?
  ├─ true  → LINE Get Image Content → Archive Image to Drive
  │          → Build Gemini Prompt → Gemini — Estimate Macros
  │          → Build meals Row → Append meals Row
  │          → LINE Reply — Confirm Card → Respond 200
  └─ false → Non-image → skip → Respond 200
```

**CGM 路徑（每日 01:30 排程）**

```
CGM CSV — Daily 01:30 → List CGM CSV Files → Download CSV
  → Parse LibreView CSV → Append cgm Rows
```

## 6. 待補（TODO）

- **一鍵校正 postback**：目前 workflow 只送出確認卡片，未含接收 `postback`（✅／✏️減半／✏️加倍）的第二個 webhook。需新增 `line-postback` webhook → 依 `data` 調整 `meals` 該列的 `portion_g` / `carb_g` 並設 `user_confirmed=true`。
- **個人常吃食物表覆蓋**：`Build meals Row` 節點的 `PERSONAL_TABLE` 目前是空物件。接一個讀 `personal_food_table` 分頁的 Google Sheets 節點，對品項名做碳水覆蓋。
- **LibreView 日期格式**：`Parse LibreView CSV` 假設 `MM-DD-YYYY HH:MM`，依實際匯出地區調整（與 `engine/cgm_coach/libre.py` 的 `dayfirst` 保持一致）。
- **去重**：`Append cgm Rows` 每日全量 append 會重複。改為先讀現有 `ts` 集合再過濾，或改用「清空後重寫近 N 天」策略。
