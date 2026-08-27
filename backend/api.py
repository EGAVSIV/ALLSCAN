from datetime import date
import math
import traceback

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data_loader import (
    TIMEFRAME_FOLDERS,
    clear_cache,
    get_cache_status,
    load_data,
    refresh_timeframe,
)
from scanner_engine import (
    SCANNERS,
    run_all_scanners_for_symbol,
    run_scanner,
    trim_df_to_date,
)

app = FastAPI(
    title="EGAVSIV Multis Scanner API",
    version="1.0.0",
)

# Allowed CORS origins (including local development servers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://allscans.raosab.in",
        "https://egavsiv.github.io",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    scanner: str
    timeframe: str = "Daily"
    analysis_date: date | None = None
    refresh: bool = False


class MatrixRequest(BaseModel):
    symbol: str
    timeframe: str = "Daily"
    analysis_date: date | None = None
    refresh: bool = False


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
        {key: clean_value(value) for key, value in row.items()}
        for row in df.to_dict(orient="records")
    ]


def latest_timestamp(timeframe, refresh=False):
    data = load_data(timeframe, force_refresh=refresh)
    latest = None

    for df in data.values():
        if df is None or df.empty:
            continue
        
        # Ensure timestamp is comparable
        value = pd.to_datetime(df.index[-1])
        if latest is None or value > latest:
            latest = value

    return latest


def resolve_date(timeframe, requested_date=None, refresh=False):
    if requested_date:
        return requested_date

    latest = latest_timestamp(timeframe, refresh=refresh)
    return latest.date() if latest is not None else date.today()


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "EGAVSIV Multis Scanner API",
    }


@app.get("/api/timeframes")
def timeframes():
    return list(TIMEFRAME_FOLDERS.keys())


@app.get("/api/scanners")
def scanners():
    return SCANNERS


@app.get("/api/symbols")
def symbols(timeframe: str = "Daily", refresh: bool = False):
    if timeframe not in TIMEFRAME_FOLDERS:
        raise HTTPException(400, f"Invalid timeframe: {timeframe}")

    try:
        data = load_data(timeframe, force_refresh=refresh)
        return sorted(data.keys())
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/last-candles")
def last_candles(refresh: bool = False):
    result = {}
    for timeframe in TIMEFRAME_FOLDERS:
        latest = latest_timestamp(timeframe, refresh=refresh)
        result[timeframe] = latest.isoformat() if latest is not None else None
    return result


@app.get("/api/cache-status")
def cache_status():
    return get_cache_status()


@app.post("/api/refresh-data")
def refresh_data():
    try:
        clear_cache()
        summary = {}
        for timeframe in TIMEFRAME_FOLDERS:
            data = refresh_timeframe(timeframe)
            summary[timeframe] = {"symbols": len(data)}

        return {"status": "success", "data": summary}
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(500, str(exc))


@app.post("/api/scan")
def scan(request: ScanRequest):
    if request.timeframe not in TIMEFRAME_FOLDERS:
        raise HTTPException(400, f"Invalid timeframe: {request.timeframe}")

    valid = {item["name"] for item in SCANNERS}
    if request.scanner not in valid:
        raise HTTPException(400, f"Invalid scanner: {request.scanner}")

    try:
        if request.refresh:
            refresh_timeframe(request.timeframe)

        anchor_date = resolve_date(
            request.timeframe,
            request.analysis_date,
            refresh=False,
        )

        result_df = run_scanner(
            request.scanner,
            request.timeframe,
            anchor_date,
            load_data,
        )

        zones = {}
        if (
            request.scanner == "RSI Market Pulse"
            and result_df is not None
            and not result_df.empty
            and "Zone" in result_df.columns
        ):
            zones = result_df["Zone"].astype(str).value_counts().to_dict()

        return {
            "status": "success",
            "scanner": request.scanner,
            "timeframe": request.timeframe,
            "analysis_date": str(anchor_date),
            "total_matches": len(result_df) if result_df is not None else 0,
            "zones": zones,
            "results": dataframe_records(result_df),
        }

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(500, str(exc))


@app.post("/api/matrix")
def matrix(request: MatrixRequest):
    if request.timeframe not in TIMEFRAME_FOLDERS:
        raise HTTPException(400, f"Invalid timeframe: {request.timeframe}")

    try:
        if request.refresh:
            refresh_timeframe(request.timeframe)

        anchor_date = resolve_date(
            request.timeframe,
            request.analysis_date,
            refresh=False,
        )

        current_data = load_data(request.timeframe)
        symbol = request.symbol.strip().upper()

        if symbol not in current_data:
            raise HTTPException(404, f"Symbol not found: {symbol}")

        symbol_df = trim_df_to_date(current_data[symbol], anchor_date)
        if symbol_df is None:
            raise HTTPException(400, "Not enough data for selected date")

        # Matrix needs current TF plus higher/required TF data from cache
        data_all_tfs = {tf: load_data(tf, force_refresh=False) for tf in TIMEFRAME_FOLDERS}
        data_all_tfs[request.timeframe] = current_data

        matrix_result = run_all_scanners_for_symbol(
            symbol,
            symbol_df,
            request.timeframe,
            anchor_date,
            data_all_tfs,
        )

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": request.timeframe,
            "analysis_date": str(anchor_date),
            "results": [
                {"Scanner": name, "Result": bool(value)}
                for name, value in matrix_result.items()
            ],
        }

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(500, str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api_2:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
