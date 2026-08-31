"""設定載入（YAML）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    sheet_id: str = ""
    service_account_json: str = ""          # Google 服務帳號金鑰路徑（不進版控）
    tz: str = "Asia/Taipei"
    report_out_dir: str = "./out"
    libre_dayfirst: bool = False
    # 指標參數覆寫（留空則用 align.py 預設）
    overrides: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
