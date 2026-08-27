from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from data_loader import TIMEFRAME_FOLDERS, load_data
from scanner_engine import (
    SCANNERS,
    run_scanner,
    run_all_scanners_for_symbol,
    trim_df_to_date,
)

# Parent of 'backend' directory (Project Root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "docs" / "data"


def clean_value(value):
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def dataframe_records(df):
    if df is None or df.empty:
        return []
    return [
        {k: clean_value(v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def safe_filename(name: str) -> str:
    return (
        name.replace("/", "-")
        .replace(" ", "_")
        .replace("→", "to")
        .replace("–", "-")
    )


def latest_timestamp_for(data: dict) -> str | None:
    latest = None
    for df in data.values():
        if df is None or df.empty:
            continue
        value = pd.to_datetime(df.index[-1])
        if latest is None or value > latest:
            latest = value
    return latest.isoformat() if latest is not None else None


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    timeframes = list(TIMEFRAME_FOLDERS.keys())
    write_json(OUT_DIR / "timeframes.json", timeframes)
    write_json(OUT_DIR / "scanners.json", SCANNERS)

    last_candles = {}
    symbols_by_tf = {}
    data_cache = {}

    for tf in timeframes:
        print(f"Loading data for {tf} ...")
        data = load_data(tf)
        data_cache[tf] = data
        symbols_by_tf[tf] = sorted(data.keys())
        last_candles[tf] = latest_timestamp_for(data)

    write_json(OUT_DIR / "last-candles.json", last_candles)

    for tf, syms in symbols_by_tf.items():
        write_json(OUT_DIR / "symbols" / f"{tf.replace(' ', '_')}.json", syms)

    anchor_date = date.today()

    # --- Scanner results, per timeframe, per scanner ---
    for tf in timeframes:
        for scanner in SCANNERS:
            name = scanner["name"]
            print(f"Scanning [{tf}] {name} ...")
            df = run_scanner(name, tf, anchor_date, load_data)

            zones = {}
            if name == "RSI Market Pulse" and df is not None and not df.empty and "Zone" in df.columns:
                zones = df["Zone"].astype(str).value_counts().to_dict()

            payload = {
                "status": "success",
                "scanner": name,
                "timeframe": tf,
                "analysis_date": str(anchor_date),
                "total_matches": len(df) if df is not None else 0,
                "zones": zones,
                "results": dataframe_records(df),
            }
            out_file = OUT_DIR / "scan" / tf.replace(" ", "_") / f"{safe_filename(name)}.json"
            write_json(out_file, payload)

    # --- Scanner matrix, per timeframe, per symbol ---
    for tf in timeframes:
        current_data = data_cache[tf]
        for sym, df in current_data.items():
            symbol_df = trim_df_to_date(df, anchor_date)
            if symbol_df is None:
                continue
            matrix_result = run_all_scanners_for_symbol(sym, symbol_df, tf, anchor_date, data_cache)
            payload = {
                "status": "success",
                "symbol": sym,
                "timeframe": tf,
                "analysis_date": str(anchor_date),
                "results": [{"Scanner": k, "Result": bool(v)} for k, v in matrix_result.items()],
            }
            out_file = OUT_DIR / "matrix" / tf.replace(" ", "_") / f"{sym}.json"
            write_json(out_file, payload)

    write_json(OUT_DIR / "meta.json", {"generated_at": datetime.now(timezone.utc).isoformat()})
    print("Static data generation complete.")


if __name__ == "__main__":
    main()
