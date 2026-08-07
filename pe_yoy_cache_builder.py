#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PE + YoY 每日快取建立器
- TWSE 上市: 從台交所官方 API 取得 (BWIBBU_d + t187ap05_L)
- TPEx 上櫃: 從 FinMind API 取得 (免費、無需 API Key)
每日執行一次，輸出 pe_yoy_cache.json
"""

import json, urllib.request, time, os

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pe_yoy_cache.json")
STOCKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")

# 最重要的 TPEx 上櫃股票代號 (優先抓取)
TPEx_PRIORITY = [
    "5274","8299","3081","4908","4979","3363","3131","6187","3529","3324",
    "6643","6488","3163","6223","5269","3661","2379","6669","3017","3653",
    "3013","6515","3583","1560","6451","3231","5274","4912","6547","4994",
    "6592","3105","3152","3406","4960","5351","6449","8454","3545","6277",
    "3714","4763","6568","3703","3049","4927","6462","5314","3061","4934",
]

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return None

def fetch_finmind(dataset, stock_id, start_date="2025-06-01"):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset={dataset}&data_id={stock_id}&start_date={start_date}"
    result = fetch_url(url)
    if result and result.get("status") == 200:
        return result.get("data", [])
    return []

def compute_yoy_from_revenue(rows):
    """從月營收序列計算最新月份的 YoY%"""
    if not rows:
        return 0.0
    latest = rows[-1]
    same_month_ly = next(
        (r for r in rows
         if r["revenue_year"] == latest["revenue_year"] - 1
         and r["revenue_month"] == latest["revenue_month"]),
        None
    )
    if same_month_ly and same_month_ly["revenue"] > 0:
        return round((latest["revenue"] - same_month_ly["revenue"]) / same_month_ly["revenue"] * 100, 1)
    return 0.0

def main():
    today = time.strftime("%Y-%m-%d")
    print(f"[{time.strftime('%H:%M:%S')}] 🚀 開始建立 PE + YoY 快取...")

    pe_map = {}   # code -> float PE
    yoy_map = {}  # code -> float YoY%

    # ── 1. TWSE 上市 PE (BWIBBU_d) ──
    print("  [TWSE] 抓取本益比...")
    twse_pe = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d") or []
    for x in twse_pe:
        code = x.get("Code", "").strip()
        pe_str = x.get("PEratio", "0").replace(",", "")
        try:
            v = float(pe_str)
            if v > 0:
                pe_map[code] = round(v, 1)
        except:
            pass
    print(f"    ✅ TWSE PE: {len(pe_map)} 筆")

    # ── 2. TWSE 上市 YoY (t187ap05_L) ──
    print("  [TWSE] 抓取月營收年增率...")
    twse_rev = fetch_url("https://openapi.twse.com.tw/v1/opendata/t187ap05_L") or []
    for x in twse_rev:
        code = x.get("公司代號", "").strip()
        yoy_str = x.get("營業收入-去年同月增減(%)", "0").replace(",", "")
        try:
            v = float(yoy_str)
            yoy_map[code] = round(v, 1)
        except:
            pass
    print(f"    ✅ TWSE YoY: {len(yoy_map)} 筆")
    time.sleep(1)

    # ── 3. 讀取 stocks 取得 TPEx 上櫃代號 (按成交量排序) ──
    tpex_codes = set(TPEx_PRIORITY)
    try:
        with open(STOCKS_FILE, encoding="utf-8") as f:
            stocks = json.load(f)
        # 加入成交量最高的上櫃股票代號
        tpex_stocks = sorted(
            [s for s in stocks if s.get("market") == "TPEx上櫃" and s.get("volume", 0) > 0],
            key=lambda x: x.get("volume", 0), reverse=True
        )[:200]
        for s in tpex_stocks:
            tpex_codes.add(s["symbol"].split(".")[0])
    except:
        pass

    # ── 4. FinMind 逐一抓取 TPEx 上櫃 PE + YoY ──
    tpex_list = list(tpex_codes)
    print(f"  [FinMind] 抓取 {len(tpex_list)} 檔 TPEx 上櫃 PE + YoY...")
    ok_count = 0

    for i, code in enumerate(tpex_list):
        # PE
        pe_rows = fetch_finmind("TaiwanStockPER", code, "2026-07-10")
        if pe_rows:
            last_pe = pe_rows[-1].get("PER", 0)
            if last_pe and last_pe > 0:
                pe_map[code] = round(float(last_pe), 1)

        # YoY
        rev_rows = fetch_finmind("TaiwanStockMonthRevenue", code, "2025-06-01")
        if rev_rows:
            yoy_val = compute_yoy_from_revenue(rev_rows)
            if yoy_val != 0:
                yoy_map[code] = yoy_val

        if pe_rows or rev_rows:
            ok_count += 1

        if (i + 1) % 20 == 0:
            print(f"    進度: {i+1}/{len(tpex_list)} ({ok_count} 筆成功)")
        time.sleep(0.3)  # 避免過快被 rate-limit

    print(f"  ✅ TPEx FinMind: PE {sum(1 for c in tpex_list if c in pe_map)} 筆 | YoY {sum(1 for c in tpex_list if c in yoy_map)} 筆")

    # ── 5. 儲存快取 ──
    cache = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pe": pe_map,
        "yoy": yoy_map,
        "total_pe": len(pe_map),
        "total_yoy": len(yoy_map),
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    print(f"[{time.strftime('%H:%M:%S')}] ✅ 快取建立完成！")
    print(f"  PE: {len(pe_map)} 檔 | YoY: {len(yoy_map)} 檔 → {CACHE_FILE}")

if __name__ == "__main__":
    main()
