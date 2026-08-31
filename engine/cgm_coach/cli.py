"""進入點：python -m cgm_coach <command>

commands:
    weekly-report   讀 Sheets → 對齊分析 → 產出週報
    import-libre     解析 LibreView CSV → 寫入 cgm 分頁
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .config import Config


def cmd_weekly_report(args: argparse.Namespace) -> int:
    from . import align, flexibility, report, sheets

    cfg = Config.load(args.config)
    meals = sheets.read_meals(cfg)
    cgm = sheets.read_cgm(cfg)
    context = sheets.read_context(cfg)  # noqa: F841  (TODO: 餵入排除規則的情境校正)

    meals["t0"] = pd.to_datetime(meals["t0"], errors="coerce")
    if args.since:
        meals = meals[meals["t0"] >= pd.Timestamp(args.since, tz=cfg.tz)]
    if args.until:
        meals = meals[meals["t0"] < pd.Timestamp(args.until, tz=cfg.tz)]

    analyzed = align.analyze_all(meals, cgm)
    ranking = align.food_ranking(analyzed, meals)
    flex = flexibility.panel(cgm)
    safety = flexibility.safety_events(cgm)

    md = report.build_markdown(
        analyzed, ranking, flex, safety,
        since=args.since or "—", until=args.until or "—",
    )
    out = report.write_report(md, cfg.report_out_dir)
    report.plot_overlays(analyzed, cgm, Path(cfg.report_out_dir))
    print(f"週報已寫入：{out}")
    return 0


def cmd_import_libre(args: argparse.Namespace) -> int:
    from . import libre, sheets

    cfg = Config.load(args.config)
    rows = libre.parse_libreview_csv(args.csv, tz=cfg.tz, dayfirst=cfg.libre_dayfirst)
    n = sheets.append_cgm(cfg, rows)
    print(f"寫入 cgm 分頁 {n} 筆")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cgm_coach")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    wr = sub.add_parser("weekly-report")
    wr.add_argument("--since", help="YYYY-MM-DD")
    wr.add_argument("--until", help="YYYY-MM-DD")
    wr.set_defaults(func=cmd_weekly_report)

    il = sub.add_parser("import-libre")
    il.add_argument("csv", help="LibreView 匯出 CSV 路徑")
    il.set_defaults(func=cmd_import_libre)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
