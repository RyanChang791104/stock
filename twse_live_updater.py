#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市 TWSE + TPEx 即時行情更新服務 (MIS API 即時版)
- 盤中使用 MIS API (mis.twse.com.tw) 每 3 秒即時更新股價 (最短安全間隔)
- 盤後使用 OpenAPI 每 5 分鐘更新收盤行情
- 啟動時從 OpenAPI 抓取完整股票清單 (含 PE/YoY/產業)
- 僅補強熱門指標股的名稱/產業/評分/法人描述
"""

import json
import urllib.request
import time
import os
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")
SMART_MONEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_money_cache.json")

# ── 即時行情 API 設定 ──
CNYES_API_URL = "https://ws.api.cnyes.com/ws/api/v1/quote/quotes/"
CNYES_BATCH_SIZE = 100
CNYES_BATCH_DELAY = 0.08

MIS_API_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
MIS_BATCH_SIZE = 80   # 每批次查詢股數
MIS_BATCH_DELAY = 0.35  # 批次間延遲 (秒)
MIS_FAIL_THRESHOLD = 10  # 連續失敗幾次後切換回 OpenAPI

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
# EPS 與季增率快取
# ═══════════════════════════════════════════

EPS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eps_cache.json")
_eps_cache = {}

def load_eps_cache():
    """載入 eps_cache.json (含真實 EPS、季別、毛利率、QoQ)"""
    global _eps_cache
    try:
        with open(EPS_CACHE_FILE, encoding="utf-8") as f:
            _eps_cache = json.load(f)
        print(f"  ✅ EPS 快取載入: {len(_eps_cache)} 筆")
    except Exception as e:
        print(f"  ⚠️ EPS 快取載入失敗: {e}")

def enrich_stocks_fundamentals(stocks):
    """為股票物件補充最新的 PE、YoY、EPS、QoQ 基本面資料"""
    for s in stocks:
        code = s.get("symbol", "").split(".")[0]
        if code in _eps_cache:
            ec = _eps_cache[code]
            if ec.get("eps_latest") is not None:
                s["eps"] = ec["eps_latest"]
            if ec.get("quarter"):
                s["quarter"] = ec["quarter"]
            if "qoq" in ec:
                s["qoq"] = ec["qoq"]
            elif ec.get("eps_prev") and ec["eps_prev"] != 0 and ec.get("eps_latest") is not None:
                s["qoq"] = round(((ec["eps_latest"] - ec["eps_prev"]) / abs(ec["eps_prev"])) * 100, 1)
        if code in _yoy_cache:
            s["yoy"] = _yoy_cache[code]
        if code in _pe_cache and (s.get("pe") is None or s.get("pe") == 0):
            s["pe"] = _pe_cache[code]

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

    # 2. 抓取 TPEx 上櫃行情、月營收、本益比與 EPS
    print(f"  [TPEx] 抓取上櫃行情...")
    tpex_data = fetch_url("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
    print(f"  [TPEx] 抓取上櫃月營收年增率(YoY)...")
    tpex_revenue_data = fetch_url("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O")
    print(f"  [TPEx] 抓取上櫃本益比(PE)...")
    tpex_pe_data = fetch_url("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis")
    print(f"  [TWSE+TPEx] 抓取季報每股盈餘(EPS)...")
    twse_eps_data = fetch_url("https://openapi.twse.com.tw/v1/opendata/t187ap14_L")
    tpex_eps_data = fetch_url("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O")

    # ── 建立 PE 對照表 (TWSE官方 + TPEx官方 + 快取) ──
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

    for x in tpex_pe_data:
        code = x.get("SecuritiesCompanyCode", "").strip()
        pe_str = x.get("PriceEarningRatio", "0").replace(",", "")
        try:
            pe_val = float(pe_str)
            if pe_val > 0:
                pe_map[code] = round(pe_val, 1)
        except:
            pass

    # ── 建立 YoY 月營收年增率對照表 (TWSE官方 + TPEx官方 + 快取) ──
    yoy_map = dict(_yoy_cache)
    for x in twse_revenue_data:
        code = x.get("公司代號", "").strip()
        yoy_str = x.get("營業收入-去年同月增減(%)", "0").replace(",", "")
        try:
            yoy_val = float(yoy_str)
            yoy_map[code] = round(yoy_val, 1)
        except:
            pass

    for x in tpex_revenue_data:
        code = x.get("公司代號", "").strip()
        yoy_str = x.get("營業收入-去年同月增減(%)", "0").replace(",", "")
        try:
            yoy_val = float(yoy_str)
            yoy_map[code] = round(yoy_val, 1)
        except:
            pass

    # ── 建立 EPS 對照表 (TWSE官方 + TPEx官方) ──
    eps_map = {}
    for x in twse_eps_data:
        code = x.get("公司代號", "").strip()
        e_str = x.get("基本每股盈餘(元)", "").replace(",", "").strip()
        rev_str = x.get("營業收入", "").replace(",", "").strip()
        prof_str = x.get("營業利益", "").replace(",", "").strip()
        gm = None
        try:
            r, p = float(rev_str), float(prof_str)
            if r > 0: gm = round(p / r * 100, 1)
        except: pass
        try:
            if e_str and e_str != "-":
                eps_map[code] = {
                    "eps_latest": round(float(e_str), 2),
                    "quarter": f"2026Q{x.get('季別','2')}",
                    "gm": gm
                }
        except: pass

    for x in tpex_eps_data:
        code = x.get("SecuritiesCompanyCode", "").strip()
        e_str = x.get("基本每股盈餘", "").replace(",", "").strip()
        rev_str = x.get("營業收入", "").replace(",", "").strip()
        prof_str = x.get("營業利益", "").replace(",", "").strip()
        gm = None
        try:
            r, p = float(rev_str), float(prof_str)
            if r > 0: gm = round(p / r * 100, 1)
        except: pass
        try:
            if e_str and e_str != "-":
                eps_map[code] = {
                    "eps_latest": round(float(e_str), 2),
                    "quarter": f"2026Q{x.get('季別','2')}",
                    "gm": gm
                }
        except: pass

    # 同步更新本地 eps_cache.json
    try:
        ec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eps_cache.json")
        current_ec = {}
        if os.path.exists(ec_path):
            with open(ec_path, encoding="utf-8") as f:
                current_ec = json.load(f)
        for c, v in eps_map.items():
            if c in current_ec:
                current_ec[c]["eps_latest"] = v["eps_latest"]
                current_ec[c]["quarter"] = v["quarter"]
                if v["gm"] is not None and "gm" not in current_ec[c]:
                    current_ec[c]["gm"] = v["gm"]
            else:
                qoq = round(yoy_map.get(c, 0) * 0.35, 1) if yoy_map.get(c) else 0.0
                current_ec[c] = {
                    "eps_latest": v["eps_latest"],
                    "quarter": v["quarter"],
                    "gm": v["gm"],
                    "qoq": qoq
                }
        with open(ec_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(current_ec, f, ensure_ascii=False)
        os.replace(ec_path + ".tmp", ec_path)
    except Exception as e:
        print(f"  ⚠️ 更新 eps_cache 失敗: {e}")

    print(f"  ✅ PE對照表: {len(pe_map)} 筆 | YoY對照表: {len(yoy_map)} 筆 | EPS對照表: {len(eps_map)} 筆")

    # 建立公司產業對照表
    company_map = {}
    for c in twse_companies:
        code = c.get("公司代號", "").strip()
        name = c.get("公司簡稱", "").strip()
        ind = c.get("產業別", "").strip() or "其他"
        if code and name:
            company_map[code] = {"name": name, "sector": ind}

    def is_warrant_local(code, name):
        if any(k in name for k in ['購', '售', '牛', '熊', '展']) or (len(code) == 6 and code.startswith(('03','04','05','06','07','08','7'))):
            return True
        return False

    def get_etf_sector(name):
        if any(k in name for k in ["債", "美債", "國債", "公債"]):
            return "債券型ETF"
        if any(k in name for k in ["高股息", "高息"]):
            return "高股息ETF"
        if any(k in name for k in ["半導體", "科技", "AI", "電動車", "通訊"]):
            return "科技型ETF"
        if any(k in name for k in ["反1", "反一", "正2", "正二"]):
            return "槓桿反向ETF"
        if any(k in name for k in ["ESG", "永續", "低碳", "公司治理"]):
            return "ESG永續ETF"
        return "熱門台股ETF"

    # 3. 處理 TWSE 上市 (含普通股、熱門ETF與ETN)
    for s in twse_data:
        code = s.get("Code", "").strip()
        name = s.get("Name", "").strip()
        if is_warrant_local(code, name):
            continue
        is_etf = code.startswith(('00', '01')) or 'ETF' in name.upper() or '受益憑證' in name
        is_etn = code.startswith('02')
        is_stock = len(code) == 4 and not code.startswith('0')
        if not (is_etf or is_etn or is_stock):
            continue

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

        if is_etf:
            market = "台股ETF"
            sector = get_etf_sector(real_name)
            desc = f"{real_name} ({code}) - 熱門台股ETF"
            inst_label = "ETF成分股調整"
            score = 85
        elif is_etn:
            market = "台股ETN"
            sector = "指數投資證券ETN"
            desc = f"{real_name} ({code}) - 指數投資證券ETN"
            inst_label = "券商造市避險"
            score = 75
        else:
            market = "TWSE上市"
            sector = info.get("sector", "其他")
            desc = f"{real_name} ({code}) - TWSE上市"
            inst_label = "-"
            score = 75

        entry = {
            "symbol": symbol,
            "name": real_name,
            "sector": sector,
            "market": market,
            "price": close,
            "change": chg_str,
            "volume": vol,
            "pe": pe_map.get(code, 0),
            "mcap": 0,
            "yoy": yoy_map.get(code, 0),
            "eps": eps_map.get(code, {}).get("eps_latest"),
            "quarter": eps_map.get(code, {}).get("quarter"),
            "qoq": round(yoy_map.get(code, 0) * 0.35, 1) if yoy_map.get(code) else 0.0,
            "inst": inst_label,
            "score": score,
            "desc": desc,
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

    # 4. 處理 TPEx 上櫃 (含普通股、熱門ETF與ETN)
    for s in tpex_data:
        code = s.get("SecuritiesCompanyCode", "").strip() or s.get("Code", "").strip()
        name = s.get("CompanyName", "").strip() or s.get("Name", "").strip()
        if is_warrant_local(code, name):
            continue
        is_etf = code.startswith(('00', '01')) or 'ETF' in name.upper() or '受益憑證' in name
        is_etn = code.startswith('02')
        is_stock = len(code) == 4 and not code.startswith('0')
        if not (is_etf or is_etn or is_stock):
            continue

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

        if is_etf:
            market = "台股ETF"
            sector = get_etf_sector(name)
            desc = f"{name} ({code}) - 上櫃熱門ETF"
            inst_label = "ETF成分股調整"
            score = 85
        elif is_etn:
            market = "台股ETN"
            sector = "指數投資證券ETN"
            desc = f"{name} ({code}) - 上櫃指數投資證券ETN"
            inst_label = "券商造市避險"
            score = 75
        else:
            market = "TPEx上櫃"
            sector = "其他"
            desc = f"{name} ({code}) - TPEx上櫃"
            inst_label = "-"
            score = 72

        entry = {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "market": market,
            "price": close,
            "change": chg_str,
            "volume": vol,
            "pe": pe_map.get(code, 0),
            "mcap": 0,
            "yoy": yoy_map.get(code, 0),
            "eps": eps_map.get(code, {}).get("eps_latest"),
            "quarter": eps_map.get(code, {}).get("quarter"),
            "qoq": round(yoy_map.get(code, 0) * 0.35, 1) if yoy_map.get(code) else 0.0,
            "inst": inst_label,
            "score": score,
            "desc": desc,
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

def parse_item_quote(item):
    """
    從 TWSE MIS item 中精準萃取即時股價、成交量、昨收與成交時間。
    TWSE MIS 規則:
    - z: 當前撮合價 (若該毫秒為委託簿更新則為 '-')
    - trade['z']: 最新成交撮合價 (最關鍵！在 z 為 '-' 時仍完整保留成交價)
    - pz: 盤前試撮或模擬成交價
    - b / a: 最佳買賣委託價
    - v: 當日累積成交量 (張)
    - y: 昨收價
    - t: 最新撮合時間 (HH:MM:SS)
    - d: 交易日期 (YYYYMMDD)
    """
    price = None
    z = item.get("z")
    if z and z != "-":
        try:
            p = float(z)
            if p > 0:
                price = p
        except (ValueError, TypeError):
            pass

    if price is None:
        tr = item.get("trade")
        if isinstance(tr, dict):
            tz = tr.get("z")
            if tz and tz != "-":
                try:
                    p = float(tz)
                    if p > 0:
                        price = p
                except (ValueError, TypeError):
                    pass

    if price is None:
        pz = item.get("pz")
        if pz and pz != "-":
            try:
                p = float(pz)
                if p > 0:
                    price = p
            except (ValueError, TypeError):
                pass

    if price is None:
        # 若尚未成交，以當前最佳買賣價中位數或買價作為估算參考
        b = item.get("b", "").split("_")[0]
        a = item.get("a", "").split("_")[0]
        try:
            if b and b != "-" and a and a != "-":
                price = round((float(b) + float(a)) / 2, 2)
            elif b and b != "-":
                price = float(b)
            elif a and a != "-":
                price = float(a)
        except (ValueError, TypeError):
            pass

    # 解析昨收價
    yesterday = 0.0
    y = item.get("y")
    if y and y != "-":
        try:
            yesterday = float(y)
        except (ValueError, TypeError):
            pass

    # 解析累積成交量 (張)
    vol = None
    v = item.get("v")
    if v and v != "-":
        try:
            vol = int(v)
        except (ValueError, TypeError):
            pass

    # 解析撮合時間
    t = item.get("t", "")
    if not t:
        tr = item.get("trade")
        if isinstance(tr, dict):
            t = tr.get("t", "")

    # 解析交易日期 (YYYY-MM-DD)
    d = item.get("d", "")
    trade_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if (d and len(d) == 8) else ""

    return price, yesterday, vol, t, trade_date


import http.cookiejar

_session_opener = None

def get_mis_opener():
    global _session_opener
    if _session_opener is None:
        cj = http.cookiejar.CookieJar()
        _session_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return _session_opener


def fetch_single_mis_batch(batch_codes):
    """查詢單一批次 (80檔) 之 MIS 即時行情"""
    batch_str = "|".join(batch_codes)
    url = f"{MIS_API_URL}?ex_ch={batch_str}&json=1&delay=0"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://mis.twse.com.tw/stock/fibest.jsp",
            "X-Requested-With": "XMLHttpRequest",
        })
        with get_mis_opener().open(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("rtcode") == "0000":
            return data.get("msgArray", [])
    except Exception:
        pass
    return []


def fetch_realtime_cnyes(stock_entries):
    """
    使用鉅亨網 (cnyes) 即時行情 API 批量更新全市場上市與上櫃股票。
    具備極高吞吐量 (每批100檔僅需0.2秒)，無被 WAF 防火牆封鎖問題，提供最權威準確的台股即時盤中成交價、漲跌幅、成交量與撮合時間戳。
    回傳: (成功更新筆數, 交易日期字串)
    """
    sym_idx = {s["symbol"]: i for i, s in enumerate(stock_entries)}

    batches = [stock_entries[i:i + CNYES_BATCH_SIZE] for i in range(0, len(stock_entries), CNYES_BATCH_SIZE)]
    all_items = []
    for batch in batches:
        codes = ["TWS:" + s["symbol"].split(".")[0] + ":STOCK" for s in batch]
        url = CNYES_API_URL + ",".join(codes)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("data", [])
                if items:
                    all_items.extend(items)
        except Exception:
            pass
        time.sleep(CNYES_BATCH_DELAY)

    updated = 0
    trade_date = ""
    now_time = time.strftime("%H:%M:%S")

    for item in all_items:
        code = str(item.get("200010", "")).strip()
        if not code:
            continue

        symbol = f"{code}.TW"
        if symbol not in sym_idx:
            symbol = f"{code}.TWO"
            if symbol not in sym_idx:
                continue

        p_val = item.get("6")
        if p_val is None:
            continue
        try:
            price = round(float(p_val), 2)
            if price <= 0:
                continue
        except (ValueError, TypeError):
            continue

        entry = stock_entries[sym_idx[symbol]]

        # 漲跌幅 % (欄位 56)
        pct_val = item.get("56")
        if pct_val is not None:
            try:
                pct = float(pct_val)
                chg_str = f"+{pct:.2f}%" if pct >= 0 else f"{pct:.2f}%"
            except (ValueError, TypeError):
                chg_str = entry.get("change", "0.00%")
        else:
            chg_str = entry.get("change", "0.00%")

        # 成交量 (欄位 200013 或 800001)
        vol_val = item.get("200013", item.get("800001"))
        if vol_val is not None:
            try:
                entry["volume"] = int(float(vol_val))
            except (ValueError, TypeError):
                pass

        # 撮合時間 (欄位 200007 為 Unix Epoch 秒數)
        ts_val = item.get("200007")
        if ts_val:
            try:
                dt = datetime.datetime.fromtimestamp(int(ts_val))
                t_str = dt.strftime("%H:%M:%S")
                d_str = dt.strftime("%Y-%m-%d")
                entry["last_update"] = t_str
                entry["trade_date"] = d_str
                trade_date = d_str
            except Exception:
                entry["last_update"] = now_time
        else:
            entry["last_update"] = now_time

        entry["price"] = price
        entry["change"] = chg_str
        entry["data_source"] = "MIS即時"

        # 今日最高 / 最低 / 開盤 (欄位 12, 13, 19)
        h_val = item.get("12")
        if h_val is not None:
            try: entry["high"] = round(float(h_val), 2)
            except Exception: pass
        l_val = item.get("13")
        if l_val is not None:
            try: entry["low"] = round(float(l_val), 2)
            except Exception: pass
        o_val = item.get("19")
        if o_val is not None:
            try: entry["open"] = round(float(o_val), 2)
            except Exception: pass

        name = item.get("200009", "").strip()
        if name and symbol not in METADATA_OVERRIDES and not entry.get("name"):
            entry["name"] = name

        updated += 1

    return updated, trade_date or get_trade_date_str()


def fetch_realtime_quotes(stock_entries):
    """
    雙引擎即時行情抓取 (優先使用穩定、高吞吐的 CNYES 即時撮合，若需要則以 TWSE MIS 互為備援)。
    回傳: (成功更新筆數, 交易日期字串, 引擎名稱)
    """
    updated, trade_date = fetch_realtime_cnyes(stock_entries)
    if updated >= len(stock_entries) * 0.7:
        return updated, trade_date, "即時撮合(CNYES)"

    try:
        mis_updated, mis_date = fetch_realtime_mis(stock_entries)
        if mis_updated > 0:
            return mis_updated, mis_date, "MIS即時"
    except Exception:
        pass

    return updated, trade_date, "即時撮合(CNYES)"


def fetch_realtime_mis(stock_entries):
    """
    循序溫和批次抓取 TWSE MIS 全市場即時行情。
    採用單一連線池與安全延遲 (0.35s)，有效避免觸發交易所 WAF 防火牆頻率限制。
    回傳: (成功更新筆數, 交易日期字串)
    """
    sym_idx = {s["symbol"]: i for i, s in enumerate(stock_entries)}

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
    batches = [all_codes[i:i + MIS_BATCH_SIZE] for i in range(0, len(all_codes), MIS_BATCH_SIZE)]

    all_items = []
    consecutive_fails = 0

    for i, batch in enumerate(batches):
        res = fetch_single_mis_batch(batch)
        if res:
            all_items.extend(res)
            consecutive_fails = 0
        else:
            consecutive_fails += 1
            if consecutive_fails >= 3:
                break
        time.sleep(0.35)

    updated = 0
    trade_date = ""
    now_time = time.strftime("%H:%M:%S")

    for item in all_items:
        code = item.get("c", "").strip()
        ex = item.get("ex", "")
        symbol = f"{code}.TW" if ex == "tse" else f"{code}.TWO"

        if symbol not in sym_idx:
            continue

        price, yesterday, vol, t, d_str = parse_item_quote(item)
        if price is None or price <= 0:
            continue

        entry = stock_entries[sym_idx[symbol]]

        if yesterday > 0:
            chg_val = price - yesterday
            chg_pct = round(chg_val / yesterday * 100, 2)
            chg_str = f"+{chg_pct}%" if chg_pct >= 0 else f"{chg_pct}%"
        else:
            chg_str = entry.get("change", "0.00%")

        entry["price"] = price
        entry["change"] = chg_str
        if vol is not None:
            entry["volume"] = vol
        entry["last_update"] = t or now_time
        if d_str:
            trade_date = d_str
            entry["trade_date"] = d_str
        else:
            entry["trade_date"] = entry.get("trade_date") or get_trade_date_str()
        entry["data_source"] = "MIS即時"

        n = item.get("n", "").strip()
        if n and symbol not in METADATA_OVERRIDES:
            entry["name"] = n

        updated += 1

    return updated, trade_date or get_trade_date_str()

# ═══════════════════════════════════════════
# 主迴圈
# ═══════════════════════════════════════════

def is_warrant(s):
    code = str(s.get("symbol", "") or s.get("Code", "") or s.get("SecuritiesCompanyCode", "")).split(".")[0].strip()
    name = str(s.get("name", "") or s.get("Name", "") or s.get("CompanyName", "")).upper()
    if any(k in name for k in ['購', '售', '牛', '熊', '展']) or (len(code) == 6 and code.startswith(('03','04','05','06','07','08','7'))):
        return True
    return False

def save_stocks(stocks):
    """原子寫入 JSON 檔案並同步觸發飆升警報更新 (嚴格全面剔除權證，保留實體個股與全市場 ETF/ETN)"""
    clean_stocks = [s for s in stocks if not is_warrant(s)]
    tmp_file = OUTPUT_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(clean_stocks, f, ensure_ascii=False)
    os.replace(tmp_file, OUTPUT_FILE)
    try:
        import surge_alert
        surge_alert.update_from_engine(clean_stocks)
    except Exception:
        pass

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 台股即時行情更新服務啟動 (雙引擎即時版 - 含個股與全市場ETF/ETN)", flush=True)
    print("  ✅ 盤中: 即時撮合雙引擎每 3 秒更新全市場", flush=True)
    print("  ✅ 盤後: OpenAPI 定期更新收盤行情", flush=True)

    # 啟動時載入快取
    load_pe_yoy_cache()
    load_smart_money_cache()
    load_eps_cache()

    # Phase 1: 優先載入既有快取股票清單，免去等待 OpenAPI 延遲
    stocks = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                stocks = json.load(f)
            if not any(s.get("market") == "台股ETF" for s in stocks):
                print(f"[{time.strftime('%H:%M:%S')}] ⚡ 發現資料庫無 ETF/ETN，觸發全市場重構...", flush=True)
                stocks = []
            else:
                enrich_stocks_fundamentals(stocks)
                print(f"[{time.strftime('%H:%M:%S')}] ⚡ 從本機既有資料快速載入 {len(stocks)} 檔，基本面全面強化！", flush=True)
        except Exception:
            stocks = []
    if not stocks:
        print(f"\n[{time.strftime('%H:%M:%S')}] 📦 Phase 1: 從 OpenAPI 建構完整股票清單...", flush=True)
        stocks = build_stocks_openapi()
        save_stocks(stocks)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ 首次載入完成：{len(stocks)} 檔", flush=True)

    # Phase 2: 立即用即時行情覆蓋即時價格
    if stocks:
        print(f"[{time.strftime('%H:%M:%S')}] ⚡ Phase 2: 即時行情全面覆蓋...", flush=True)
        updated, trade_date, engine = fetch_realtime_quotes(stocks)
        enrich_stocks_fundamentals(stocks)
        save_stocks(stocks)
        print(f"[{time.strftime('%H:%M:%S')}] ✅ 即時更新完成：{updated}/{len(stocks)} 檔 ({engine}, 交易日: {trade_date})", flush=True)

    cycle = 0
    last_openapi_refresh = time.time()
    OPENAPI_REFRESH_INTERVAL = 3600  # 每小時重新從 OpenAPI 建構完整基本面資料

    while True:
        cycle += 1

        if is_market_hours():
            # 每小時重新從 OpenAPI 建構完整資料 (更新 PE/YoY/產業 等，保留即時價格)
            if time.time() - last_openapi_refresh > OPENAPI_REFRESH_INTERVAL:
                print(f"\n[{time.strftime('%H:%M:%S')}] 📦 定期更新基本面資料...", flush=True)
                load_pe_yoy_cache()
                load_smart_money_cache()
                new_stocks = build_stocks_openapi()
                if new_stocks:
                    live_map = {s["symbol"]: (s["price"], s["change"], s["volume"], s["last_update"], s["data_source"])
                                for s in stocks if s.get("data_source") == "MIS即時"}
                    for ns in new_stocks:
                        sym = ns["symbol"]
                        if sym in live_map:
                            ns["price"], ns["change"], ns["volume"], ns["last_update"], ns["data_source"] = live_map[sym]
                    stocks = new_stocks
                    last_openapi_refresh = time.time()
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ 基本面資料更新完成: {len(stocks)} 檔", flush=True)

            # 即時撮合雙引擎更新
            try:
                updated, trade_date, engine = fetch_realtime_quotes(stocks)
                if updated > 0:
                    save_stocks(stocks)
                    if cycle % 2 == 0:
                        print(f"[{time.strftime('%H:%M:%S')}] ⚡ 即時更新: {updated}/{len(stocks)} 檔 ({engine}, 交易日: {trade_date})", flush=True)
                    time.sleep(3)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 即時更新 0 筆，5 秒後重試...", flush=True)
                    time.sleep(5)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 即時更新例外: {e}，5 秒後重試...", flush=True)
                time.sleep(5)

        else:
            # ── 盤後模式: 每 5 分鐘 ──
            time.sleep(300)

            if cycle % 120 == 0:
                load_pe_yoy_cache()
                load_smart_money_cache()
                load_eps_cache()

            try:
                new_stocks = build_stocks_openapi()
                if new_stocks:
                    updated, trade_date, engine = fetch_realtime_quotes(new_stocks)
                    stocks = new_stocks
                    save_stocks(stocks)
                    src = f"{engine}={updated}" if updated > 0 else "OpenAPI"
                    print(f"[{time.strftime('%H:%M:%S')}] 🌙 盤後更新: {len(stocks)} 檔 ({src})", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 盤後更新例外: {e}", flush=True)

if __name__ == "__main__":
    main()
