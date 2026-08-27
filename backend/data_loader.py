from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_DIR

TIMEFRAME_FOLDERS = {
    "15 Min": "stockdata_15",
    "1 Hour": "stockdata_1H",
    "Daily": "stockdata_D",
    "Weekly": "stockdata_W",
    "Monthly": "stockdata_M",
}

def _to_df(payload):
    if isinstance(payload, dict):
        for key in ("data", "records", "candles", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    df = pd.DataFrame(payload)
    if df.empty:
        return None
    df.columns = [str(c).strip().lower() for c in df.columns]
    aliases = {
        "timestamp": "datetime", "date": "datetime", "time": "datetime",
        "o": "open", "h": "high", "l": "low", "c": "close",
        "v": "volume", "vol": "volume"
    }
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns})
    if "datetime" not in df.columns:
        return None
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for c in ("open", "high", "low", "close"):
        if c not in df.columns:
            return None
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    else:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"])
    if df.empty:
        return None
    return df.sort_values("datetime").drop_duplicates("datetime", keep="last").set_index("datetime")

def load_data(timeframe: str) -> dict[str, pd.DataFrame]:
    folder_name = TIMEFRAME_FOLDERS[timeframe]
    folder = DATA_ROOT / folder_name
    if not folder.exists():
        raise FileNotFoundError(f"Missing data folder: {folder}")
    out = {}
    for path in sorted(folder.rglob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            df = _to_df(json.loads(path.read_text(encoding="utf-8")))
            if df is not None and not df.empty:
                out[path.stem.upper()] = df
        except Exception as exc:
            print(f"Skipping {path}: {exc}")
    return out

def available_timeframes() -> list[str]:
    return [tf for tf, folder in TIMEFRAME_FOLDERS.items() if (DATA_ROOT / folder).exists()]
