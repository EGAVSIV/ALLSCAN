from __future__ import annotations
import os
import numpy as np
import pandas as pd
import talib

try:
    import streamlit as st
except ImportError:
    class _NoOpCache:
        def __call__(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    class _StreamlitShim:
        cache_data = _NoOpCache()

    st = _StreamlitShim()

SAFE_COLS = [
    "Symbol", "Signal", "Trend", "State", "Setup", "Divergence",
    "RSI", "Zone", "Confluence", "Bias", "Probability", "TV_Link",
]
BULL_KEYWORDS = ["Bullish", "BUY", "Breakout", "Uptrend", "Momentum"]
BEAR_KEYWORDS = ["Bearish", "SELL", "Breakdown", "Downtrend"]


def make_tradingview_link(sym: str) -> str:
    base = 'https://in.tradingview.com/chart/LqUZraZ9/'
    return f'{base}?symbol=NSE%3A{sym}'


def empty_result_df():
    return pd.DataFrame({c: [] for c in SAFE_COLS})


def get_last_candle_by_tf(folder_path: str):
    last_dt = None
    if not os.path.isdir(folder_path):
        return None
    for f in os.listdir(folder_path):
        if not f.endswith('.parquet'):
            continue
        try:
            df = pd.read_parquet(os.path.join(folder_path, f))
            if df.empty:
                continue
            if isinstance(df.index, pd.DatetimeIndex):
                dt = df.index[-1]
            elif 'datetime' in df.columns:
                dt = pd.to_datetime(df['datetime']).iloc[-1]
            else:
                continue
            if dt.tzinfo is None:
                dt = dt.tz_localize('UTC')
            else:
                dt = dt.tz_convert('UTC')
            dt = dt.tz_convert('Asia/Kolkata')
            if last_dt is None or dt > last_dt:
                last_dt = dt
        except Exception:
            continue
    return last_dt


def trim_df_to_date(df: pd.DataFrame, anchor_date):
    if df is None or df.empty:
        return None
    df = df.copy()
    if isinstance(df.index, pd.DatetimeIndex):
        df = df[df.index.date <= anchor_date]
    elif 'datetime' in df.columns:
        df = df[df['datetime'].dt.date <= anchor_date]
    if len(df) < 120:
        return None
    return df


def rsi_market_pulse(df):
    if len(df) < 14:
        return None
    rsi = talib.RSI(df['close'], 14).iloc[-1]
    if rsi > 60:
        zone = 'RSI > 60'
    elif rsi < 40:
        zone = 'RSI < 40'
    else:
        zone = 'RSI 40–60'
    return (round(rsi, 2), zone)


def volume_shocker(df):
    if len(df) < 20:
        return False
    vol_sma = df['volume'].rolling(10).mean()
    last, prev = (df.iloc[-1], df.iloc[-2])
    return last['volume'] > 2 * vol_sma.iloc[-1] and prev['close'] * 0.95 <= last['close'] <= prev['close'] * 1.05


def nrb_7(df):
    if len(df) < 20:
        return None
    base = df.iloc[-7]
    inside = df.iloc[-6:-1]
    last = df.iloc[-1]
    base_high = base['high']
    base_low = base['low']
    cond_high_low = inside['high'].max() <= base_high and inside['low'].min() >= base_low
    cond_open_close = inside['open'].max() <= base_high and inside['open'].min() >= base_low and (inside['close'].max() <= base_high) and (inside['close'].min() >= base_low)
    is_nrb = cond_high_low and cond_open_close
    if not is_nrb:
        return None
    avg_vol = df['volume'].rolling(10).mean().iloc[-2]
    if last['volume'] < 1.5 * avg_vol:
        return None
    if last['close'] > base_high:
        return 'NRB-7 Bullish Breakout + Volume'
    if last['close'] < base_low:
        return 'NRB-7 Bearish Breakdown + Volume'
    return None


def counter_attack(df):
    if len(df) < 2:
        return None
    prev, curr = (df.iloc[-2], df.iloc[-1])
    mid = (prev['open'] + prev['close']) / 2
    if prev['close'] < prev['open'] and curr['close'] > curr['open']:
        if curr['open'] < prev['close'] and curr['close'] >= mid:
            return 'Bullish'
    if prev['close'] > prev['open'] and curr['close'] < curr['open']:
        if curr['open'] > prev['close'] and curr['close'] <= mid:
            return 'Bearish'
    return None


def breakaway_gap(df):
    if len(df) < 50:
        return None
    df = df.copy()
    df['EMA20'] = talib.EMA(df['close'], 20)
    df['EMA50'] = talib.EMA(df['close'], 50)
    prev, curr = (df.iloc[-2], df.iloc[-1])
    if curr['open'] > prev['high'] * 1.005 and curr['low'] > prev['high']:
        if curr['EMA20'] < curr['EMA50']:
            return 'Bullish Breakaway Gap'
    if curr['open'] < prev['low'] * 0.995 and curr['high'] < prev['low']:
        if curr['EMA20'] > curr['EMA50']:
            return 'Bearish Breakaway Gap'
    return None


def rsi_adx(df):
    if len(df) < 20:
        return None
    rsi = talib.RSI(df['close'], 14).iloc[-1]
    adx = talib.ADX(df['high'], df['low'], df['close'], 14).iloc[-1]
    if adx > 50 and rsi < 20:
        return 'Bullish Reversal'
    if adx > 50 and rsi > 80:
        return 'Probabale Bearish Reversal'
    return None


def rsi_wm(df_tf, df_w, df_m):
    r_tf = talib.RSI(df_tf['close'], 14).iloc[-1]
    r_w = talib.RSI(df_w['close'], 14).iloc[-1]
    r_m = talib.RSI(df_m['close'], 14).iloc[-1]
    if r_w > 60 and r_m > 60 and (r_tf < 40):
        return 'Bullish WM Reversal'
    if r_w < 40 and r_m < 40 and (r_tf > 60):
        return 'Bearish WM Reversal'
    return None


def macd_market_pulse(df):
    if len(df) < 30:
        return None
    macd, signal, _ = talib.MACD(df['close'], 12, 26, 9)
    m, s = (macd.iloc[-1], signal.iloc[-1])
    pm = macd.iloc[-2]
    if m > 0 and m > s and (m > pm):
        return 'Strong Bullish'
    if m > 0 and m > s and (m < pm):
        return 'Bullish Cooling'
    if m > 0 and m < s and (m > pm):
        return 'Bullish Reversal Watch'
    if m > 0 and m < s and (m < pm):
        return 'Weak Bullish'
    if m < 0 and m > s and (m > pm):
        return 'Bearish Reversal Watch'
    if m < 0 and m > s and (m < pm):
        return 'Weak Bearish'
    if m < 0 and m < s and (m > pm):
        return 'Bearish Recovery Attempt'
    if m < 0 and m < s and (m < pm):
        return 'Strong Bearish'
    return None


def macd_normal_divergence(df, lookback=30):
    if len(df) < lookback:
        return None
    macd, _, _ = talib.MACD(df['close'], 12, 26, 9)
    price_low1 = df['low'].iloc[-lookback:-15].min()
    price_low2 = df['low'].iloc[-15:].min()
    macd_low1 = macd.iloc[-lookback:-15].min()
    macd_low2 = macd.iloc[-15:].min()
    if price_low2 < price_low1 and macd_low2 > macd_low1:
        return 'Bullish ND'
    price_high1 = df['high'].iloc[-lookback:-15].max()
    price_high2 = df['high'].iloc[-15:].max()
    macd_high1 = macd.iloc[-lookback:-15].max()
    macd_high2 = macd.iloc[-15:].max()
    if price_high2 > price_high1 and macd_high2 < macd_high1:
        return 'Bearish ND'
    return None


def macd_rd(df, df_htf):
    if len(df) < 60 or len(df_htf) < 30:
        return None
    macd, signal, _ = talib.MACD(df['close'], 12, 26, 9)
    latest = macd.iloc[-1]
    prev = macd.iloc[-2]
    sig = signal.iloc[-1]
    max60 = macd.rolling(60).max().iloc[-1]
    macd_htf, _, _ = talib.MACD(df_htf['close'], 12, 26, 9)
    macd_htf_val = macd_htf.iloc[-1]
    macd_htf_now = macd_htf.iloc[-1]
    macd_htf_prev = macd_htf.iloc[-2]
    macd_htf_uptick = macd_htf_now > macd_htf_prev
    ema50_ltf = talib.EMA(df['close'], 50).iloc[-1]
    ema50_htf = talib.EMA(df_htf['close'], 50).iloc[-1]
    close_ltf = df['close'].iloc[-1]
    close_htf = df_htf['close'].iloc[-1]
    ema_condition = close_ltf > ema50_ltf and close_htf > ema50_htf
    if latest > prev and latest > 0 and (sig < latest) and (macd_htf_val > 0) and (max60 > 0) and (latest / max60 < 0.25) and ema_condition and macd_htf_uptick:
        return 'MACD RD (Compression + Trend Aligned)'
    return None


def third_wave_finder(df, lookback_cross=50, tolerance=0.02):
    if len(df) < lookback_cross + 5:
        return False
    close = df['close']
    ema20 = talib.EMA(close, 20)
    ema50 = talib.EMA(close, 50)
    cross_idx = None
    for i in range(len(close) - 1, 0, -1):
        if ema20.iloc[i] > ema50.iloc[i] and ema20.iloc[i - 1] <= ema50.iloc[i - 1]:
            cross_idx = i
            break
    if cross_idx is None:
        return False
    start_idx = max(0, cross_idx - lookback_cross)
    pre_ema20 = ema20.iloc[start_idx:cross_idx]
    pre_ema50 = ema50.iloc[start_idx:cross_idx]
    if pre_ema20.empty:
        return False
    bearish_ratio = (pre_ema20 < pre_ema50).mean()
    if bearish_ratio < 0.7:
        return False
    ema50_now = ema50.iloc[-1]
    price_now = close.iloc[-1]
    if ema50_now == 0 or np.isnan(ema50_now):
        return False
    dist = abs(price_now - ema50_now) / ema50_now
    if dist > tolerance:
        return False
    if ema20.iloc[-1] <= ema50.iloc[-1]:
        return False
    return True


def c_wave_finder(df, lookback_cross=50, tolerance=0.02):
    if len(df) < lookback_cross + 5:
        return False
    close = df['close']
    ema20 = talib.EMA(close, 20)
    ema50 = talib.EMA(close, 50)
    cross_idx = None
    for i in range(len(close) - 1, 0, -1):
        if ema20.iloc[i] < ema50.iloc[i] and ema20.iloc[i - 1] >= ema50.iloc[i - 1]:
            cross_idx = i
            break
    if cross_idx is None:
        return False
    start_idx = max(0, cross_idx - lookback_cross)
    pre_ema20 = ema20.iloc[start_idx:cross_idx]
    pre_ema50 = ema50.iloc[start_idx:cross_idx]
    if pre_ema20.empty:
        return False
    bullish_ratio = (pre_ema20 > pre_ema50).mean()
    if bullish_ratio < 0.7:
        return False
    ema50_now = ema50.iloc[-1]
    price_now = close.iloc[-1]
    if ema50_now == 0 or np.isnan(ema50_now):
        return False
    dist = abs(price_now - ema50_now) / ema50_now
    if dist > tolerance:
        return False
    if ema20.iloc[-1] >= ema50.iloc[-1]:
        return False
    return True


def macd_peak_bearish_divergence(df):
    if len(df) < 80:
        return None
    macd, _, _ = talib.MACD(df['close'], 12, 26, 9)
    old_slice = slice(-60, -30)
    new_slice = slice(-30, None)
    price_high1 = df['high'].iloc[old_slice].max()
    price_high2 = df['high'].iloc[new_slice].max()
    idx1 = df['high'].iloc[old_slice].idxmax()
    idx2 = df['high'].iloc[new_slice].idxmax()
    macd_high1 = macd.loc[idx1]
    macd_high2 = macd.loc[idx2]
    if price_high2 > price_high1 and macd_high2 < macd_high1:
        return 'Bearish MACD Peak Divergence'
    return None


def macd_base_bullish_divergence(df):
    if len(df) < 80:
        return None
    macd, _, _ = talib.MACD(df['close'], 12, 26, 9)
    price_low1 = df['low'].iloc[-60:-30].min()
    price_low2 = df['low'].iloc[-30:].min()
    macd_low1 = macd.iloc[-60:-30].min()
    macd_low2 = macd.iloc[-30:].min()
    if price_low2 < price_low1 and macd_low2 > macd_low1:
        return 'Bullish MACD Base Divergence'
    return None


def trend_alignment(df):
    if len(df) < 100:
        return None
    ema20 = talib.EMA(df['close'], 20)
    ema50 = talib.EMA(df['close'], 50)
    ema100 = talib.EMA(df['close'], 100)
    if ema20.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]:
        return 'Strong Uptrend'
    if ema20.iloc[-1] < ema50.iloc[-1] < ema100.iloc[-1]:
        return 'Strong Downtrend'
    return None


def pullback_to_ema(df):
    if len(df) < 60:
        return None
    ema20 = talib.EMA(df['close'], 20)
    ema50 = talib.EMA(df['close'], 50)
    last = df.iloc[-1]
    if ema20.iloc[-1] > ema50.iloc[-1]:
        if last['low'] <= ema20.iloc[-1] and last['close'] > ema20.iloc[-1]:
            return 'Bullish EMA Pullback'
    if ema20.iloc[-1] < ema50.iloc[-1]:
        if last['high'] >= ema20.iloc[-1] and last['close'] < ema20.iloc[-1]:
            return 'Bearish EMA Pullback'
    return None


def confluence_setup(df):
    if len(df) < 60:
        return None
    rsi = talib.RSI(df['close'], 14).iloc[-1]
    macd, sig, _ = talib.MACD(df['close'], 12, 26, 9)
    ema20 = talib.EMA(df['close'], 20)
    ema50 = talib.EMA(df['close'], 50)
    if rsi > 50 and macd.iloc[-1] > sig.iloc[-1] and (ema20.iloc[-1] > ema50.iloc[-1]):
        return 'Bullish Confluence'
    if rsi < 50 and macd.iloc[-1] < sig.iloc[-1] and (ema20.iloc[-1] < ema50.iloc[-1]):
        return 'Bearish Confluence'
    return None


def macd_hook_up(df):
    if len(df) < 35:
        return None
    macd, signal, hist = talib.MACD(df['close'], 12, 26, 9)
    if macd.iloc[-1] > 0 and macd.iloc[-1] > signal.iloc[-1] and (macd.iloc[-2] > signal.iloc[-2]) and (macd.iloc[-2] < macd.iloc[-3]) and (macd.iloc[-1] > macd.iloc[-2]) and (hist.iloc[-1] > hist.iloc[-2]):
        return 'MACD Hook Up'
    return None


def macd_hook_down(df):
    if len(df) < 35:
        return None
    macd, signal, hist = talib.MACD(df['close'], 12, 26, 9)
    if macd.iloc[-1] < 0 and macd.iloc[-1] < signal.iloc[-1] and (macd.iloc[-2] < signal.iloc[-2]) and (macd.iloc[-2] > macd.iloc[-3]) and (macd.iloc[-1] < macd.iloc[-2]) and (hist.iloc[-1] < hist.iloc[-2]):
        return 'MACD Hook Down'
    return None


def macd_histogram_divergence(df):
    if len(df) < 50:
        return None
    _, _, hist = talib.MACD(df['close'], 12, 26, 9)
    price_low1 = df['low'].iloc[-40:-20].min()
    price_low2 = df['low'].iloc[-20:].min()
    hist_low1 = hist.iloc[-40:-20].min()
    hist_low2 = hist.iloc[-20:].min()
    if price_low2 < price_low1 and hist_low2 > hist_low1:
        return 'Bullish Histogram Divergence'
    price_high1 = df['high'].iloc[-40:-20].max()
    price_high2 = df['high'].iloc[-20:].max()
    hist_high1 = hist.iloc[-40:-20].max()
    hist_high2 = hist.iloc[-20:].max()
    if price_high2 > price_high1 and hist_high2 < hist_high1:
        return 'Bearish Histogram Divergence'
    return None


def ema50_stoch_oversold(df):
    if len(df) < 50:
        return None
    ema50 = talib.EMA(df['close'], 50)
    slowk, slowd = talib.STOCH(df['high'], df['low'], df['close'], fastk_period=14, slowk_period=3, slowd_period=3)
    price = df['close'].iloc[-1]
    ema_val = ema50.iloc[-1]
    near_ema = abs(price - ema_val) / ema_val <= 0.005
    stoch_cross = slowk.iloc[-2] < slowd.iloc[-2] and slowk.iloc[-1] > slowd.iloc[-1] and (slowk.iloc[-1] < 20)
    if near_ema and stoch_cross:
        return 'EMA50 + Stoch Oversold Buy'
    return None


def dark_cloud_cover(df):
    if len(df) < 15:
        return None
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if prev['close'] <= prev['open']:
        return None
    rsi = talib.RSI(df['close'], 14)
    if rsi.iloc[-2] <= 60:
        return None
    if curr['close'] >= curr['open']:
        return None
    if curr['open'] <= prev['close']:
        return None
    mid = (prev['open'] + prev['close']) / 2
    if curr['close'] >= mid:
        return None
    return 'Dark Cloud Cover (Bearish | RSI>60)'


def morning_star_bottom(df):
    if len(df) < 60:
        return None
    ema50 = talib.EMA(df['close'], 50)
    if df['close'].iloc[-1] > ema50.iloc[-1]:
        return None
    pattern = talib.CDLMORNINGSTAR(df['open'], df['high'], df['low'], df['close']).iloc[-1]
    if pattern > 0:
        return 'Morning Star (Bottom)'
    return None


def evening_star_top(df):
    if len(df) < 60:
        return None
    ema50 = talib.EMA(df['close'], 50)
    if df['close'].iloc[-1] < ema50.iloc[-1]:
        return None
    pattern = talib.CDLEVENINGSTAR(df['open'], df['high'], df['low'], df['close']).iloc[-1]
    if pattern < 0:
        return 'Evening Star (Top)'
    return None


def bullish_gsas(df_tf, df_htf):
    rsi = talib.RSI(df_tf['close'], 14)
    adx = talib.ADX(df_tf['high'], df_tf['low'], df_tf['close'], 14)
    ubb, _, _ = talib.BBANDS(df_tf['close'], 20)
    macd_htf, sig_htf, _ = talib.MACD(df_htf['close'], 12, 26, 9)
    ema20_htf = talib.EMA(df_htf['close'], 20)
    if rsi.iloc[-1] > 60 and ubb.iloc[-1] > ubb.iloc[-2] and (adx.iloc[-1] > adx.iloc[-2]) and (adx.iloc[-2] < adx.iloc[-3]) and (macd_htf.iloc[-1] > sig_htf.iloc[-1]) and (df_htf['close'].iloc[-1] > ema20_htf.iloc[-1]):
        return 'Bullish GSAS'
    return None


def bearish_gsas(df_tf, df_htf):
    rsi = talib.RSI(df_tf['close'], 14)
    adx = talib.ADX(df_tf['high'], df_tf['low'], df_tf['close'], 14)
    _, _, lbb = talib.BBANDS(df_tf['close'], 20)
    macd_htf, sig_htf, _ = talib.MACD(df_htf['close'], 12, 26, 9)
    ema20_htf = talib.EMA(df_htf['close'], 20)
    if rsi.iloc[-1] < 60 and lbb.iloc[-1] < lbb.iloc[-2] and (adx.iloc[-1] > adx.iloc[-2]) and (adx.iloc[-2] < adx.iloc[-3]) and (macd_htf.iloc[-1] < sig_htf.iloc[-1]) and (df_htf['close'].iloc[-1] < ema20_htf.iloc[-1]):
        return 'Bearish GSAS'
    return None


def rsi_swing(df):
    if len(df) < 20:
        return None
    rsi = talib.RSI(df['close'], 14)
    rsi_prev = rsi.iloc[-2]
    rsi_curr = rsi.iloc[-1]
    if rsi_prev < 40 and rsi_curr > 40:
        return 'RSI Bullish Swing'
    if rsi_prev > 60 and rsi_curr < 60:
        return 'RSI Bearish Swing'
    return None


def ema50_fake_breakdown(df):
    if len(df) < 55:
        return None
    df = df.copy()
    df['EMA20'] = talib.EMA(df['close'], 20)
    df['EMA50'] = talib.EMA(df['close'], 50)
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if curr['close'] > curr['EMA50'] and prev['close'] < prev['EMA50'] and (curr['EMA20'] > curr['EMA50']):
        return '50 EMA Fake Breakdown'
    return None


def ema50_fake_breakout(df):
    if len(df) < 55:
        return None
    df = df.copy()
    df['EMA20'] = talib.EMA(df['close'], 20)
    df['EMA50'] = talib.EMA(df['close'], 50)
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if curr['close'] < curr['EMA50'] and prev['close'] > prev['EMA50'] and (curr['EMA20'] < curr['EMA50']):
        return '50 EMA Fake Breakout'
    return None


def kdj(df, period=9, signal=3):
    low_min = df['low'].rolling(period).min()
    high_max = df['high'].rolling(period).max()
    rng = (high_max - low_min).replace(0, np.nan)
    rsv = 100 * (df['close'] - low_min) / rng
    rsv = rsv.clip(lower=0, upper=100)

    def bcwsma(series, length, m=1):
        out = []
        for i, val in enumerate(series):
            if i == 0 or np.isnan(val):
                out.append(val)
            else:
                out.append((m * val + (length - m) * out[i - 1]) / length)
        return pd.Series(out, index=series.index)
    pK = bcwsma(rsv, signal, 1)
    pD = bcwsma(pK, signal, 1)
    pJ = 3 * pK - 2 * pD
    return (pK, pD, pJ)


def kdj_buy(df):
    if len(df) < 20:
        return None
    pK, pD, pJ = kdj(df)
    if pd.isna(pD.iloc[-1]) or pd.isna(pD.iloc[-2]) or pd.isna(pJ.iloc[-1]) or pd.isna(pJ.iloc[-2]):
        return None
    crossed_up = pJ.iloc[-2] < pD.iloc[-2] and pJ.iloc[-1] > pD.iloc[-1]
    oversold = pD.iloc[-1] < 30 and pJ.iloc[-1] < 30
    if crossed_up and oversold:
        return 'KDJ BUY (J↑D oversold)'
    return None


def kdj_sell(df):
    if len(df) < 20:
        return None
    pK, pD, pJ = kdj(df)
    if pd.isna(pD.iloc[-1]) or pd.isna(pD.iloc[-2]) or pd.isna(pJ.iloc[-1]) or pd.isna(pJ.iloc[-2]):
        return None
    crossed_down = pJ.iloc[-2] > pD.iloc[-2] and pJ.iloc[-1] < pD.iloc[-1]
    overbought = pD.iloc[-1] > 70 and pJ.iloc[-1] > 70
    if crossed_down and overbought:
        return 'KDJ SELL (J↓D overbought)'
    return None


def consecutive_close_momentum(df, min_count=3):
    if len(df) < min_count + 1:
        return None
    closes = df['close'].values
    if closes[-1] > closes[-2]:
        direction = 'Bull'
    elif closes[-1] < closes[-2]:
        direction = 'Bear'
    else:
        return None
    count = 1
    for i in range(len(closes) - 2, 0, -1):
        if direction == 'Bull':
            if closes[i] > closes[i - 1]:
                count += 1
            else:
                break
        elif closes[i] < closes[i - 1]:
            count += 1
        else:
            break
    if count >= min_count:
        return (direction, count)
    return None


def camarilla_breakout(df):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    high = prev['high']
    low = prev['low']
    close = prev['close']
    rng = high - low
    H4 = close + rng * 1.1 / 2
    L4 = close - rng * 1.1 / 2
    if curr['close'] > H4:
        return 'Bullish Camarilla Breakout'
    if curr['close'] < L4:
        return 'Bearish Camarilla Breakdown'
    return None


def cpr_breakout(df):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    high = prev['high']
    low = prev['low']
    close = prev['close']
    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = pivot * 2 - bc
    top = max(tc, bc)
    bottom = min(tc, bc)
    if curr['close'] > top:
        return 'Bullish CPR Breakout'
    if curr['close'] < bottom:
        return 'Bearish CPR Breakdown'
    return None


def inside_bar_breakout(df):
    if len(df) < 4:
        return None
    mother = df.iloc[-4]
    inside1 = df.iloc[-3]
    inside2 = df.iloc[-2]
    curr = df.iloc[-1]
    inside_ok = inside1['high'] < mother['high'] and inside1['low'] > mother['low'] and (inside2['high'] < mother['high']) and (inside2['low'] > mother['low'])
    if not inside_ok:
        return None
    if curr['close'] > mother['high']:
        return 'Bullish Inside Bar Breakout (3-bar coil)'
    if curr['close'] < mother['low']:
        return 'Bearish Inside Bar Breakdown (3-bar coil)'
    return None


def adx_expansion(df):
    if len(df) < 30:
        return None
    adx = talib.ADX(df['high'], df['low'], df['close'], 14)
    ema20 = talib.EMA(df['close'], 20)
    if adx.iloc[-2] < 20 and adx.iloc[-1] > 25:
        if df['close'].iloc[-1] > ema20.iloc[-1]:
            return 'Bullish ADX Expansion'
        if df['close'].iloc[-1] < ema20.iloc[-1]:
            return 'Bearish ADX Expansion'
    return None


def range_expansion_day(df, lookback=5):
    if len(df) < lookback + 2:
        return None
    today = df.iloc[-1]
    avg_range = (df['high'] - df['low']).iloc[-lookback - 1:-1].mean()
    today_range = today['high'] - today['low']
    if today_range > 1.5 * avg_range:
        if today['close'] > today['open']:
            return 'Bullish Range Expansion Day'
        else:
            return 'Bearish Range Expansion Day'
    return None


def failed_breakout_breakdown(df, lookback=20):
    if len(df) < lookback + 2:
        return None
    recent_high = df['high'].iloc[-lookback:-1].max()
    recent_low = df['low'].iloc[-lookback:-1].min()
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if prev['high'] > recent_high and curr['close'] < recent_high:
        return 'Failed Breakout (Bearish)'
    if prev['low'] < recent_low and curr['close'] > recent_low:
        return 'Failed Breakdown (Bullish)'
    return None


def ema_compression_expansion(df):
    if len(df) < 60:
        return None
    ema20 = talib.EMA(df['close'], 20)
    ema50 = talib.EMA(df['close'], 50)
    ema100 = talib.EMA(df['close'], 100)
    compression = abs(ema20.iloc[-2] - ema50.iloc[-2]) / ema50.iloc[-2] < 0.003 and abs(ema50.iloc[-2] - ema100.iloc[-2]) / ema100.iloc[-2] < 0.003
    if not compression:
        return None
    if ema20.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]:
        return 'Bullish EMA Compression Break'
    if ema20.iloc[-1] < ema50.iloc[-1] < ema100.iloc[-1]:
        return 'Bearish EMA Compression Break'
    return None


def rsi_macd_cross_swing(df):
    if len(df) < 50:
        return None
    rsi = talib.RSI(df['close'], 14)
    macd, signal, _ = talib.MACD(df['close'], 12, 26, 9)
    rsi_prev = rsi.iloc[-2]
    macd_prev = macd.iloc[-2]
    signal_prev = signal.iloc[-2]
    rsi_curr = rsi.iloc[-1]
    macd_curr = macd.iloc[-1]
    signal_curr = signal.iloc[-1]
    if rsi_prev < 40 and rsi_curr > 40 and (macd_prev < signal_prev) and (macd_curr > signal_curr):
        return 'Bullish RSI+MACD Cross'
    if rsi_prev > 60 and rsi_curr < 60 and (macd_prev > signal_prev) and (macd_curr < signal_curr):
        return 'Bearish RSI+MACD Cross'
    return None


def atr_percent(df, period=14):
    if len(df) < period + 1:
        return None
    atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=period)
    val = atr.iloc[-1]
    close = df['close'].iloc[-1]
    if pd.isna(val) or close <= 0:
        return None
    return val / close * 100.0


def calculate_confluence(row):
    score = 0
    text = ' '.join([str(row.get('Signal', '')), str(row.get('Trend', '')), str(row.get('State', '')), str(row.get('Setup', '')), str(row.get('Divergence', ''))])
    for k in BULL_KEYWORDS:
        if k in text:
            score += 1
    for k in BEAR_KEYWORDS:
        if k in text:
            score -= 1
    score = max(min(score, 5), -5)
    if score > 0:
        bias = 'Bullish'
    elif score < 0:
        bias = 'Bearish'
    else:
        bias = 'Neutral'
    abs_score = abs(score)
    if abs_score >= 4:
        prob = 'High'
    elif abs_score >= 3:
        prob = 'Medium'
    else:
        prob = 'Low'
    return (score, bias, prob)


def run_all_scanners_for_symbol(sym, df, tf, analysis_date, data_all_tfs):
    results = {}
    results['RSI Market Pulse'] = rsi_market_pulse(df) is not None
    results['Volume Shocker'] = volume_shocker(df)
    results['NRB-7 Breakout'] = nrb_7(df) is not None
    results['Counter Attack'] = counter_attack(df) is not None
    results['Breakaway Gaps'] = breakaway_gap(df) is not None
    results['RSI + ADX'] = rsi_adx(df) is not None
    results['MACD Market Pulse'] = macd_market_pulse(df) is not None
    results['MACD Normal Divergence'] = macd_normal_divergence(df) is not None
    results['MACD Bearish Peak Divergence'] = macd_peak_bearish_divergence(df) is not None
    results['MACD Bullish Base Divergence'] = macd_base_bullish_divergence(df) is not None
    results['Trend Alignment (EMA)'] = trend_alignment(df) is not None
    results['Pullback to EMA'] = pullback_to_ema(df) is not None
    results['High Probability Confluence'] = confluence_setup(df) is not None
    results['MACD Hook Up'] = macd_hook_up(df) is not None
    results['MACD Hook Down'] = macd_hook_down(df) is not None
    results['MACD Histogram Divergence'] = macd_histogram_divergence(df) is not None
    results['EMA50 + Stoch Oversold'] = ema50_stoch_oversold(df) is not None
    results['Dark Cloud Cover'] = dark_cloud_cover(df) is not None
    results['Morning Star (Bottom)'] = morning_star_bottom(df) is not None
    results['Evening Star (Top)'] = evening_star_top(df) is not None
    results['50 EMA Fake Breakdown'] = ema50_fake_breakdown(df) is not None
    results['50 EMA Fake Breakout'] = ema50_fake_breakout(df) is not None
    results['KDJ BUY (Oversold)'] = kdj_buy(df) is not None
    results['KDJ SELL (Overbought)'] = kdj_sell(df) is not None
    results['Probable Momentum (Consecutive Close)'] = consecutive_close_momentum(df, min_count=3) is not None
    results['Camarilla Breakout / Breakdown'] = camarilla_breakout(df) is not None
    results['CPR Breakout / Breakdown'] = cpr_breakout(df) is not None
    results['Inside Bar Breakout'] = inside_bar_breakout(df) is not None
    results['ADX Expansion (Trend Ignition)'] = adx_expansion(df) is not None
    results['Range Expansion Day'] = range_expansion_day(df) is not None
    results['Failed Breakout / Breakdown'] = failed_breakout_breakdown(df) is not None
    results['EMA Compression → Expansion'] = ema_compression_expansion(df) is not None
    results['RSI Swing'] = rsi_swing(df) is not None
    if 'Weekly' in data_all_tfs and 'Monthly' in data_all_tfs:
        data_w = data_all_tfs['Weekly']
        data_m = data_all_tfs['Monthly']
        if sym in data_w and sym in data_m:
            df_w = trim_df_to_date(data_w[sym], analysis_date)
            df_m = trim_df_to_date(data_m[sym], analysis_date)
            if df_w is not None and df_m is not None:
                results['RSI WM 60–40'] = rsi_wm(df, df_w, df_m) is not None
            else:
                results['RSI WM 60–40'] = False
        else:
            results['RSI WM 60–40'] = False
    else:
        results['RSI WM 60–40'] = False
    htf_map = {'15 Min': '1 Hour', '1 Hour': 'Daily', 'Daily': 'Weekly', 'Weekly': 'Monthly'}
    if tf in htf_map and htf_map[tf] in data_all_tfs:
        data_htf = data_all_tfs[htf_map[tf]]
    else:
        data_htf = None
    if data_htf is not None and sym in data_htf:
        df_htf = trim_df_to_date(data_htf[sym], analysis_date)
        if df_htf is not None:
            results['MACD RD (4th Wave)'] = macd_rd(df, df_htf) is not None
        else:
            results['MACD RD (4th Wave)'] = False
    else:
        results['MACD RD (4th Wave)'] = False
    results['Probable 3rd Wave'] = third_wave_finder(df)
    results['Probable C Wave'] = c_wave_finder(df)
    if data_htf is not None and sym in data_htf:
        df_htf = trim_df_to_date(data_htf[sym], analysis_date)
        if df_htf is not None:
            results['Bullish GSAS'] = bullish_gsas(df, df_htf) is not None
            results['Bearish GSAS'] = bearish_gsas(df, df_htf) is not None
        else:
            results['Bullish GSAS'] = False
            results['Bearish GSAS'] = False
    else:
        results['Bullish GSAS'] = False
        results['Bearish GSAS'] = False
    atr_val = atr_percent(df)
    results['Top 10 by ATR %'] = atr_val is not None
    return results


def liquidity_sweep_reversal(df, lookback=20):
    if len(df) < lookback + 2:
        return None
    prev_high = df['high'].iloc[-lookback:-1].max()
    prev_low = df['low'].iloc[-lookback:-1].min()
    last = df.iloc[-1]
    if last['low'] < prev_low and last['close'] > prev_low:
        return 'Bullish Liquidity Sweep'
    if last['high'] > prev_high and last['close'] < prev_high:
        return 'Bearish Liquidity Sweep'
    return None


def island_reversal(df):
    if len(df) < 5:
        return None
    a = df.iloc[-4]
    b = df.iloc[-3]
    c = df.iloc[-2]
    d = df.iloc[-1]
    if b['low'] > a['high'] and d['open'] < c['low']:
        return 'Bullish Island Reversal'
    if b['high'] < a['low'] and d['open'] > c['high']:
        return 'Bearish Island Reversal'
    return None


def wyckoff_spring_upthrust(df, lookback=30):
    if len(df) < lookback + 2:
        return None
    range_high = df['high'].iloc[-lookback:-1].max()
    range_low = df['low'].iloc[-lookback:-1].min()
    last = df.iloc[-1]
    if last['low'] < range_low and last['close'] > range_low:
        return 'Wyckoff Spring (Bullish)'
    if last['high'] > range_high and last['close'] < range_high:
        return 'Wyckoff Upthrust (Bearish)'
    return None


def smart_money_trap(df):
    if len(df) < 3:
        return None
    prev = df.iloc[-2]
    last = df.iloc[-1]
    if prev['close'] > prev['high'] * 0.99 and last['close'] < prev['low']:
        return 'Bull Trap Reversal'
    if prev['close'] < prev['low'] * 1.01 and last['close'] > prev['high']:
        return 'Bear Trap Reversal'
    return None


def bump_and_run_reversal(df):
    if len(df) < 40:
        return None
    slope1 = (df['close'].iloc[-30] - df['close'].iloc[-40]) / 10
    slope2 = (df['close'].iloc[-1] - df['close'].iloc[-10]) / 10
    if slope2 > slope1 * 2 and df['close'].iloc[-1] < df['close'].iloc[-5]:
        return 'BARR Top Reversal'
    if slope2 < slope1 * 2 and df['close'].iloc[-1] > df['close'].iloc[-5]:
        return 'BARR Bottom Reversal'
    return None


def exhaustion_bar(df):
    if len(df) < 20:
        return None
    avg_range = (df['high'] - df['low']).rolling(10).mean().iloc[-2]
    last = df.iloc[-1]
    big_bar = last['high'] - last['low'] > 2 * avg_range
    if big_bar:
        if last['close'] < last['open']:
            return 'Bearish Exhaustion'
        if last['close'] > last['open']:
            return 'Bullish Exhaustion'
    return None


def shakeout_trap(df, lookback=20):
    if len(df) < lookback + 2:
        return None
    high = df['high'].iloc[-lookback:-1].max()
    low = df['low'].iloc[-lookback:-1].min()
    prev = df.iloc[-2]
    last = df.iloc[-1]
    if prev['low'] < low and last['close'] > low:
        return 'Bullish Shakeout'
    if prev['high'] > high and last['close'] < high:
        return 'Bearish Shakeout'
    return None


def hidden_pivot_reversal(df, lookback=25):
    if len(df) < lookback:
        return None
    highs = df['high'].iloc[-lookback:]
    lows = df['low'].iloc[-lookback:]
    if highs.iloc[-1] > highs.iloc[:-1].max() and df['close'].iloc[-1] < highs.iloc[:-1].max():
        return 'Hidden Pivot Bearish Reversal'
    if lows.iloc[-1] < lows.iloc[:-1].min() and df['close'].iloc[-1] > lows.iloc[:-1].min():
        return 'Hidden Pivot Bullish Reversal'
    return None


def springer_reversal(df, lookback=25):
    if len(df) < lookback + 5:
        return None
    support = df['low'].iloc[-lookback:-5].min()
    recent = df.iloc[-1]
    if recent['low'] < support and recent['close'] > support:
        return 'Springer Reversal (Bullish)'
    return None


# ==============================
# SCANNER TILE CONFIG  (re-added — required by generate_static_data.py / api)
# ==============================
SCANNERS = [
    {"name": "RSI Market Pulse", "color": "#1abc9c"},
    {"name": "Volume Shocker", "color": "#1abc9c"},
    {"name": "NRB-7 Breakout", "color": "#1abc9c"},
    {"name": "Counter Attack", "color": "#1abc9c"},
    {"name": "Breakaway Gaps", "color": "#e67e22"},
    {"name": "RSI + ADX", "color": "#e67e22"},
    {"name": "RSI WM 60–40", "color": "#e67e22"},
    {"name": "MACD Market Pulse", "color": "#e67e22"},
    {"name": "MACD Normal Divergence", "color": "#f1c40f"},
    {"name": "MACD RD (4th Wave)", "color": "#f1c40f"},
    {"name": "Probable 3rd Wave", "color": "#f1c40f"},
    {"name": "Probable C Wave", "color": "#f1c40f"},
    {"name": "MACD Bearish Peak Divergence", "color": "#3498db"},
    {"name": "MACD Bullish Base Divergence", "color": "#3498db"},
    {"name": "Trend Alignment (EMA)", "color": "#3498db"},
    {"name": "Pullback to EMA", "color": "#3498db"},
    {"name": "High Probability Confluence", "color": "#e84393"},
    {"name": "MACD Hook Up", "color": "#e84393"},
    {"name": "MACD Hook Down", "color": "#e84393"},
    {"name": "MACD Histogram Divergence", "color": "#e84393"},
    {"name": "EMA50 + Stoch Oversold", "color": "#f1c40f"},
    {"name": "Dark Cloud Cover", "color": "#f1c40f"},
    {"name": "Morning Star (Bottom)", "color": "#f1c40f"},
    {"name": "Evening Star (Top)", "color": "#f1c40f"},
    {"name": "Bullish GSAS", "color": "#27ae60"},
    {"name": "Bearish GSAS", "color": "#27ae60"},
    {"name": "50 EMA Fake Breakdown", "color": "#27ae60"},
    {"name": "50 EMA Fake Breakout", "color": "#27ae60"},
    {"name": "KDJ BUY (Oversold)", "color": "#f39c12"},
    {"name": "KDJ SELL (Overbought)", "color": "#f39c12"},
    {"name": "Probable Momentum (Consecutive Close)", "color": "#f39c12"},
    {"name": "Camarilla Breakout / Breakdown", "color": "#f39c12"},
    {"name": "CPR Breakout / Breakdown", "color": "#e67e22"},
    {"name": "Inside Bar Breakout", "color": "#e67e22"},
    {"name": "ADX Expansion (Trend Ignition)", "color": "#e67e22"},
    {"name": "Range Expansion Day", "color": "#e67e22"},
    {"name": "Failed Breakout / Breakdown", "color": "#34495e"},
    {"name": "EMA Compression → Expansion", "color": "#34495e"},
    {"name": "Top 10 by ATR %", "color": "#34495e"},
    {"name": "Liquidity Sweep Reversal", "color": "#34495e"},
    {"name": "Island Reversal", "color": "#ff6b81"},
    {"name": "Wyckoff Spring / Upthrust", "color": "#ff6b81"},
    {"name": "Smart Money Trap", "color": "#ff6b81"},
    {"name": "Bump & Run Reversal", "color": "#ff6b81"},
    {"name": "Exhaustion Bar", "color": "#3498db"},
    {"name": "Shakeout / Trap", "color": "#3498db"},
    {"name": "Hidden Pivot Reversal", "color": "#3498db"},
    {"name": "Springer Reversal", "color": "#3498db"},
    {"name": "RSI + MACD Cross Swing", "color": "#9b59b6"},
    {"name": "RSI Swing", "color": "#8e44ad"},
]


def run_scanner(scanner, tf, analysis_date, data_loader):
    """
    scanner: name string from SCANNERS
    tf: timeframe key e.g. "Daily"
    analysis_date: date object
    data_loader: function(tf) -> {symbol: df}  (this is data_loader.load_data)
    """
    data = data_loader(tf)
    if not data:
        return empty_result_df()

    results = []
    atr_list = []

    if scanner in ["Bullish GSAS", "Bearish GSAS", "MACD RD (4th Wave)"]:
        htf_map = {"15 Min": "1 Hour", "1 Hour": "Daily", "Daily": "Weekly", "Weekly": "Monthly"}
        if tf not in htf_map:
            return empty_result_df()
        data_htf = data_loader(htf_map[tf])
    else:
        data_htf = None

    if scanner == "RSI WM 60–40":
        data_w = data_loader("Weekly")
        data_m = data_loader("Monthly")

    for sym, df in data.items():
        df = trim_df_to_date(df, analysis_date)
        if df is None:
            continue

        base_row = {
            "Symbol": sym, "Signal": "", "Trend": "", "State": "", "Setup": "",
            "Divergence": "", "RSI": "", "Zone": "", "Confluence": 0,
            "Bias": "", "Probability": "", "TV_Link": "",
        }

        if scanner == "Top 10 by ATR %":
            v = atr_percent(df)
            if v is not None:
                row = base_row.copy()
                row["Signal"] = "High ATR %"
                row["State"] = f"{v:.2f}%"
                atr_list.append((sym, v, row))
            continue

        if scanner == "RSI Market Pulse":
            r = rsi_market_pulse(df)
            if r:
                row = base_row.copy(); row["RSI"] = r[0]; row["Zone"] = r[1]; results.append(row)
        elif scanner == "Volume Shocker" and volume_shocker(df):
            row = base_row.copy(); row["Signal"] = "Volume Shocker"; results.append(row)
        elif scanner == "NRB-7 Breakout":
            sig = nrb_7(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Counter Attack":
            sig = counter_attack(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Breakaway Gaps":
            sig = breakaway_gap(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "RSI + ADX":
            sig = rsi_adx(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "RSI WM 60–40":
            if sym in data_w and sym in data_m:
                df_wt = trim_df_to_date(data_w[sym], analysis_date)
                df_mt = trim_df_to_date(data_m[sym], analysis_date)
                if df_wt is None or df_mt is None:
                    continue
                sig = rsi_wm(df, df_wt, df_mt)
                if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "MACD Market Pulse":
            sig = macd_market_pulse(df)
            if sig: row = base_row.copy(); row["State"] = sig; results.append(row)
        elif scanner == "MACD Normal Divergence":
            sig = macd_normal_divergence(df)
            if sig: row = base_row.copy(); row["Divergence"] = sig; results.append(row)
        elif scanner == "MACD RD (4th Wave)":
            if data_htf is not None and sym in data_htf:
                df_htf = trim_df_to_date(data_htf[sym], analysis_date)
                if df_htf is None: continue
                sig = macd_rd(df, df_htf)
                if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Probable 3rd Wave":
            if third_wave_finder(df):
                row = base_row.copy(); row["Signal"] = "Probable 3rd Wave"; results.append(row)
        elif scanner == "Probable C Wave":
            if c_wave_finder(df):
                row = base_row.copy(); row["Signal"] = "Probable C Wave"; results.append(row)
        elif scanner == "MACD Bearish Peak Divergence":
            sig = macd_peak_bearish_divergence(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; row["Divergence"] = sig; results.append(row)
        elif scanner == "MACD Bullish Base Divergence":
            sig = macd_base_bullish_divergence(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; row["Divergence"] = sig; results.append(row)
        elif scanner == "Trend Alignment (EMA)":
            sig = trend_alignment(df)
            if sig: row = base_row.copy(); row["Trend"] = sig; results.append(row)
        elif scanner == "Pullback to EMA":
            sig = pullback_to_ema(df)
            if sig: row = base_row.copy(); row["Setup"] = sig; results.append(row)
        elif scanner == "High Probability Confluence":
            sig = confluence_setup(df)
            if sig: row = base_row.copy(); row["Setup"] = sig; results.append(row)
        elif scanner == "MACD Hook Up":
            sig = macd_hook_up(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "MACD Hook Down":
            sig = macd_hook_down(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "MACD Histogram Divergence":
            sig = macd_histogram_divergence(df)
            if sig: row = base_row.copy(); row["Divergence"] = sig; results.append(row)
        elif scanner == "EMA50 + Stoch Oversold":
            sig = ema50_stoch_oversold(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Dark Cloud Cover":
            sig = dark_cloud_cover(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Morning Star (Bottom)":
            sig = morning_star_bottom(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Evening Star (Top)":
            sig = evening_star_top(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Bullish GSAS":
            if data_htf is not None and sym in data_htf:
                df_htf = trim_df_to_date(data_htf[sym], analysis_date)
                if df_htf is None: continue
                sig = bullish_gsas(df, df_htf)
                if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Bearish GSAS":
            if data_htf is not None and sym in data_htf:
                df_htf = trim_df_to_date(data_htf[sym], analysis_date)
                if df_htf is None: continue
                sig = bearish_gsas(df, df_htf)
                if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "50 EMA Fake Breakdown":
            sig = ema50_fake_breakdown(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "50 EMA Fake Breakout":
            sig = ema50_fake_breakout(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "KDJ BUY (Oversold)":
            sig = kdj_buy(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "KDJ SELL (Overbought)":
            sig = kdj_sell(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Probable Momentum (Consecutive Close)":
            res = consecutive_close_momentum(df, min_count=3)
            if res:
                direction, days = res
                row = base_row.copy()
                row["Signal"] = f"{direction} Momentum"
                row["State"] = f"{days} Consecutive Days"
                results.append(row)
        elif scanner == "Camarilla Breakout / Breakdown":
            sig = camarilla_breakout(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "CPR Breakout / Breakdown":
            sig = cpr_breakout(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Inside Bar Breakout":
            sig = inside_bar_breakout(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "ADX Expansion (Trend Ignition)":
            sig = adx_expansion(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Range Expansion Day":
            sig = range_expansion_day(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Failed Breakout / Breakdown":
            sig = failed_breakout_breakdown(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Liquidity Sweep Reversal":
            sig = liquidity_sweep_reversal(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Island Reversal":
            sig = island_reversal(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Wyckoff Spring / Upthrust":
            sig = wyckoff_spring_upthrust(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Smart Money Trap":
            sig = smart_money_trap(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Bump & Run Reversal":
            sig = bump_and_run_reversal(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Exhaustion Bar":
            sig = exhaustion_bar(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Shakeout / Trap":
            sig = shakeout_trap(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "RSI + MACD Cross Swing":
            sig = rsi_macd_cross_swing(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Hidden Pivot Reversal":
            sig = hidden_pivot_reversal(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "Springer Reversal":
            sig = springer_reversal(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "EMA Compression → Expansion":
            sig = ema_compression_expansion(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)
        elif scanner == "RSI Swing":
            sig = rsi_swing(df)
            if sig: row = base_row.copy(); row["Signal"] = sig; results.append(row)

    if scanner == "Top 10 by ATR %":
        if not atr_list:
            return empty_result_df()
        atr_list.sort(key=lambda x: x[1], reverse=True)
        results = [r[2] for r in atr_list[:10]]

    if not results:
        return empty_result_df()

    df_res = pd.DataFrame(results)
    for c in SAFE_COLS:
        if c not in df_res.columns:
            df_res[c] = "" if c != "Confluence" else 0

    for i, row in df_res.iterrows():
        score, bias, prob = calculate_confluence(row)
        df_res.at[i, "Confluence"] = score
        df_res.at[i, "Bias"] = bias
        df_res.at[i, "Probability"] = prob

    df_res["TV_Link"] = df_res["Symbol"].apply(lambda s: f"[TV]({make_tradingview_link(s)})" if s else "")

    bias_rank = {"Bullish": 0, "Neutral": 1, "Bearish": 2}
    df_res["_bias_rank"] = df_res["Bias"].map(bias_rank)
    df_res = df_res.sort_values(by=["Confluence", "_bias_rank"], ascending=[False, True]).drop(columns="_bias_rank")
    df_res = df_res[SAFE_COLS]
    df_res = df_res.replace([np.inf, -np.inf], "").fillna("")
    return df_res
