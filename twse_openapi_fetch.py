#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市 TWSE + TPEx 官方 Open API 真實行情爬取器
直接從 TWSE (台灣證券交易所) 與 TPEx (櫃買中心) 官方 Open API 下載當日全市場收盤行情
"""

import json
import urllib.request
import urllib.parse
import time
import os

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")

def fetch_twse_stocks():
    """從 TWSE 官方 API 抓取上市股票全部收盤行情"""
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"[TWSE] API 回傳狀態: {data.get('stat', 'unknown')}")
        return data.get("data", []), data.get("fields", [])
    except Exception as e:
        print(f"[TWSE] 抓取失敗: {e}")
        return [], []

def fetch_tpex_stocks():
    """從 TPEx 官方 API 抓取上櫃股票全部收盤行情"""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"[TPEx] 抓取成功，共 {len(data)} 筆")
        return data
    except Exception as e:
        print(f"[TPEx] 抓取失敗: {e}")
        return []

def fetch_twse_listed_all():
    """從 TWSE Open API 取得全部上市股票列表與收盤價"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"[TWSE OpenAPI] 上市股票行情: {len(data)} 筆")
        return data
    except Exception as e:
        print(f"[TWSE OpenAPI] 失敗: {e}")
        return []

def fetch_twse_company_list():
    """從 TWSE 取得全部上市公司列表與產業分類"""
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"[TWSE OpenAPI] 上市公司列表: {len(data)} 筆")
        return data
    except Exception as e:
        print(f"[TWSE OpenAPI] 公司列表失敗: {e}")
        return []

def fetch_tpex_company_list():
    """從 TPEx 取得全部上櫃公司列表"""
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_listed_companies"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"[TPEx OpenAPI] 上櫃公司列表: {len(data)} 筆")
        return data
    except Exception as e:
        print(f"[TPEx OpenAPI] 公司列表失敗: {e}")
        return []

def main():
    print("=" * 60)
    print("🚀 台灣股市官方 Open API 真實行情爬取器")
    print(f"📅 抓取日期: 2026-07-19 (今日最新收盤)")
    print("=" * 60)

    stocks = []
    now_str = time.strftime("%H:%M:%S")

    # 嘗試抓取 TWSE 上市行情
    twse_all = fetch_twse_listed_all()
    twse_companies = fetch_twse_company_list()
    time.sleep(1)
    tpex_stocks = fetch_tpex_stocks()
    tpex_companies = fetch_tpex_company_list()

    # 建立公司名稱 & 產業對照表
    company_map = {}
    for c in twse_companies:
        code = c.get("公司代號", "").strip()
        name = c.get("公司簡稱", "").strip()
        ind = c.get("產業別", "").strip()
        if code and name:
            company_map[code] = {"name": name, "sector": ind or "其他"}

    for c in tpex_companies:
        code = c.get("SecuritiesCompanyCode", "").strip() or c.get("Code", "").strip()
        name = c.get("CompanyName", "").strip() or c.get("Name", "").strip()
        ind = c.get("IndustryCode", "").strip() or "其他"
        if code and name:
            company_map[code] = {"name": name, "sector": ind}

    print(f"\n✅ 公司對照表建立完成: {len(company_map)} 間公司")

    # 處理 TWSE 上市股票行情
    for s in twse_all:
        code = s.get("Code", "").strip()
        name = s.get("Name", "").strip()
        close_str = s.get("ClosingPrice", "0").replace(",", "")
        change_str = s.get("Change", "0").replace(",", "")

        try:
            close = float(close_str)
        except:
            continue
        if close <= 0:
            continue

        try:
            chg_val = float(change_str)
            if close > 0:
                chg_pct = round(chg_val / (close - chg_val) * 100, 2)
                chg_str = f"+{chg_pct}%" if chg_pct >= 0 else f"{chg_pct}%"
            else:
                chg_str = "0.00%"
        except:
            chg_str = "0.00%"

        info = company_map.get(code, {})
        real_name = info.get("name", name) or name
        sector = info.get("sector", "其他")

        stocks.append({
            "symbol": f"{code}.TW",
            "name": real_name,
            "sector": sector,
            "market": "TWSE上市",
            "price": close,
            "change": chg_str,
            "pe": 0,
            "mcap": 0,
            "yoy": 0,
            "inst": "-",
            "score": 75,
            "desc": f"{real_name} ({code}) 上市股票",
            "last_update": now_str
        })

    print(f"✅ TWSE 上市股票: {len(stocks)} 筆")

    # 處理 TPEx 上櫃股票行情
    tpex_count = 0
    for s in tpex_stocks:
        code = s.get("SecuritiesCompanyCode", "").strip() or s.get("Code", "").strip()
        name = s.get("CompanyName", "").strip() or s.get("Name", "").strip()
        close_str = str(s.get("Close", s.get("ClosingPrice", "0"))).replace(",", "")

        try:
            close = float(close_str)
        except:
            continue
        if close <= 0:
            continue

        chg_raw = str(s.get("Change", "0")).replace(",", "")
        try:
            chg_val = float(chg_raw)
            prev = close - chg_val
            chg_pct = round(chg_val / prev * 100, 2) if prev > 0 else 0
            chg_str = f"+{chg_pct}%" if chg_pct >= 0 else f"{chg_pct}%"
        except:
            chg_str = "0.00%"

        info = company_map.get(code, {})
        real_name = info.get("name", name) or name
        sector = info.get("sector", "其他")

        stocks.append({
            "symbol": f"{code}.TWO",
            "name": real_name,
            "sector": sector,
            "market": "TPEx上櫃",
            "price": close,
            "change": chg_str,
            "pe": 0,
            "mcap": 0,
            "yoy": 0,
            "inst": "-",
            "score": 72,
            "desc": f"{real_name} ({code}) 上櫃股票",
            "last_update": now_str
        })
        tpex_count += 1

    print(f"✅ TPEx 上櫃股票: {tpex_count} 筆")
    print(f"\n📊 合計全台股標的: {len(stocks)} 檔")

    if len(stocks) < 100:
        print("❌ 資料量不足，請確認網路連線後重新執行！")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)

    print(f"✅ 已儲存至 {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
