#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市技術指標(SMA/布林通道/KD/RSI/MACD/ATR)每日計算器 (多線程高效版)
- 自動篩選成交量 >= 500 張的上市上櫃活躍標的 (約 300~500 檔)
- 使用 ThreadPoolExecutor (20線程) 於 15 秒內完成 Yahoo Finance 3個月行情抓取
- 計算:
  1. 5MA / 10MA / 20MA
  2. 布林通道 (Upper / Lower / Width)
  3. 20日成交均量 (Volume SMA20)
  4. RSI (14) 指標
  5. KD (9, 3, 3) 隨機指標
  6. MACD (12, 26, 9) 指標及柱狀圖 (Histogram)
  7. Wilder's ATR (14) 波動度指標
"""

import json
import urllib.request
import time
import os
import math
import concurrent.futures
import re

STOCKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tech_cache.json")

def get_historical_prices(symbol):
    """從 Yahoo Finance API 抓取 3 個月的每日開高低收與成交量"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            
            result = data.get('chart', {}).get('result', [])
            if not result:
                return [], [], [], []
                
            quote = result[0].get('indicators', {}).get('quote', [{}])[0]
            closes = quote.get('close', [])
            volumes = quote.get('volume', [])
            highs = quote.get('high', [])
            lows = quote.get('low', [])
            
            # 對齊並過濾掉 None 值
            valid_closes = []
            valid_volumes = []
            valid_highs = []
            valid_lows = []
            for c, v, h, l in zip(closes, volumes, highs, lows):
                if c is not None and v is not None and h is not None and l is not None:
                    valid_closes.append(c)
                    valid_volumes.append(v)
                    valid_highs.append(h)
                    valid_lows.append(l)
            return valid_closes, valid_volumes, valid_highs, valid_lows
    except Exception as e:
        return [], [], [], []

def calculate_ema(prices, period):
    """計算指數移動平均線 (EMA)"""
    if not prices:
        return []
    ema = [prices[0]]
    multiplier = 2.0 / (period + 1.0)
    for p in prices[1:]:
        ema.append((p - ema[-1]) * multiplier + ema[-1])
    return ema

def calculate_macd(closes):
    """計算 MACD (12, 26, 9)"""
    if len(closes) < 26:
        return [0.0] * len(closes), [0.0] * len(closes), [0.0] * len(closes)
        
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal_line = calculate_ema(macd_line, 9)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    
    return macd_line, signal_line, hist

def calculate_rsi(closes, period=14):
    """計算 Wilder's RSI (14)"""
    if len(closes) < period + 1:
        return [50.0] * len(closes)
        
    gains = []
    losses = []
    for t in range(1, len(closes)):
        change = closes[t] - closes[t-1]
        gains.append(change if change > 0 else 0.0)
        losses.append(-change if change < 0 else 0.0)
        
    rsi_list = [50.0] * (period + 1)
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rsi = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi_list.append(rsi)
    
    for t in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[t]) / period
        avg_loss = (avg_loss * (period - 1) + losses[t]) / period
        if avg_loss == 0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_list.append(rsi)
        
    return rsi_list

def calculate_atr(highs, lows, closes, period=14):
    """計算 Wilder's ATR (14)"""
    if len(closes) < period + 1:
        return [0.0] * len(closes)
        
    tr_list = [highs[0] - lows[0]]
    for t in range(1, len(closes)):
        tr = max(
            highs[t] - lows[t],
            abs(highs[t] - closes[t-1]),
            abs(lows[t] - closes[t-1])
        )
        tr_list.append(tr)
        
    atr_list = []
    first_atr = sum(tr_list[:period]) / period
    for _ in range(period):
        atr_list.append(0.0)
        
    current_atr = first_atr
    atr_list.append(current_atr)
    
    for t in range(period + 1, len(closes)):
        current_atr = (current_atr * (period - 1) + tr_list[t]) / period
        atr_list.append(current_atr)
        
    return atr_list

def calculate_kd(highs, lows, closes, period=9):
    """計算 Stochastic KD (9, 3, 3)"""
    if len(closes) < period:
        return [50.0] * len(closes), [50.0] * len(closes)
        
    rsv_list = []
    for t in range(len(closes)):
        if t < period - 1:
            rsv_list.append(50.0)
            continue
        slice_highs = highs[t - period + 1 : t + 1]
        slice_lows = lows[t - period + 1 : t + 1]
        hh = max(slice_highs)
        ll = min(slice_lows)
        if hh == ll:
            rsv = 50.0
        else:
            rsv = 100.0 * (closes[t] - ll) / (hh - ll)
        rsv_list.append(rsv)
        
    k_list = []
    d_list = []
    current_k = 50.0
    current_d = 50.0
    
    for rsv in rsv_list:
        current_k = (2.0 / 3.0) * current_k + (1.0 / 3.0) * rsv
        current_d = (2.0 / 3.0) * current_d + (1.0 / 3.0) * current_k
        k_list.append(current_k)
        d_list.append(current_d)
        
    return k_list, d_list

def calc_all_indicators(closes, volumes, highs, lows):
    """綜合計算所有均線、布林通道與進階量化指標"""
    if len(closes) < 30: # 確保有足夠的數據溫機計算 EMA26
        return None
        
    c_20 = closes[-20:]
    v_20 = volumes[-20:]
    
    sma5 = sum(closes[-5:]) / 5.0 if len(closes) >= 5 else sum(closes) / len(closes)
    sma10 = sum(closes[-10:]) / 10.0 if len(closes) >= 10 else sum(closes) / len(closes)
    sma20 = sum(c_20) / 20.0
    vol_sma20 = sum(v_20) / 20.0
    
    # 計算布林通道
    variance = sum((c - sma20) ** 2 for c in c_20) / 20.0
    stddev = math.sqrt(variance)
    upper_band = sma20 + (2 * stddev)
    lower_band = sma20 - (2 * stddev)
    band_width = (upper_band - lower_band) / sma20 if sma20 > 0 else 0.0
    
    # 計算進階指標
    rsi_list = calculate_rsi(closes)
    k_list, d_list = calculate_kd(highs, lows, closes)
    macd_line, signal_line, hist_list = calculate_macd(closes)
    atr_list = calculate_atr(highs, lows, closes)
    
    # 判斷黃金交叉 (回測最近 3 天)
    kd_golden_cross = False
    for t in range(len(closes) - 3, len(closes)):
        if t > 0:
            if k_list[t-1] <= d_list[t-1] and k_list[t] > d_list[t]:
                kd_golden_cross = True
                break
                
    macd_golden_cross = False
    for t in range(len(closes) - 3, len(closes)):
        if t > 0:
            if hist_list[t-1] <= 0 and hist_list[t] > 0:
                macd_golden_cross = True
                break
                
    sma5_20_golden_cross = False
    # 5MA/20MA 交叉判斷 (今天 SMA5 和 SMA20)
    if len(closes) >= 23:
        p_sma5 = sum(closes[-6:-1]) / 5.0
        p_sma20 = sum(closes[-21:-1]) / 20.0
        if p_sma5 <= p_sma20 and sma5 > sma20:
            sma5_20_golden_cross = True
            
    return {
        "sma5": round(sma5, 2),
        "sma10": round(sma10, 2),
        "sma20": round(sma20, 2),
        "upper_band": round(upper_band, 2),
        "lower_band": round(lower_band, 2),
        "band_width": round(band_width, 4),
        "vol_sma20": round(vol_sma20, 1),
        "rsi": round(rsi_list[-1], 2),
        "k": round(k_list[-1], 2),
        "d": round(d_list[-1], 2),
        "macd_hist": round(hist_list[-1], 3),
        "atr": round(atr_list[-1], 3),
        "kd_golden_cross": kd_golden_cross,
        "macd_golden_cross": macd_golden_cross,
        "golden_cross_5_20": sma5_20_golden_cross,
        "latest_close": closes[-1],
        "history5d": [round(c, 2) for c in closes[-5:]] if len(closes) >= 5 else [round(c, 2) for c in closes]
    }

def build_cache():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 啟動進階量化指標(MA/布林/RSI/KD/MACD/ATR)平行計算...")
    
    if not os.path.exists(STOCKS_FILE):
        print(f"❌ 錯誤：找不到 {STOCKS_FILE} 檔案！")
        return
        
    try:
        with open(STOCKS_FILE, "r", encoding="utf-8") as f:
            stocks = json.load(f)
    except Exception as e:
        print(f"❌ 讀取 {STOCKS_FILE} 失敗: {e}")
        return
        
    candidate_stocks = []
    for s in stocks:
        symbol = s.get("symbol", "")
        market = s.get("market", "")
        volume = s.get("volume", 0) or 0
        code = symbol.split(".")[0]
        if market in ["TWSE上市", "TPEx上櫃"] and volume >= 500 and len(code) == 4:
            candidate_stocks.append(s)
            
    candidate_stocks.sort(key=lambda x: x.get("volume", 0) or 0, reverse=True)
    target_stocks = candidate_stocks
    print(f"  📊 篩選出 {len(candidate_stocks)} 檔液態個股，進行平行爬取...")
    
    tech_cache = {}
    
    def process_stock(s):
        symbol = s.get("symbol", "")
        if not symbol:
            return None
        closes, volumes, highs, lows = get_historical_prices(symbol)
        if closes and volumes and highs and lows:
            indicators = calc_all_indicators(closes, volumes, highs, lows)
            if indicators:
                code = symbol.split(".")[0]
                return code, indicators
        return None

    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_stock = {executor.submit(process_stock, s): s for s in target_stocks}
        for future in concurrent.futures.as_completed(future_to_stock):
            res = future.result()
            if res:
                code, indicators = res
                tech_cache[code] = indicators
                
    elapsed = time.time() - start_time
    
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": tech_cache
    }
    
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
        
    print(f"[{time.strftime('%H:%M:%S')}] ✅ 技術指標快取建立完成，共 {len(tech_cache)} 筆 (耗時: {elapsed:.2f} 秒) → {CACHE_FILE}")

if __name__ == "__main__":
    build_cache()
