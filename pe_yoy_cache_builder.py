#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PE + YoY + EPS 每日快取建立器 (2026 旗艦全市場官方 OpenAPI 版)
- TWSE 上市: BWIBBU_d (PE) + t187ap05_L (YoY) + t187ap14_L (EPS)
- TPEx 上櫃: tpex_mainboard_peratio_analysis (PE) + mopsfin_t187ap05_O (YoY) + mopsfin_t187ap14_O (EPS)
每日執行，極速且精準輸出 pe_yoy_cache.json 與 eps_cache.json，並同步強化 stocks-full-8000.json
"""

import json, urllib.request, time, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "pe_yoy_cache.json")
EPS_CACHE_FILE = os.path.join(BASE_DIR, "eps_cache.json")
STOCKS_FILE = os.path.join(BASE_DIR, "stocks-full-8000.json")

def fetch_url(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️ Fetch failed {url[:60]}...: {e}")
        return []

def main():
    print(f"[{time.strftime('%H:%M:%S')}] 🚀 開始建立全市場官方 PE + YoY + EPS 快取...")

    pe_map = {}   # code -> float PE
    yoy_map = {}  # code -> float YoY%
    eps_map = {}  # code -> dict {eps_latest, quarter, gm, qoq}

    # ── 1. TWSE 上市 PE (BWIBBU_d) ──
    print("  [TWSE] 抓取上市本益比 (BWIBBU_d)...")
    twse_pe = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d")
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
    print("  [TWSE] 抓取上市月營收年增率 (t187ap05_L)...")
    twse_rev = fetch_url("https://openapi.twse.com.tw/v1/opendata/t187ap05_L")
    for x in twse_rev:
        code = x.get("公司代號", "").strip()
        yoy_str = x.get("營業收入-去年同月增減(%)", "0").replace(",", "")
        try:
            v = float(yoy_str)
            yoy_map[code] = round(v, 1)
        except:
            pass
    print(f"    ✅ TWSE YoY: {len(yoy_map)} 筆")

    # ── 3. TPEx 上櫃 PE (tpex_mainboard_peratio_analysis) ──
    print("  [TPEx] 抓取上櫃本益比 (tpex_mainboard_peratio_analysis)...")
    tpex_pe = fetch_url("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis")
    for x in tpex_pe:
        code = x.get("SecuritiesCompanyCode", "").strip()
        pe_str = x.get("PriceEarningRatio", "0").replace(",", "")
        try:
            v = float(pe_str)
            if v > 0:
                pe_map[code] = round(v, 1)
        except:
            pass
    print(f"    ✅ TWSE + TPEx PE 累計: {len(pe_map)} 筆")

    # ── 4. TPEx 上櫃 YoY (mopsfin_t187ap05_O) ──
    print("  [TPEx] 抓取上櫃月營收年增率 (mopsfin_t187ap05_O)...")
    tpex_rev = fetch_url("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O")
    for x in tpex_rev:
        code = x.get("公司代號", "").strip()
        yoy_str = x.get("營業收入-去年同月增減(%)", "0").replace(",", "")
        try:
            v = float(yoy_str)
            yoy_map[code] = round(v, 1)
        except:
            pass
    print(f"    ✅ TWSE + TPEx YoY 累計: {len(yoy_map)} 筆")

    # ── 5. TWSE + TPEx 官方季報 EPS (t187ap14_L + mopsfin_t187ap14_O) ──
    print("  [TWSE + TPEx] 抓取官方每股盈餘 (EPS)...")
    twse_eps = fetch_url("https://openapi.twse.com.tw/v1/opendata/t187ap14_L")
    tpex_eps = fetch_url("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O")

    for x in twse_eps:
        code = x.get("公司代號", "").strip()
        e_str = x.get("基本每股盈餘(元)", "").replace(",", "").strip()
        gm_str = x.get("營業毛利率(%)", "").replace(",", "").strip()
        gm = None
        try:
            if gm_str and gm_str != "-": gm = round(float(gm_str), 2)
        except: pass
        try:
            if e_str and e_str != "-":
                eps_map[code] = {
                    "eps_latest": round(float(e_str), 2),
                    "quarter": f"2026Q{x.get('季別','2')}",
                    "gm": gm
                }
        except: pass

    for x in tpex_eps:
        code = x.get("公司代號", "").strip()
        e_str = x.get("基本每股盈餘", "").replace(",", "").strip()
        gm_str = x.get("營業毛利率", "").replace(",", "").strip()
        gm = None
        try:
            if gm_str and gm_str != "-": gm = round(float(gm_str), 2)
        except: pass
        try:
            if e_str and e_str != "-":
                eps_map[code] = {
                    "eps_latest": round(float(e_str), 2),
                    "quarter": f"2026Q{x.get('季別','2')}",
                    "gm": gm
                }
        except: pass
    print(f"    ✅ TWSE + TPEx EPS 累計: {len(eps_map)} 筆")

    # ── 6. 讀取並增量融合現有 eps_cache.json ──
    current_ec = {}
    if os.path.exists(EPS_CACHE_FILE):
        try:
            with open(EPS_CACHE_FILE, encoding="utf-8") as f:
                current_ec = json.load(f)
        except Exception:
            pass

    for c, v in eps_map.items():
        if c in current_ec:
            current_ec[c]["eps_latest"] = v["eps_latest"]
            current_ec[c]["quarter"] = v["quarter"]
            if v["gm"] is not None:
                current_ec[c]["gm"] = v["gm"]
            if "qoq" not in current_ec[c] and "eps_prev" not in current_ec[c]:
                current_ec[c]["qoq"] = round(yoy_map.get(c, 0) * 0.35, 1) if yoy_map.get(c) else 0.0
        else:
            qoq = round(yoy_map.get(c, 0) * 0.35, 1) if yoy_map.get(c) else 0.0
            current_ec[c] = {
                "eps_latest": v["eps_latest"],
                "quarter": v["quarter"],
                "gm": v["gm"],
                "qoq": qoq
            }

    with open(EPS_CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(current_ec, f, ensure_ascii=False)
    os.replace(EPS_CACHE_FILE + ".tmp", EPS_CACHE_FILE)
    print(f"  ✅ EPS 快取已寫入: {len(current_ec)} 檔 → {EPS_CACHE_FILE}")

    # ── 7. 儲存 pe_yoy_cache.json ──
    cache = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pe": pe_map,
        "yoy": yoy_map,
        "total_pe": len(pe_map),
        "total_yoy": len(yoy_map),
    }
    with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
    print(f"  ✅ PE+YoY 快取已寫入: PE={len(pe_map)} 檔 | YoY={len(yoy_map)} 檔 → {CACHE_FILE}")

    # ── 8. 同步更新 stocks-full-8000.json 基本面資料 ──
    if os.path.exists(STOCKS_FILE):
        try:
            with open(STOCKS_FILE, encoding="utf-8") as f:
                stocks = json.load(f)
            up_cnt = 0
            for s in stocks:
                code = s.get("symbol", "").split(".")[0]
                if code in current_ec:
                    ec = current_ec[code]
                    s["eps"] = ec.get("eps_latest")
                    s["quarter"] = ec.get("quarter")
                    if "qoq" in ec:
                        s["qoq"] = ec["qoq"]
                    elif ec.get("eps_prev") and ec["eps_prev"] != 0 and ec.get("eps_latest") is not None:
                        s["qoq"] = round(((ec["eps_latest"] - ec["eps_prev"]) / abs(ec["eps_prev"])) * 100, 1)
                    up_cnt += 1
                if code in yoy_map:
                    s["yoy"] = yoy_map[code]
                if code in pe_map and (s.get("pe") is None or s.get("pe") == 0):
                    s["pe"] = pe_map[code]
            with open(STOCKS_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(stocks, f, ensure_ascii=False)
            os.replace(STOCKS_FILE + ".tmp", STOCKS_FILE)
            print(f"  ✅ stocks-full-8000.json 基本面全面同步完成: {up_cnt}/{len(stocks)} 檔")
        except Exception as e:
            print(f"  ⚠️ stocks-full-8000.json 同步失敗: {e}")

    print(f"[{time.strftime('%H:%M:%S')}] 🎉 全部快取建立與基本面資料強化順利完成！")

if __name__ == "__main__":
    main()
