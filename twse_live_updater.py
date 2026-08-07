#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市 TWSE + TPEx 即時行情更新服務 (MIS API 即時版)
- 盤中使用 MIS API (mis.twse.com.tw) 每 15 秒即時更新股價
- 盤後使用 OpenAPI 每 5 分鐘更新收盤行情
- 啟動時從 OpenAPI 抓取完整股票清單 (含 PE/YoY/產業)
- 僅補強熱門指標股的名稱/產業/評分/法人描述
"""

import json
import urllib.request
import time
import os
import datetime

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")
SMART_MONEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_money_cache.json")

# ── MIS API 設定 ──
MIS_API_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
MIS_BATCH_SIZE = 80  # 每批次查詢股數 (實測 100 可行，保守用 80)
MIS_BATCH_DELAY = 0.3  # 批次間延遲 (秒)
MIS_FAIL_THRESHOLD = 3  # 連續失敗幾次後切換回 OpenAPI

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

# ═══════════════════════════════════════════
# 工具函式
# ═══════════════════════════════════════════

import csv
import io
import re

def fetch_url(url):
    """通用 HTTP GET JSON 抓取，加強對控制字元之過濾以防止 JSONDecodeError"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            # 移除 JSON 字串中的不合法控制字元 (0x00-0x1F, 0x7F)
            content = re.sub(r'[\x00-\x1f\x7f]', '', content)
            return json.loads(content)
    except Exception as e:
        print(f"  ⚠️ 抓取失敗 {url[:60]}: {e}")
        return []

def fetch_twse_csv():
    """從台灣證券交易所 RWD 官網抓取最新的 CSV 收盤行情，解決 OpenAPI 伺服器快取過久的問題"""
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_data = resp.read()
            
        try:
            content = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_data.decode("cp950", errors="ignore")
            
        stocks = []
        reader = csv.reader(io.StringIO(content))
        header = next(reader, None)
        if not header:
            return []
            
        for row in reader:
            if len(row) < 10 or not row[0].strip().isdigit():
                continue
                
            code = row[1].strip()
            name = row[2].strip()
            vol_str = row[3].strip()
            close_str = row[8].strip()
            change_str = row[9].strip()
            
            try:
                closing_price = str(float(close_str.replace(",", "")))
            except ValueError:
                closing_price = "0.00"
                
            stocks.append({
                "Code": code,
                "Name": name,
                "ClosingPrice": closing_price,
                "Change": change_str,
                "TradeVolume": vol_str
            })
            
        print(f"  ✅ [TWSE CSV] 成功抓取今日實時行情，共 {len(stocks)} 筆交易記錄")
        return stocks
    except Exception as e:
        print(f"  ⚠️ [TWSE CSV] 抓取失敗: {e}，將嘗試使用 OpenAPI Fallback")
        return []

def is_market_hours():
    """判斷目前是否在台股交易時段 (平日 08:30~13:35)"""
    now = datetime.datetime.now()
    # 週末不開盤
    if now.weekday() >= 5:
        return False
    t = now.time()
    # 交易時段 08:30 ~ 13:35 (含盤後撮合到 14:30，但 MIS 資料到 13:35 左右)
    return datetime.time(8, 30) <= t <= datetime.time(14, 30)

def get_trade_date_str():
    """取得今日日期字串 (YYYY-MM-DD)"""
    return datetime.date.today().strftime("%Y-%m-%d")

# ═══════════════════════════════════════════
# PE/YoY 快取
# ═══════════════════════════════════════════

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

# ═══════════════════════════════════════════
# 大戶籌碼快取
# ═══════════════════════════════════════════

_smart_money = {}

def load_smart_money_cache():
    """載入 smart_money_cache.json"""
    global _smart_money
    try:
        with open(SMART_MONEY_FILE, encoding="utf-8") as f:
            _smart_money = json.load(f)
        print(f"  ✅ 大戶籌碼快取載入: {len(_smart_money)} 筆")
    except Exception:
        pass

# ═══════════════════════════════════════════
# Phase 1: OpenAPI 完整資料建構 (啟動時 & 每小時)
# ═══════════════════════════════════════════

def build_stocks_openapi():
    """從 TWSE + TPEx OpenAPI 建構完整股票清單 (含 PE/YoY/產業/名稱)"""
    now_str = time.strftime("%H:%M:%S")
    trade_date = get_trade_date_str()
    stocks = []
    seen = set()

    # 1. 抓取 TWSE 上市行情與公司列表 (優先用官網實時 CSV，失敗則 fallback OpenAPI)
    print(f"  [TWSE] 抓取上市行情...")
    twse_data = fetch_twse_csv()
    if not twse_data:
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
    pe_map = dict(_pe_cache)
    for x in twse_pe_data:
        code = x.get("Code", "").strip()
        pe_str = x.get("PEratio", "0").replace(",", "")
        try:
            pe_val = float(pe_str)
            if pe_val > 0:
                pe_map[code] = round(pe_val, 1)
        except:
            pass

    # ── 建立 YoY 月營收年增率對照表 (TWSE官方 + FinMind快取) ──
    yoy_map = dict(_yoy_cache)
    for x in twse_revenue_data:
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

    # 3. 處理 TWSE 上市
    for s in twse_data:
        code = s.get("Code", "").strip()
        # 過濾權證與可轉債 (權證代碼大於4碼且非00開頭)
        if len(code) > 6 or (len(code) > 4 and not code.startswith("00")):
            continue
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
            vol = int(float(vol_str)) // 1000
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
            "last_update": now_str,
            "trade_date": trade_date,
            "data_source": "OpenAPI"
        }

        if symbol in METADATA_OVERRIDES:
            ov = METADATA_OVERRIDES[symbol]
            entry["name"] = ov["name"]
            entry["sector"] = ov["sector"]
            entry["score"] = ov["score"]
            entry["inst"] = ov["inst"]
            entry["desc"] = ov["desc"]

        stocks.append(entry)
        seen.add(symbol)

    # 4. 處理 TPEx 上櫃
    for s in tpex_data:
        code = s.get("SecuritiesCompanyCode", "").strip() or s.get("Code", "").strip()
        # 過濾權證與可轉債 (權證代碼大於4碼且非00開頭)
        if len(code) > 6 or (len(code) > 4 and not code.startswith("00")):
            continue
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
            vol = int(float(vol_str)) // 1000
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
            "last_update": now_str,
            "trade_date": trade_date,
            "data_source": "OpenAPI"
        }

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

# ═══════════════════════════════════════════
# Phase 2: MIS API 即時行情覆蓋
# ═══════════════════════════════════════════

def fetch_realtime_mis(stock_entries):
    """
    使用 TWSE MIS API 批次抓取即時行情，覆蓋 stock_entries 中的價格。
    回傳: (成功更新筆數, 交易日期字串)
    """
    # 建立 symbol -> index 對照
    sym_idx = {s["symbol"]: i for i, s in enumerate(stock_entries)}

    # 分類 TWSE / TPEx 代碼
    twse_codes = []
    tpex_codes = []
    for s in stock_entries:
        sym = s["symbol"]
        if sym.endswith(".TW"):
            code = sym.replace(".TW", "")
            twse_codes.append(f"tse_{code}.tw")
        elif sym.endswith(".TWO"):
            code = sym.replace(".TWO", "")
            tpex_codes.append(f"otc_{code}.tw")

    all_codes = twse_codes + tpex_codes
    updated = 0
    trade_date = ""

    # 批次查詢
    for i in range(0, len(all_codes), MIS_BATCH_SIZE):
        batch = all_codes[i:i + MIS_BATCH_SIZE]
        batch_str = "|".join(batch)
        url = f"{MIS_API_URL}?ex_ch={batch_str}&json=1&delay=0"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://mis.twse.com.tw/stock/fibest.jsp",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            if data.get("rtcode") != "0000":
                print(f"    ⚠️ MIS 批次 {i//MIS_BATCH_SIZE+1} 回傳異常: rtcode={data.get('rtcode')}")
                continue

            for item in data.get("msgArray", []):
                code = item.get("c", "").strip()
                ex = item.get("ex", "")  # tse or otc
                z = item.get("z", "-")   # 成交價
                y = item.get("y", "-")   # 昨收
                v = item.get("v", "0")   # 累積成交量 (張)
                n = item.get("n", "")    # 名稱
                d = item.get("d", "")    # 日期 (YYYYMMDD)
                t = item.get("t", "")    # 時間 (HH:MM:SS)

                # 判斷 symbol
                if ex == "tse":
                    symbol = f"{code}.TW"
                else:
                    symbol = f"{code}.TWO"

                if symbol not in sym_idx:
                    continue

                idx = sym_idx[symbol]
                entry = stock_entries[idx]

                # 解析成交價
                try:
                    price = float(z)
                except (ValueError, TypeError):
                    # z 可能是 "-" (尚未成交)，跳過此股
                    continue

                if price <= 0:
                    continue

                # 解析昨收計算漲跌幅
                try:
                    yesterday = float(y)
                    if yesterday > 0:
                        chg_val = price - yesterday
                        chg_pct = round(chg_val / yesterday * 100, 2)
                        chg_str = f"+{chg_pct}%" if chg_pct >= 0 else f"{chg_pct}%"
                    else:
                        chg_str = "0.00%"
                except (ValueError, TypeError):
                    chg_str = "0.00%"

                # 解析成交量
                try:
                    vol = int(v)  # MIS API 回傳的已經是「張」
                except (ValueError, TypeError):
                    vol = entry.get("volume", 0)

                # 解析交易日期
                if d and len(d) == 8:
                    trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

                # 更新 entry
                entry["price"] = price
                entry["change"] = chg_str
                entry["volume"] = vol
                entry["last_update"] = t or time.strftime("%H:%M:%S")
                entry["trade_date"] = trade_date or get_trade_date_str()
                entry["data_source"] = "MIS即時"
                if n:
                    # MIS 有時回傳更精確的名稱，但只在非 override 時使用
                    if symbol not in METADATA_OVERRIDES:
                        entry["name"] = n.strip()

                updated += 1

        except Exception as e:
            print(f"    ⚠️ MIS 批次 {i//MIS_BATCH_SIZE+1} 失敗: {e}")

        # 批次間延遲
        if i + MIS_BATCH_SIZE < len(all_codes):
            time.sleep(MIS_BATCH_DELAY)

    return updated, trade_date

# ═══════════════════════════════════════════
# 主迴圈
# ═══════════════════════════════════════════

def save_stocks(stocks):
    """原子寫入 JSON 檔案"""
    tmp_file = OUTPUT_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)
    os.replace(tmp_file, OUTPUT_FILE)

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 台股即時行情更新服務啟動 (MIS API 即時版)")
    print("  ✅ 盤中: MIS API 每 15 秒即時更新")
    print("  ✅ 盤後: OpenAPI 每 5 分鐘更新收盤行情")

    # 啟動時載入快取
    load_pe_yoy_cache()
    load_smart_money_cache()

    # Phase 1: 首次完整建構
    print(f"\n[{time.strftime('%H:%M:%S')}] 📦 Phase 1: 從 OpenAPI 建構完整股票清單...")
    stocks = build_stocks_openapi()
    save_stocks(stocks)
    print(f"[{time.strftime('%H:%M:%S')}] ✅ 首次載入完成：{len(stocks)} 檔")

    # Phase 2: 立即用 MIS API 覆蓋即時價格
    if stocks:
        print(f"[{time.strftime('%H:%M:%S')}] ⚡ Phase 2: MIS API 即時行情覆蓋...")
        updated, trade_date = fetch_realtime_mis(stocks)
        save_stocks(stocks)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ MIS 即時更新完成：{updated}/{len(stocks)} 檔 (交易日: {trade_date})")

    cycle = 0
    mis_fail_count = 0
    last_openapi_refresh = time.time()
    OPENAPI_REFRESH_INTERVAL = 3600  # 每小時重新從 OpenAPI 建構完整資料

    while True:
        cycle += 1

        if is_market_hours():
            # ── 盤中模式: MIS API 每 15 秒 ──
            time.sleep(15)

            # 每小時重新從 OpenAPI 建構完整資料 (更新 PE/YoY/產業 等)
            if time.time() - last_openapi_refresh > OPENAPI_REFRESH_INTERVAL:
                print(f"\n[{time.strftime('%H:%M:%S')}] 📦 定期重建完整資料...")
                load_pe_yoy_cache()
                load_smart_money_cache()
                new_stocks = build_stocks_openapi()
                if new_stocks:
                    stocks = new_stocks
                    last_openapi_refresh = time.time()
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ 完整資料重建完成: {len(stocks)} 檔")

            # MIS 即時更新
            try:
                updated, trade_date = fetch_realtime_mis(stocks)
                if updated > 0:
                    save_stocks(stocks)
                    mis_fail_count = 0
                    if cycle % 4 == 0:  # 每分鐘印一次日誌
                        print(f"[{time.strftime('%H:%M:%S')}] ⚡ MIS 即時更新: {updated}/{len(stocks)} 檔 (交易日: {trade_date})")
                else:
                    mis_fail_count += 1
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ MIS 更新 0 筆 (連續失敗: {mis_fail_count})")
            except Exception as e:
                mis_fail_count += 1
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ MIS 更新例外: {e} (連續失敗: {mis_fail_count})")

            # 連續失敗超過閾值，回退到 OpenAPI
            if mis_fail_count >= MIS_FAIL_THRESHOLD:
                print(f"[{time.strftime('%H:%M:%S')}] 🔄 MIS 連續失敗 {mis_fail_count} 次，回退 OpenAPI...")
                try:
                    new_stocks = build_stocks_openapi()
                    if new_stocks:
                        stocks = new_stocks
                        save_stocks(stocks)
                        print(f"[{time.strftime('%H:%M:%S')}] ✅ OpenAPI 回退更新: {len(stocks)} 檔")
                except Exception as e:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ OpenAPI 回退也失敗: {e}")
                mis_fail_count = 0
                time.sleep(30)  # 回退後多等一下

        else:
            # ── 盤後模式: OpenAPI 每 5 分鐘 ──
            time.sleep(300)

            # 每 120 次循環 (約 10 小時) 重新載入快取
            if cycle % 120 == 0:
                load_pe_yoy_cache()
                load_smart_money_cache()

            try:
                new_stocks = build_stocks_openapi()
                if new_stocks:
                    # 盤後也嘗試用 MIS 覆蓋一次 (可能有盤後零股交易)
                    updated, trade_date = fetch_realtime_mis(new_stocks)
                    stocks = new_stocks
                    save_stocks(stocks)
                    src = f"MIS={updated}" if updated > 0 else "OpenAPI"
                    print(f"[{time.strftime('%H:%M:%S')}] 🌙 盤後更新: {len(stocks)} 檔 ({src})")
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 盤後更新例外: {e}")

if __name__ == "__main__":
    main()
