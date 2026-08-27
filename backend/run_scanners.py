from __future__ import annotations
import json, re, shutil, traceback
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from data_loader import load_data, available_timeframes
import scanner_engine as eng

PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULT_ROOT = PROJECT_DIR / "SCANNER_RESULTS"

# Scanner names discovered from the existing Python source.
SCANNERS = [
    "RSI Market Pulse","Volume Shocker","NRB-7 Breakout","Counter Attack",
    "Breakaway Gaps","RSI + ADX","MACD Market Pulse","MACD Normal Divergence",
    "Trend Alignment (EMA)","Pullback to EMA","High Probability Confluence",
    "MACD Hook Up","MACD Hook Down","MACD Histogram Divergence",
    "EMA50 + Stoch Oversold","Dark Cloud Cover","Morning Star (Bottom)",
    "Evening Star (Top)","Bullish GSAS","Bearish GSAS","50 EMA Fake Breakdown",
    "50 EMA Fake Breakout","KDJ BUY (Oversold)","KDJ SELL (Overbought)",
    "Probable Momentum (Consecutive Close)","Camarilla Breakout / Breakdown",
    "CPR Breakout / Breakdown","Inside Bar Breakout","ADX Expansion (Trend Ignition)",
    "Range Expansion Day","Failed Breakout / Breakdown","EMA Compression → Expansion",
    "Top 10 by ATR %","Liquidity Sweep Reversal","Island Reversal",
    "Wyckoff Spring / Upthrust","Smart Money Trap","Bump & Run Reversal",
    "Exhaustion Bar","Shakeout / Trap","Hidden Pivot Reversal","Springer Reversal",
    "RSI + MACD Cross Swing","RSI Swing"
]

def slug(name):
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return s.lower()

def _last_candles(all_tf_data, tf_label, analysis_date=None):
    data = all_tf_data.get(tf_label, {})
    out = {}
    for sym, df in data.items():
        if df is None or df.empty:
            continue
        x = df
        if analysis_date:
            ts = pd.Timestamp(analysis_date)
            x = x[x.index <= ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)]
        if not x.empty:
            out[sym] = x.iloc[-1]
    return out

def _serialize_value(v):
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if hasattr(v, "item"):
        try: return v.item()
        except Exception: pass
    if pd.isna(v) if not isinstance(v, (list,dict,tuple)) else False:
        return None
    return v

def _normalize_rows(result, sym, scanner):
    if result is None or result is False:
        return []
    if isinstance(result, pd.DataFrame):
        rows = result.reset_index().to_dict("records")
    elif isinstance(result, pd.Series):
        rows = [result.to_dict()]
    elif isinstance(result, dict):
        rows = [result]
    elif result is True:
        rows = [{"Symbol": sym, "Scanner": scanner, "Result": "Match"}]
    else:
        rows = [{"Symbol": sym, "Scanner": scanner, "Result": str(result)}]
    final = []
    for row in rows:
        row = {str(k): _serialize_value(v) for k,v in row.items()}
        row.setdefault("Symbol", sym)
        row.setdefault("Scanner", scanner)
        final.append(row)
    return final

def scan_timeframe(timeframe, analysis_date=None):
    primary = load_data(timeframe)
    all_tf = {timeframe: primary}
    for tf in ("15 Min","1 Hour","Daily","Weekly","Monthly"):
        if tf not in all_tf:
            try: all_tf[tf] = load_data(tf)
            except Exception: all_tf[tf] = {}

    # Supply multi-timeframe helper to engines that expect it.
    eng.get_last_candle_by_tf = lambda tf_label, date=None: _last_candles(all_tf, tf_label, date or analysis_date)

    results = {scanner: [] for scanner in SCANNERS}
    errors = []

    for n, (sym, df) in enumerate(primary.items(), start=1):
        if df is None or df.empty:
            continue
        try:
            output = eng.run_all_scanners_for_symbol(
                sym, df, timeframe, analysis_date, all_tf
            )
            if isinstance(output, dict):
                for scanner, value in output.items():
                    if scanner in results and value not in (False, None, "", []):
                        results[scanner].extend(_normalize_rows(value, sym, scanner))
        except Exception as exc:
            errors.append({"symbol": sym, "error": str(exc)})
        if n % 100 == 0:
            print(f"{timeframe}: processed {n}/{len(primary)}")

    generated = datetime.now(timezone.utc).isoformat()
    manifest = {
        "timeframe": timeframe,
        "generated_at": generated,
        "symbols_scanned": len(primary),
        "scanners": {}
    }

    for scanner, rows in results.items():
        folder = RESULT_ROOT / slug(scanner)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{slug(timeframe)}.json"
        payload = {
            "scanner": scanner,
            "timeframe": timeframe,
            "generated_at": generated,
            "symbols_scanned": len(primary),
            "match_count": len(rows),
            "rows": rows
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        manifest["scanners"][scanner] = {"file": str(path.relative_to(PROJECT_DIR)).replace("\\","/"), "match_count": len(rows)}

    return manifest, errors

def main():
    RESULT_ROOT.mkdir(exist_ok=True)
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "timeframes": {}, "errors": []}

    for tf in available_timeframes():
        print(f"\n=== Running {tf} scanners ===")
        try:
            info, errors = scan_timeframe(tf)
            manifest["timeframes"][tf] = info
            manifest["errors"].extend(errors)
        except Exception as exc:
            manifest["errors"].append({"timeframe": tf, "error": traceback.format_exc()})
            print(f"ERROR {tf}: {exc}")

    (RESULT_ROOT/"manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nDONE. Results written to SCANNER_RESULTS/")

if __name__ == "__main__":
    main()
