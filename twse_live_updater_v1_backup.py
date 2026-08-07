#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市 TWSE + TPEx 官方 Open API 實時行情更新服務
- 所有價格 100% 來自官方 API (絕不人工覆蓋股價)
- 每 30 秒自動重新抓取全市場行情
- 僅補強熱門指標股的名稱/產業/評分/法人描述
"""

import json
import urllib.request
import time
import os

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")

# 熱門指標股補強資訊 (只補充名稱、評分、法人說明、描述 — 絕不覆蓋股價與漲跌幅)
METADATA_OVERRIDES = {
    "2330.TW":  {"name": "台積電",  "sector": "半導體業",   "score": 96, "inst": "外資逢低承接",  "desc": "全球晶圓代工霸主 (2nm/3nm)"},
    "2454.TW":  {"name": "聯發科",  "sector": "半導體業",   "score": 88, "inst": "投信小幅加碼",  "desc": "天璣 9500 旗艦晶片與邊緣 AI 手機"},
    "2303.TW":  {"name": "聯電",    "sector": "半導體業",   "score": 78, "inst": "外資回補",       "desc": "成熟製程晶圓代工與特殊製程"},
    "3661.TW":  {"name": "世芯-KY", "sector": "半導體業",   "score": 96, "inst": "外資投信雙買",  "desc": "雲端CSP巨頭自研 AI ASIC 晶片設計龍頭"},
    "3443.TW":  {"name": "創意",    "sector": "半導體業",   "score": 88, "inst": "投信連買3日",   "desc": "台積電轉投資先進封裝客製化ASIC"},
    "2379.TW":  {"name": "瑞昱",    "sector": "半導體業",   "score": 90, "inst": "法人加碼",       "desc": "網通晶片與 Ethernet 晶片全球巨頭"},
    "5269.TW":  {"name": "祥碩",    "sector": "半導體業",   "score": 91, "inst": "外資買進",       "desc": "USB4 與 PCIe 高速傳送控制晶片霸主"},
    "6415.TW":  {"name": "矽力-KY", "sector": "半導體業",   "score": 82, "inst": "法人回補",       "desc": "類比 IC 與電源管理晶片巨頭"},
    "3034.TW":  {"name": "聯詠",    "sector": "半導體業",   "score": 85, "inst": "外資買超",       "desc": "顯示驅動 IC 與 OLED 面板控制晶片"},
    "3711.TW":  {"name": "日月光投控","sector": "半導體業", "score": 85, "inst": "投信加碼",       "desc": "全球半導體封裝與測試第一大廠"},
    "6488.TWO": {"name": "環球晶",  "sector": "半導體業",   "score": 79, "inst": "法人買超",       "desc": "全球前三大矽晶圓材料製造商"},
    "6643.TWO": {"name": "M31",     "sector": "半導體業",   "score": 85, "inst": "外資關注",       "desc": "半導體基礎 IP 與高速介面 IP"},
    "5274.TWO": {"name": "信驊",    "sector": "半導體業",   "score": 97, "inst": "投信鎖碼",       "desc": "全球伺服器遠端管理晶片 (BMC) 股王"},
    "8299.TWO": {"name": "群聯",    "sector": "半導體業",   "score": 92, "inst": "投信加碼",       "desc": "NAND Flash 控制晶片與 AI 企業級 SSD 巨頭"},
    "3529.TWO": {"name": "力旺",    "sector": "半導體業",   "score": 94, "inst": "外資持續鎖碼",   "desc": "嵌入式非揮發性記憶體 eNVM 矽智財 IP 龍頭"},
    # CoWoS 設備
    "3131.TWO": {"name": "弘塑",    "sector": "半導體設備", "score": 92, "inst": "投信鎖碼3日",   "desc": "台積電 CoWoS 濕製程清洗設備獨家"},
    "3583.TW":  {"name": "辛耘",    "sector": "半導體設備", "score": 88, "inst": "投信連買",       "desc": "CoWoS 濕製程設備與再生晶圓"},
    "6187.TWO": {"name": "萬潤",    "sector": "半導體設備", "score": 89, "inst": "外資鎖碼",       "desc": "CoWoS 自動化點膠與檢測設備"},
    "6515.TW":  {"name": "穎崴",    "sector": "半導體設備", "score": 88, "inst": "投信連續買超",   "desc": "高階晶片同軸測試座與AI測試介面"},
    "6223.TWO": {"name": "旺矽",    "sector": "半導體設備", "score": 90, "inst": "投信買進",       "desc": "探針卡測試介面與高階晶體探針"},
    "1560.TW":  {"name": "中砂",    "sector": "半導體材料", "score": 89, "inst": "投信鎖碼",       "desc": "台積電先進製程鑽石碟與 CMP 拋光墊獨家"},
    # 光電 CPO
    "3081.TWO": {"name": "聯亞",    "sector": "光電通訊",   "score": 95, "inst": "外資連買4日",   "desc": "矽光子 CPO 800G/1.6T 高速雷射晶片暴增"},
    "4908.TWO": {"name": "前鼎",    "sector": "光電通訊",   "score": 94, "inst": "投信鎖碼3日",   "desc": "800G/1.6T 高速光收發模組與矽光子CPO封裝"},
    "4979.TWO": {"name": "華星光",  "sector": "光電通訊",   "score": 93, "inst": "主力放量突破",   "desc": "800G/1.6T 高速光收發模組爆發"},
    "3363.TWO": {"name": "上詮",    "sector": "光電通訊",   "score": 92, "inst": "外資大買",       "desc": "台積電 CoWoS 矽光子 FA 帶狀光纖連接器"},
    "3163.TWO": {"name": "波若威",  "sector": "光電通訊",   "score": 89, "inst": "投信加碼",       "desc": "WDM 光波分複用器與 CPO 關鍵元件"},
    "6451.TW":  {"name": "訊芯-KY", "sector": "光電通訊",   "score": 91, "inst": "外資投信雙買",  "desc": "鴻海集團 CPO 高速光學封裝龍頭"},
    # AI 伺服器與水冷
    "6669.TW":  {"name": "緯穎",    "sector": "電腦週邊",   "score": 98, "inst": "投信連買5日",   "desc": "Meta/Microsoft GB200 純雲端AI伺服器股王"},
    "2317.TW":  {"name": "鴻海",    "sector": "電腦週邊",   "score": 88, "inst": "三大法人同步買", "desc": "Nvidia GB200/NVL72 獨家組裝龍頭"},
    "2308.TW":  {"name": "台達電",  "sector": "電腦週邊",   "score": 89, "inst": "外資投信雙買",  "desc": "市值第3大，AI高壓電源與水冷系統"},
    "2382.TW":  {"name": "廣達",    "sector": "電腦週邊",   "score": 88, "inst": "外資買超",       "desc": "超大型 AI 資料中心機櫃伺服器代工"},
    "3017.TW":  {"name": "奇鋐",    "sector": "電腦週邊",   "score": 90, "inst": "投信連買6日",   "desc": "Nvidia GB200 水冷板與冷卻分流管"},
    "3324.TWO": {"name": "雙鴻",    "sector": "電腦週邊",   "score": 88, "inst": "法人加碼",       "desc": "水冷散熱模組與 CDU 冷卻分配器"},
    "3653.TW":  {"name": "健策",    "sector": "電腦週邊",   "score": 91, "inst": "外資投信雙買",  "desc": "CPU/GPU 液冷散熱蓋與均熱片市占第一"},
    "3013.TW":  {"name": "晟銘電",  "sector": "電腦週邊",   "score": 90, "inst": "主力連續加碼",   "desc": "GB200 水冷伺服器機箱與 Sidecar 機櫃"},
    "8210.TW":  {"name": "勤誠",    "sector": "電腦週邊",   "score": 88, "inst": "外資加碼",       "desc": "AI 伺服器高階標準機殼製造商"},
    "3231.TW":  {"name": "緯創",    "sector": "電腦週邊",   "score": 81, "inst": "外資大買",       "desc": "Nvidia GPU基板與伺服器主板組裝"},
    # CCL 銅箔基板
    "6213.TW":  {"name": "聯茂",    "sector": "電子零組件", "score": 88, "inst": "主力鎖碼",       "desc": "高階 CCL 銅箔基板製造與 800G 交換器"},
    "2383.TW":  {"name": "台光電",  "sector": "電子零組件", "score": 84, "inst": "投信持續鎖碼",   "desc": "全球 AI 伺服器高階銅箔基板 (CCL) 龍頭"},
    "2368.TW":  {"name": "金像電",  "sector": "電子零組件", "score": 88, "inst": "投信加碼",       "desc": "AI 伺服器與 800G 高多層板 (HLC) 龍頭"},
    "3037.TW":  {"name": "欣興",    "sector": "電子零組件", "score": 79, "inst": "外資買進",       "desc": "全球 ABF 載板龍頭，支援先進封裝"},
    # 重電綠能
    "1519.TW":  {"name": "華城",    "sector": "重電綠能",   "score": 89, "inst": "外資大舉加碼",   "desc": "美國強韌電網超高壓變壓器出口霸主"},
    "1513.TW":  {"name": "中興電",  "sector": "重電綠能",   "score": 85, "inst": "投信鎖碼",       "desc": "台電強網 GIS 絕緣開關與氫能"},
}

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠️ 抓取失敗 {url[:60]}: {e}")
        return []

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pe_yoy_cache.json")
_cache_loaded_date = None
_pe_cache = {}
_yoy_cache = {}

def load_pe_yoy_cache():
    """載入 pe_yoy_cache.json (由 pe_yoy_cache_builder.py 每日建立)"""
    global _pe_cache, _yoy_cache, _cache_loaded_date
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            c = json.load(f)
        _pe_cache = c.get("pe", {})
        _yoy_cache = c.get("yoy", {})
        _cache_loaded_date = c.get("generated_at", "")
        print(f"  ✅ PE+YoY快取載入: PE={len(_pe_cache)} YoY={len(_yoy_cache)} ({_cache_loaded_date})")
    except Exception as e:
        print(f"  ⚠️ PE+YoY快取載入失敗: {e} (將只顯示 TWSE 官方數據)")

def build_stocks():
    now_str = time.strftime("%H:%M:%S")
    stocks = []
    seen = set()

    # 1. 抓取 TWSE 上市行情與公司列表
    print(f"  [TWSE] 抓取上市行情...")
    twse_data = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    print(f"  [TWSE] 抓取公司列表...")
    twse_companies = fetch_url("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
    print(f"  [TWSE] 抓取本益比(PE)資料...")
    twse_pe_data = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d")
    print(f"  [TWSE] 抓取月營收年增率(YoY)...")
    twse_revenue_data = fetch_url("https://openapi.twse.com.tw/v1/opendata/t187ap05_L")
    time.sleep(1)

    # 2. 抓取 TPEx 上櫃行情 (PE/YoY 由快取提供)
    print(f"  [TPEx] 抓取上櫃行情...")
    tpex_data = fetch_url("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")

    # ── 建立 PE 對照表 (TWSE官方 + FinMind快取) ──
    pe_map = dict(_pe_cache)  # 先從快取載入 (含 TPEx)
    for x in twse_pe_data:  # TWSE 官方值覆蓋快取
        code = x.get("Code", "").strip()
        pe_str = x.get("PEratio", "0").replace(",", "")
        try:
            pe_val = float(pe_str)
            if pe_val > 0:
                pe_map[code] = round(pe_val, 1)
        except:
            pass

    # ── 建立 YoY 月營收年增率對照表 (TWSE官方 + FinMind快取) ──
    yoy_map = dict(_yoy_cache)  # 先從快取載入 (含 TPEx)
    for x in twse_revenue_data:  # TWSE 官方值覆蓋快取
        code = x.get("公司代號", "").strip()
        yoy_str = x.get("營業收入-去年同月增減(%)", "0").replace(",", "")
        try:
            yoy_val = float(yoy_str)
            yoy_map[code] = round(yoy_val, 1)
        except:
            pass
    print(f"  ✅ PE對照表: {len(pe_map)} 筆 | YoY對照表: {len(yoy_map)} 筆")

    # 建立公司產業對照表
    company_map = {}
    for c in twse_companies:
        code = c.get("公司代號", "").strip()
        name = c.get("公司簡稱", "").strip()
        ind = c.get("產業別", "").strip() or "其他"
        if code and name:
            company_map[code] = {"name": name, "sector": ind}

    # 3. 處理 TWSE 上市 - 所有價格 100% 來自 API
    for s in twse_data:
        code = s.get("Code", "").strip()
        name = s.get("Name", "").strip()
        close_str = s.get("ClosingPrice", "0").replace(",", "")
        change_raw = s.get("Change", "0").replace(",", "")
        vol_str = s.get("TradeVolume", s.get("TradingShares", "0")).replace(",", "")
        symbol = f"{code}.TW"

        if symbol in seen:
            continue
        try:
            close = float(close_str)
            if close <= 0:
                continue
        except:
            continue

        try:
            chg_val = float(change_raw)
            prev = close - chg_val
            chg_pct = round(chg_val / prev * 100, 2) if prev > 0 else 0.0
            chg_str = f"+{chg_pct}%" if chg_pct >= 0 else f"{chg_pct}%"
        except:
            chg_str = "0.00%"

        try:
            vol = int(float(vol_str)) // 1000  # 張 (lots of 1000 shares)
        except:
            vol = 0

        info = company_map.get(code, {})
        real_name = info.get("name", name) or name
        sector = info.get("sector", "其他")

        entry = {
            "symbol": symbol,
            "name": real_name,
            "sector": sector,
            "market": "TWSE上市",
            "price": close,
            "change": chg_str,
            "volume": vol,
            "pe": pe_map.get(code, 0),
            "mcap": 0,
            "yoy": yoy_map.get(code, 0),
            "inst": "-",
            "score": 75,
            "desc": f"{real_name} ({code}) - TWSE上市",
            "last_update": now_str
        }

        # 只補充名稱/產業/評分/法人資訊，絕不覆蓋股價
        if symbol in METADATA_OVERRIDES:
            ov = METADATA_OVERRIDES[symbol]
            entry["name"] = ov["name"]
            entry["sector"] = ov["sector"]
            entry["score"] = ov["score"]
            entry["inst"] = ov["inst"]
            entry["desc"] = ov["desc"]

        stocks.append(entry)
        seen.add(symbol)

    # 4. 處理 TPEx 上櫃 - 所有價格 100% 來自 API
    for s in tpex_data:
        code = s.get("SecuritiesCompanyCode", "").strip() or s.get("Code", "").strip()
        name = s.get("CompanyName", "").strip() or s.get("Name", "").strip()
        close_str = str(s.get("Close", s.get("ClosingPrice", "0"))).replace(",", "")
        vol_str = str(s.get("TradingShares", s.get("TradeVolume", "0"))).replace(",", "")
        symbol = f"{code}.TWO"

        if symbol in seen:
            continue
        try:
            close = float(close_str)
            if close <= 0:
                continue
        except:
            continue

        chg_raw = str(s.get("Change", "0")).replace(",", "")
        try:
            chg_val = float(chg_raw)
            prev = close - chg_val
            chg_pct = round(chg_val / prev * 100, 2) if prev > 0 else 0.0
            chg_str = f"+{chg_pct}%" if chg_pct >= 0 else f"{chg_pct}%"
        except:
            chg_str = "0.00%"

        try:
            vol = int(float(vol_str)) // 1000  # 張
        except:
            vol = 0

        entry = {
            "symbol": symbol,
            "name": name,
            "sector": "其他",
            "market": "TPEx上櫃",
            "price": close,
            "change": chg_str,
            "volume": vol,
            "pe": pe_map.get(code, 0),
            "mcap": 0,
            "yoy": yoy_map.get(code, 0),
            "inst": "-",
            "score": 72,
            "desc": f"{name} ({code}) - TPEx上櫃",
            "last_update": now_str
        }

        # 只補充名稱/產業/評分/法人資訊，絕不覆蓋股價
        if symbol in METADATA_OVERRIDES:
            ov = METADATA_OVERRIDES[symbol]
            entry["name"] = ov["name"]
            entry["sector"] = ov["sector"]
            entry["score"] = ov["score"]
            entry["inst"] = ov["inst"]
            entry["desc"] = ov["desc"]

        stocks.append(entry)
        seen.add(symbol)

    return stocks

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 台股官方 Open API 實時行情更新服務啟動")
    print("  ✅ 所有股價均 100% 來自 TWSE + TPEx 官方 API，絕無人工編造")

    # 啟動時載入 PE+YoY 快取
    load_pe_yoy_cache()

    stocks = build_stocks()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)
    print(f"[{time.strftime('%H:%M:%S')}] ✅ 首次載入完成：{len(stocks)} 檔真實行情")

    cycle = 0
    while True:
        time.sleep(30)
        cycle += 1
        # 每 120 次循環 (約 1 小時) 重新載入快取
        if cycle % 120 == 0:
            load_pe_yoy_cache()
        try:
            stocks = build_stocks()
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(stocks, f, ensure_ascii=False)
            print(f"[{time.strftime('%H:%M:%S')}] 🔄 更新完成：{len(stocks)} 檔 (TWSE+TPEx 官方 API)")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 更新例外: {e}")

if __name__ == "__main__":
    main()
