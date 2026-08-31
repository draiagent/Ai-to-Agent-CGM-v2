"""Google Sheets 讀寫（骨架）。

用服務帳號（Service Account）授權，把試算表分享給該服務帳號 email。
金鑰路徑由 config.service_account_json 指定，不進版控。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .config import Config

MEALS_SHEET = "meals"
CGM_SHEET = "cgm"
CONTEXT_SHEET = "context"
FOOD_TABLE_SHEET = "personal_food_table"


def _client(cfg: "Config"):
    """回傳 gspread client。"""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(cfg.service_account_json, scopes=scopes)
    return gspread.authorize(creds)


def _read_sheet(cfg: "Config", name: str) -> pd.DataFrame:
    gc = _client(cfg)
    ws = gc.open_by_key(cfg.sheet_id).worksheet(name)
    return pd.DataFrame(ws.get_all_records())


def read_meals(cfg: "Config") -> pd.DataFrame:
    df = _read_sheet(cfg, MEALS_SHEET)
    for col in ("carb_g", "net_carb_g", "protein_g", "fat_g", "fiber_g", "gi_est", "gl_est", "confidence"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_cgm(cfg: "Config") -> pd.DataFrame:
    df = _read_sheet(cfg, CGM_SHEET)
    if "glucose_mgdl" in df:
        df["glucose_mgdl"] = pd.to_numeric(df["glucose_mgdl"], errors="coerce")
    return df


def read_context(cfg: "Config") -> pd.DataFrame:
    return _read_sheet(cfg, CONTEXT_SHEET)


def read_personal_food_table(cfg: "Config") -> list[dict]:
    """個人常吃食物表，回傳 list[dict] 供 foodtable.apply_overrides 使用。"""
    df = _read_sheet(cfg, FOOD_TABLE_SHEET)
    return df.to_dict("records")


def append_cgm(cfg: "Config", rows: pd.DataFrame) -> int:
    """把新 cgm 列 append 到分頁；回傳寫入筆數。

    TODO: 先讀既有 (ts, sensor_session) 集合再過濾，避免重複。
    """
    gc = _client(cfg)
    ws = gc.open_by_key(cfg.sheet_id).worksheet(CGM_SHEET)
    values = rows[["ts", "glucose_mgdl", "sensor_session", "source"]].values.tolist()
    ws.append_rows(values, value_input_option="USER_ENTERED")
    return len(values)
