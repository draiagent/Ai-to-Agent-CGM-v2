"""LibreView 匯出 CSV 解析（骨架）。

LibreView（FreeStyle Libre）匯出格式：
    第 1 行  報表標題與產生時間
    第 2 行  欄位名，含 "Device Timestamp"、"Record Type"、
             "Historic Glucose mg/dL"、"Scan Glucose mg/dL"、"Serial Number" …
    Record Type: 0=自動歷史值, 1=手動掃描, 其他=事件/註記/胰島素

輸出統一為 cgm 分頁列：ts (Asia/Taipei, ISO8601), glucose_mgdl, sensor_session, source='libre'
"""

from __future__ import annotations

import io
from typing import Union

import pandas as pd

from .align import TZ

HISTORIC_COL = "Historic Glucose mg/dL"
SCAN_COL = "Scan Glucose mg/dL"
TS_COL = "Device Timestamp"
SERIAL_COL = "Serial Number"


def parse_libreview_csv(source: Union[str, bytes, io.IOBase],
                        tz: str = TZ, dayfirst: bool = False) -> pd.DataFrame:
    """解析 LibreView CSV → 標準化 cgm DataFrame。

    Args:
        source: 檔案路徑、bytes 或 file-like。
        tz: 目標時區（naive 時間視為當地時間）。
        dayfirst: LibreView 依匯出帳號地區可能是 DD-MM-YYYY；歐系帳號設 True。

    TODO:
        - 依 Record Type 過濾（目前 historic + scan 都收）。
        - 從 "Serial Number" 推導 sensor_session；若空則以「時間連續 + 序號相同」分段。
        - 併多份匯出時去重（呼叫端負責，或在此加 drop_duplicates）。
    """
    if isinstance(source, (str,)):
        raw = open(source, "r", encoding="utf-8").read()
    elif isinstance(source, bytes):
        raw = source.decode("utf-8")
    else:
        raw = source.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

    # 跳過第 1 行報表標題
    body = raw.split("\n", 1)[1]
    df = pd.read_csv(io.StringIO(body))

    glucose = df.get(HISTORIC_COL)
    if glucose is None:
        glucose = df.get(SCAN_COL)
    else:
        glucose = glucose.fillna(df.get(SCAN_COL))

    out = pd.DataFrame({
        "ts": pd.to_datetime(df[TS_COL], dayfirst=dayfirst, errors="coerce"),
        "glucose_mgdl": pd.to_numeric(glucose, errors="coerce"),
        "sensor_session": df.get(SERIAL_COL, "unknown").astype(str),
    })
    out = out.dropna(subset=["ts", "glucose_mgdl"])
    out["ts"] = out["ts"].dt.tz_localize(tz)
    out["ts"] = out["ts"].dt.tz_convert(tz).map(lambda t: t.isoformat())
    out["source"] = "libre"
    out = out.drop_duplicates(subset=["ts", "sensor_session"]).reset_index(drop=True)
    return out
