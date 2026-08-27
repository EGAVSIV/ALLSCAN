from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import scanner_engine as eng
from data_loader import load_data, trim_df_to_date, TIMEFRAME_FOLDERS

app=FastAPI(title="MULTIS Local Scanner")
app.add_middleware(CORSMiddleware, allow_origins=["https://allscans.raosab.in"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

class ScanRequest(BaseModel):
    scanner:str
    timeframe:str="Daily"
    analysis_date:str|None=None
    symbol:str|None=None

def _json(v):
    if isinstance(v,(pd.Timestamp,)): return v.isoformat()
    if hasattr(v,"item"):
        try:return v.item()
        except:pass
    return v

def _run(req):
    data=load_data(req.timeframe)
    if req.symbol:
        data={req.symbol.upper():data.get(req.symbol.upper())}
    data={k:v for k,v in data.items() if v is not None}
    if not data: return []
    all_tfs={req.timeframe:data}
    for tf in ("1 Hour","Daily","Weekly","Monthly"):
        if tf not in all_tfs:
            try: all_tfs[tf]=load_data(tf)
            except Exception: all_tfs[tf]={}
    rows=[]
    for sym,df in data.items():
        df=trim_df_to_date(df,req.analysis_date)
        if df is None: continue
        try:
            result=eng.run_all_scanners_for_symbol(sym,df,req.timeframe,req.analysis_date,all_tfs)
            if result.get(req.scanner,False):
                rows.append({"Symbol":sym,"Scanner":req.scanner,"Result":"Yes"})
        except Exception as e:
            continue
    return rows

@app.get("/timeframes")
def timeframes(): return list(TIMEFRAME_FOLDERS)

@app.get("/symbols/{timeframe}")
def symbols(timeframe:str): return sorted(load_data(timeframe).keys())

@app.get("/status")
def status():
    return {"service":"MULTIS PC Scanner","data":{tf:len(load_data(tf)) for tf in TIMEFRAME_FOLDERS}}

@app.post("/scan")
def scan(req:ScanRequest):
    if req.timeframe not in TIMEFRAME_FOLDERS: raise HTTPException(400,"Invalid timeframe")
    return {"scanner":req.scanner,"timeframe":req.timeframe,"analysis_date":req.analysis_date,"rows":_run(req)}

@app.post("/matrix")
def matrix(req:ScanRequest):
    if not req.symbol: raise HTTPException(400,"symbol is required")
    data=load_data(req.timeframe); sym=req.symbol.upper()
    if sym not in data: raise HTTPException(404,"Symbol not found")
    df=trim_df_to_date(data[sym],req.analysis_date)
    all_tfs={req.timeframe:data}
    for tf in ("1 Hour","Daily","Weekly","Monthly"):
        if tf not in all_tfs:
            try: all_tfs[tf]=load_data(tf)
            except: all_tfs[tf]={}
    r=eng.run_all_scanners_for_symbol(sym,df,req.timeframe,req.analysis_date,all_tfs)
    return {"symbol":sym,"rows":[{"Scanner":k,"Result":"Yes" if v else "No"} for k,v in r.items()]}
