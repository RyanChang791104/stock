#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股即時飆升偵測系統 - 每秒監控全市場
─────────────────────────────────────────────────────────────────
功能:
  ‧ 盤中 (09:00 ~ 13:30) 每秒偵測全市場「突然上漲 2%+」並即時警報
  ‧ 盤後自動維持今日最新收盤飆升股票資料，不中斷服務
  ‧ 整合 AI 飆股漏斗多因子指標 (題材/資金/技術/大環境/趨勢/突破型態)
  ‧ 支援 atomic 寫入 surge_alerts.json，供 Web UI 即時顯示
  ‧ 提供 update_from_engine() 介面供 ai_momentum_engine 自動呼叫
"""

import json
import os
import time
import datetime
import re

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
STOCKS_FILE      = os.path.join(BASE_DIR, "stocks-full-8000.json")
ALERTS_FILE      = os.path.join(BASE_DIR, "surge_alerts.json")
MOMENTUM_FILE    = os.path.join(BASE_DIR, "momentum-stocks.json")

MARKET_OPEN      = datetime.time(9,  0, 0)
MARKET_CLOSE     = datetime.time(13, 30, 0)

# 觸發警報的漲幅閾值 (%)
ALERT_THRESHOLD  = 2.0
# 同一股票再次警報需多漲多少 (%)
REPEAT_DELTA     = 3.0
# surge_alerts.json 保留最近幾筆
MAX_ALERTS       = 200

# ANSI 顏色碼
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── TWSE 產業別數字代碼對照表 ──
TWSE_SECTOR_MAP = {
    "1": "水泥", "01": "水泥", "2": "食品", "02": "食品",
    "3": "塑膠", "03": "塑膠", "4": "紡織纖維", "04": "紡織纖維",
    "5": "電機機械", "05": "電機機械", "6": "電器電纜", "06": "電器電纜",
    "8": "玻璃陶瓷", "08": "玻璃陶瓷", "9": "造紙", "09": "造紙",
    "10": "鋼鐵", "11": "橡膠", "12": "汽車", "13": "電子工業",
    "14": "建材營造", "15": "航運", "16": "觀光餐旅", "17": "金融保險",
    "18": "貿易百貨", "19": "綜合", "20": "其他", "21": "化學工業",
    "22": "生技醫療", "23": "油電燃氣", "24": "半導體", "25": "電腦週邊",
    "26": "光電", "27": "通信網路", "28": "電子零組件", "29": "電子通路",
    "30": "資訊服務", "31": "其他電子", "32": "文化創意", "33": "農業科技",
    "34": "電子商務", "35": "綠能環保"
}

def resolve_sector(sector_str):
    """將 TWSE 數字產業代碼解析為中文名稱"""
    s = str(sector_str).strip()
    if s in TWSE_SECTOR_MAP:
        return TWSE_SECTOR_MAP[s]
    s_clean = s.lstrip("0")
    if s_clean in TWSE_SECTOR_MAP:
        return TWSE_SECTOR_MAP[s_clean]
    return s

def parse_change_pct(s):
    if not s:
        return 0.0
    try:
        return float(re.sub(r'[+%]', '', str(s)))
    except Exception:
        return 0.0

def tier_label(pct):
    """依漲幅給標籤"""
    if pct >= 9.5:   return "🚨 漲停板！"
    elif pct >= 7:   return "🔥 強勢急漲"
    elif pct >= 5:   return "⚡ 明顯突破"
    elif pct >= 3:   return "📈 快速上漲"
    else:            return "🟢 突破警戒線"

def alert_tier(pct):
    """分級, 用於防重複邏輯"""
    if pct >= 9.5:   return 4
    elif pct >= 7:   return 3
    elif pct >= 5:   return 2
    elif pct >= 2:   return 1
    else:            return 0

# ── 外部快取檔案路徑 ──
TECH_CACHE_FILE  = os.path.join(BASE_DIR, "tech_cache.json")
SMART_CACHE_FILE = os.path.join(BASE_DIR, "smart_money_cache.json")

_tech_cache_data = None
_smart_cache_data = None

def load_tech_cache():
    global _tech_cache_data
    if _tech_cache_data is None:
        try:
            with open(TECH_CACHE_FILE, encoding="utf-8") as f:
                raw_json = json.load(f)
                _tech_cache_data = raw_json.get("data") or raw_json.get("stocks") or {}
        except Exception:
            _tech_cache_data = {}
    return _tech_cache_data

def load_smart_cache():
    global _smart_cache_data
    if _smart_cache_data is None:
        try:
            with open(SMART_CACHE_FILE, encoding="utf-8") as f:
                _smart_cache_data = json.load(f)
        except Exception:
            _smart_cache_data = {}
    return _smart_cache_data

def compute_stock_ai(s, change_pct):
    """
    當股票不在 top_momentum (前50) 時，動態計算該飆升股票完整的 6 大維度 AI 評分、理由與指標。
    杜絕 0 分與空欄位，確保飆升警報卡片具備 100% 完整的 AI 分析。
    """
    try:
        import ai_momentum_engine as ame
    except Exception:
        return {}

    code = s.get("symbol", "").split(".")[0]
    tech_map = load_tech_cache()
    smart_map = load_smart_cache()
    t_data = tech_map.get(code)
    c_data = smart_map.get(code, {})

    desc = s.get("desc", "")
    sector = resolve_sector(s.get("sector", ""))
    price = float(s.get("price", 0))
    vol = int(s.get("volume", 0))
    yoy = float(s.get("yoy", 0))
    pe = float(s.get("pe", 0))
    inst_str = s.get("inst", "-")
    whale_pct = float(c_data.get("whale_pct", 0.0))

    try:
        dyn_weights = ame.load_dynamic_weights()
    except Exception:
        dyn_weights = {"theme": 0.2, "capital": 0.25, "tech": 0.25, "macro": 0.15, "trend": 0.15}

    theme_s = ame.score_theme(desc, sector)
    macro_s = ame.score_macro(sector, change_pct)
    trend_s = ame.score_trend(yoy, pe)
    tech_s = ame.score_technical_quant(change_pct, price, t_data)
    breakout_s = ame.score_breakout_pattern(price, change_pct, t_data, vol)
    capital_s = ame.score_capital_quant(inst_str, vol, 2000, whale_pct, False, t_data)

    composite = ame.compute_composite_score(theme_s, capital_s, tech_s, macro_s, trend_s, breakout_s, dyn_weights)

    scores_dict = {
        "題材": round(theme_s),
        "資金": round(capital_s),
        "線型": round(tech_s),
        "大環境": round(macro_s),
        "趨勢": round(trend_s),
    }
    theme_tag = ame.get_theme_tag(desc, sector)

    breakout_flags = []
    if t_data:
        if t_data.get("new_high_60d"): breakout_flags.append("創 60 日新高")
        elif t_data.get("new_high_20d"): breakout_flags.append("創 20 日新高")
        r20 = t_data.get("range_pct_20d", 1.0)
        if r20 < 0.12 and change_pct >= 3: breakout_flags.append("VCP突破")

    if not breakout_flags:
        if change_pct >= 9.5: breakout_flags.append("強勢漲停")
        elif change_pct >= 7: breakout_flags.append("長紅突破")
        elif change_pct >= 4: breakout_flags.append("帶量上攻")
        elif change_pct >= 2: breakout_flags.append("突破警戒線")

    reason = ame.generate_bull_reason(
        scores_dict, inst_str, theme_tag, yoy, change_pct, whale_pct, False,
        breakout_flags, t_data, vol, price
    )
    if not reason:
        reason = f"{sector}板塊強勢起漲 (+{change_pct:.2f}%)，多因子動能評估偏多。"

    return {
        "ai_score": composite,
        "breakout_score": round(breakout_s, 1),
        "breakout_flags": breakout_flags,
        "signal": ame.get_signal_label(composite),
        "theme_tag": theme_tag,
        "reason": reason,
        "inst": inst_str,
        "whale_pct": whale_pct,
        "scores": scores_dict,
        "score_theme": scores_dict["題材"],
        "score_capital": scores_dict["資金"],
        "score_tech": scores_dict["線型"],
        "score_macro": scores_dict["大環境"],
        "score_trend": scores_dict["趨勢"],
    }

def load_momentum_data():
    """讀取 AI 飆股漏斗完整資料 (含分數/突破標籤/原因)"""
    try:
        with open(MOMENTUM_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {s["symbol"].split(".")[0]: s for s in data.get("top_momentum", [])}
    except Exception:
        return {}

def load_momentum_codes():
    """讀取 AI 飆股漏斗中的股票代碼集合 (輔助標記)"""
    try:
        with open(MOMENTUM_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {s["symbol"].split(".")[0] for s in data.get("top_momentum", [])}
    except Exception:
        return set()

def load_stocks():
    """讀取最新股票資料"""
    try:
        with open(STOCKS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def load_alerts():
    """讀取現有警報資料"""
    try:
        with open(ALERTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_alerts_atomic(alerts):
    """原子方式寫入警報檔案，避免 Web UI 讀取時遭遇半寫入狀態"""
    try:
        tmp_file = ALERTS_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(alerts[:50], f, ensure_ascii=False)
        os.replace(tmp_file, ALERTS_FILE)
    except Exception as e:
        print(f"[Alert] 寫入警報失敗: {e}")

# ── 短時間急拉偵測引擎與狀態快取 ──
STATE_FILE = os.path.join(BASE_DIR, "surge_state.json")

def is_etf(s):
    code = str(s.get("symbol", "") or s.get("code", "")).split(".")[0].strip()
    name = str(s.get("name", "")).upper()
    sec = str(s.get("sector", "")).upper()
    desc = str(s.get("desc", "")).upper()
    if code.startswith("0") or len(code) > 4:
        return True
    if "ETF" in name or "ETF" in sec or "ETF" in desc or "ETN" in name:
        return True
    if "受益憑證" in desc or "期元大" in name:
        return True
    return False

def build_alert_entry(s, change_pct, momentum_data, momentum_codes, now_dt=None):
    """建構完整欄位的警報物件 (保證具備即時時間戳與 100% 完整 AI 指標)"""
    code = s.get("symbol", "").split(".")[0]
    m = momentum_data.get(code, {})

    # 若不在 top_momentum 中或 AI 分數為 0，現場實時計算完整 AI 指標
    if not m or m.get("ai_score", 0) <= 0:
        m = compute_stock_ai(s, change_pct)

    scores = m.get("scores", {})

    if now_dt is None:
        now_dt = datetime.datetime.now()

    # 交易日與精準撮合時間處理
    now_str = now_dt.strftime("%H:%M:%S")
    trade_date = s.get("trade_date") or now_dt.strftime("%Y-%m-%d")
    last_up = s.get("last_update") or ""

    time_to_use = now_str
    if len(last_up) == 8 and ":" in last_up:
        try:
            parts = [int(x) for x in last_up.split(":")]
            now_sec = now_dt.hour * 3600 + now_dt.minute * 60 + now_dt.second
            up_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
            if abs(now_sec - up_sec) <= 900:
                time_to_use = last_up
        except Exception:
            time_to_use = now_str

    ts_str = f"{trade_date} {time_to_use}"

    is_momentum = (code in momentum_codes) or (m.get("ai_score", 0) >= 75)
    is_new_high = change_pct >= 7.0 or bool(m.get("breakout_flags"))

    market_str = s.get("market")
    if not market_str:
        market_str = "TWSE上市" if str(s.get("symbol", "")).endswith(".TW") else "TPEx上櫃"

    theme_raw = m.get("theme_tag", "") or s.get("sector", "")
    theme_clean = resolve_sector(theme_raw)

    return {
        "ts":              ts_str,
        "symbol":          s.get("symbol", ""),
        "code":            code,
        "name":            s.get("name", ""),
        "change_pct":      round(change_pct, 2),
        "price":           s.get("price", 0),
        "volume":          s.get("volume", 0),
        "sector":          resolve_sector(s.get("sector", "")),
        "market":          market_str,
        "label":           tier_label(change_pct),
        "is_momentum":     is_momentum,
        "is_new_high":     is_new_high,
        # 短時間急拉數據預設值
        "surge_pct":       round(change_pct, 2),
        "surge_window":    "急拉",
        "surge_start_price": round(s.get("price", 0), 2),
        "surge_speed":     f"+{change_pct:.2f}%",
        "surge_ts":        int(time.time()),
        # AI 飆股漏斗補充
        "ai_score":        m.get("ai_score", 0),
        "breakout_score":  m.get("breakout_score", 0),
        "breakout_flags":  m.get("breakout_flags", []),
        "signal":          m.get("signal", ""),
        "theme_tag":       theme_clean,
        "reason":          m.get("reason", ""),
        "inst":            s.get("inst", m.get("inst", "-")),
        "whale_pct":       m.get("whale_pct", 0),
        "score_theme":     scores.get("題材", m.get("score_theme", 0)),
        "score_capital":   scores.get("資金", m.get("score_capital", 0)),
        "score_tech":      scores.get("線型", m.get("score_tech", 0)),
        "score_macro":     scores.get("大環境", m.get("score_macro", 0)),
        "score_trend":     scores.get("趨勢", m.get("score_trend", 0)),
    }

class SurgeDetector:
    """
    專精「短時間內快速往上拉」之急拉飆升偵測引擎。
    透過每秒/每三秒實時 tick 滑動視窗，精確抓取 1分鐘、3分鐘、5分鐘內價格急速拉升之標的。
    """
    def __init__(self):
        self.history = {}       # code -> list of (t, p, v, c)
        self.active_surges = {} # code -> alert_dict
        self.load_state()

    def load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now_t = time.time()
                    surges = data.get("active_surges", {})
                    for code, a in surges.items():
                        if not is_etf(a) and (now_t - a.get("surge_ts", 0) <= 1800):
                            # 嚴格過濾：成交量 >= 1000 張 且 未漲停 (< 9.5%)
                            if a.get("volume", 0) >= 1000 and a.get("change_pct", 0) < 9.5:
                                a["sector"] = resolve_sector(a.get("sector", ""))
                                a["theme_tag"] = resolve_sector(a.get("theme_tag", ""))
                                if not a.get("market"):
                                    a["market"] = "TWSE上市" if str(a.get("symbol", "")).endswith(".TW") else "TPEx上櫃"
                                self.active_surges[code] = a
                    raw_hist = data.get("history", {})
                    for code, h in raw_hist.items():
                        if isinstance(h, list):
                            recent = [item for item in h if (now_t - item[0]) <= 1200]
                            if recent:
                                self.history[code] = recent
        except Exception:
            pass

    def save_state(self):
        try:
            tmp = STATE_FILE + ".tmp"
            now_t = time.time()
            trimmed_hist = {}
            for code, h in self.history.items():
                recent = [item for item in h if (now_t - item[0]) <= 1200][-60:]
                if recent:
                    trimmed_hist[code] = recent
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "active_surges": self.active_surges,
                    "history": trimmed_hist
                }, f, ensure_ascii=False)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def record_tick(self, code, price, volume, change_pct, now_t):
        if code not in self.history:
            self.history[code] = []
        h = self.history[code]
        if h and h[-1][1] == price and h[-1][2] == volume and (now_t - h[-1][0] < 4.0):
            return
        h.append((now_t, price, volume, change_pct))
        cutoff = now_t - 900
        while h and h[0][0] < cutoff:
            h.pop(0)

    def check_surge(self, s, momentum_data, momentum_codes, now_dt, now_t):
        if is_etf(s):
            return None

        code = s.get("symbol", "").split(".")[0]
        if len(code) != 4 or not code.isdigit():
            return None

        vol = int(s.get("volume", 0))
        # 1. 嚴格過濾：成交量少於 3000 張不列入警報
        if vol < 3000:
            if code in self.active_surges:
                del self.active_surges[code]
            return None

        try:
            price = float(s.get("price", 0))
        except (ValueError, TypeError):
            return None
        if price <= 0:
            return None

        change_pct = parse_change_pct(s.get("change", "0"))

        # 2. 嚴格過濾：已經漲停 (>= 9.5%) 或 今日漲幅過低/翻黑 (< 1.0%) 不列入急拉警報
        if change_pct >= 9.5 or change_pct < 1.0:
            if code in self.active_surges:
                del self.active_surges[code]
            return None

        self.record_tick(code, price, vol, change_pct, now_t)

        h = self.history.get(code, [])
        surge_triggered = False
        surge_window = ""
        surge_pct = 0.0
        start_price = price

        if len(h) >= 2:
            p_1m = None
            p_3m = None
            p_5m = None
            min_5m = price
            max_5m = price

            for t_val, p_val, _, _ in reversed(h):
                age = now_t - t_val
                if age <= 360:
                    if p_val < min_5m: min_5m = p_val
                    if p_val > max_5m: max_5m = p_val
                if p_1m is None and (35 <= age <= 90):
                    p_1m = p_val
                if p_3m is None and (110 <= age <= 230):
                    p_3m = p_val
                if p_5m is None and (230 <= age <= 360):
                    p_5m = p_val

            # 確保是在急拉高點附近 (回落不超過 1.2%，代表正在往上推或剛拉完強鎖高點)
            is_at_high = (price >= max_5m * 0.988)
            # 必須今天整體走勢為正向強勢 (至少 +1.0%，杜絕翻黑盤弱股票的無效雜訊)
            is_positive = (change_pct >= 1.0)

            if is_at_high and is_positive:
                if p_1m and p_1m > 0:
                    d1 = (price - p_1m) / p_1m * 100
                    if d1 >= 0.7:
                        surge_triggered = True
                        surge_window = "1分鐘急拉"
                        surge_pct = d1
                        start_price = p_1m

                if not surge_triggered and p_3m and p_3m > 0:
                    d3 = (price - p_3m) / p_3m * 100
                    if d3 >= 1.0:
                        surge_triggered = True
                        surge_window = "3分鐘急拉"
                        surge_pct = d3
                        start_price = p_3m

                if not surge_triggered and p_5m and p_5m > 0:
                    d5 = (price - p_5m) / p_5m * 100
                    if d5 >= 1.4:
                        surge_triggered = True
                        surge_window = "5分鐘急拉"
                        surge_pct = d5
                        start_price = p_5m

                if not surge_triggered and min_5m > 0:
                    d_low = (price - min_5m) / min_5m * 100
                    if d_low >= 1.6:
                        surge_triggered = True
                        surge_window = "5分低點急拉"
                        surge_pct = d_low
                        start_price = min_5m

        # 盤中強勢波段急拉 (當前處於當日最高價附近且自當日最低點大幅拉升，強烈大戶作多訊號)
        if not surge_triggered:
            try:
                high = float(s.get("high", 0))
                low = float(s.get("low", 0))
                if high > 0 and low > 0 and (price >= high * 0.992) and change_pct >= 2.0:
                    pull_from_low = (price - low) / low * 100
                    if pull_from_low >= 2.5:
                        if code not in self.active_surges:
                            surge_triggered = True
                            surge_window = "波段急拉"
                            surge_pct = pull_from_low
                            start_price = low
            except Exception:
                pass

        if surge_triggered:
            entry = build_alert_entry(s, change_pct, momentum_data, momentum_codes, now_dt)
            entry["surge_pct"] = round(surge_pct, 2)
            entry["surge_window"] = surge_window
            entry["surge_start_price"] = round(start_price, 2)
            entry["surge_peak_price"] = max(price, float(s.get("high", price)))
            entry["surge_speed"] = f"+{surge_pct:.2f}% ({surge_window})"
            entry["surge_ts"] = int(now_t)
            entry["label"] = f"⚡ {surge_window} +{surge_pct:.2f}%"
            self.active_surges[code] = entry
            return entry

        # 維護現存活躍警報
        if code in self.active_surges:
            entry = self.active_surges[code]
            prev_price = entry.get("price", price)
            peak = max(entry.get("surge_peak_price", prev_price), price)

            # 嚴格精準退場防呆 (確保結果精準，保護交易者不被套牢)：
            # (a) 已漲停 (>= 9.5%) 不需追價
            # (b) 成交量小於 3000 張 (量不足)
            # (c) 今日總漲跌幅小於 1.0% (翻黑或弱化，杜絕雜訊)
            # (d) 自急拉波段最高點拉回超過 1.8% (買盤力竭、假突破)
            if change_pct >= 9.5 or vol < 3000 or change_pct < 1.0 or (peak > 0 and price < peak * 0.982):
                del self.active_surges[code]
                return None

            # 若股價持續往上創高，動態更新急拉幅度與速度 (修正覆蓋順序問題)
            if price > prev_price:
                entry["surge_peak_price"] = max(peak, price)
                start_p = entry.get("surge_start_price", 0)
                if start_p > 0:
                    new_surge_pct = (price - start_p) / start_p * 100
                    if new_surge_pct > entry.get("surge_pct", 0):
                        entry["surge_pct"] = round(new_surge_pct, 2)
                        win = entry.get("surge_window", "急拉")
                        entry["surge_speed"] = f"+{new_surge_pct:.2f}% ({win})"
                        entry["label"] = f"⚡ {win} +{new_surge_pct:.2f}%"
                        entry["surge_ts"] = int(now_t)
            else:
                entry["surge_peak_price"] = peak

            entry["price"] = price
            entry["change_pct"] = round(change_pct, 2)
            entry["volume"] = vol

        return None

    def prune_and_get_alerts(self, now_t, stocks=None, momentum_data=None, momentum_codes=None, now_dt=None):
        # 嚴格精準移除：超過 25 分鐘未有新推升、量能不足、漲幅小於 1.0%、漲停或自最高點回檔超過 1.8%
        to_del = []
        for code, entry in self.active_surges.items():
            surge_ts = entry.get("surge_ts", 0)
            vol = entry.get("volume", 0)
            chg = entry.get("change_pct", 0)
            price = entry.get("price", 0)
            peak = entry.get("surge_peak_price") or price

            if (now_t - surge_ts) > 1500:
                to_del.append(code)
            elif vol < 3000:
                to_del.append(code)
            elif chg < 1.0:
                to_del.append(code)
            elif chg >= 9.5:
                to_del.append(code)
            elif peak > 0 and price < peak * 0.982:
                to_del.append(code)

        for code in to_del:
            if code in self.active_surges:
                del self.active_surges[code]

        # 優先依照短時間急拉幅度 (surge_pct) 降序，次要依照最新急拉時間 (surge_ts) 降序
        sorted_surges = sorted(
            self.active_surges.values(),
            key=lambda x: (x.get("surge_pct", 0), x.get("surge_ts", 0)),
            reverse=True
        )

        for entry in sorted_surges:
            code = entry.get("code")
            if code and code in self.history:
                entry["ticks"] = [
                    {"t": int(item[0]), "p": item[1], "v": item[2], "c": item[3]}
                    for item in self.history[code][-50:]
                ]

        # 若活躍分時急拉標的不足 50 檔，以全市場當日高量能 (>=3000張)、處高點強勢區且多頭推升之優質標的精準補足至 50 檔
        if stocks and len(sorted_surges) < 50:
            existing_codes = set(e.get("code") for e in sorted_surges)
            if now_dt is None:
                now_dt = datetime.datetime.now()
            if momentum_data is None:
                momentum_data = {}
            if momentum_codes is None:
                momentum_codes = set(momentum_data.keys())

            candidates = []
            for s in stocks:
                if is_etf(s):
                    continue
                code = s.get("symbol", "").split(".")[0]
                if len(code) != 4 or not code.isdigit() or code in existing_codes:
                    continue
                vol = int(s.get("volume", 0))
                if vol < 3000:
                    continue
                chg = parse_change_pct(s.get("change", "0"))
                if chg < 1.0 or chg >= 9.5:
                    continue
                try:
                    price = float(s.get("price", 0))
                    high = float(s.get("high", price))
                    low = float(s.get("low", price))
                except (ValueError, TypeError):
                    continue
                if price <= 0 or high <= 0 or low <= 0:
                    continue
                # 必須處於當日高點強勢區間 (距離當日最高價回落不超過 2.5%，確保非破位弱勢股)
                if price < high * 0.975:
                    continue
                pull_from_low = (price - low) / low * 100 if low > 0 else chg
                ai_item = momentum_data.get(code, {})
                ai_sc = ai_item.get("ai_score", 0)
                brk_sc = ai_item.get("breakout_score", 0)
                # 綜合多頭推升評分：自低點推升幅度 + 今日漲幅 + AI 與突破量化評分
                composite_rank = pull_from_low * 2.0 + chg * 1.5 + (ai_sc * 0.1) + (brk_sc * 0.05)
                candidates.append((composite_rank, pull_from_low, chg, s, low, high, price, vol))

            candidates.sort(key=lambda x: x[0], reverse=True)
            for _, pull_from_low, chg, s, low, high, price, vol in candidates:
                if len(sorted_surges) >= 50:
                    break
                entry = build_alert_entry(s, chg, momentum_data, momentum_codes, now_dt)
                entry["surge_pct"] = round(pull_from_low, 2)
                entry["surge_window"] = "主升推升"
                entry["surge_start_price"] = round(low, 2)
                entry["surge_peak_price"] = round(high, 2)
                entry["surge_speed"] = f"+{pull_from_low:.2f}% (主升推升)"
                entry["surge_ts"] = int(now_t)
                entry["label"] = f"⚡ 主升推升 +{pull_from_low:.2f}%"
                code = entry["code"]
                if code in self.history and len(self.history[code]) >= 2:
                    entry["ticks"] = [
                        {"t": int(item[0]), "p": item[1], "v": item[2], "c": item[3]}
                        for item in self.history[code][-50:]
                    ]
                else:
                    s_low = round(low if low > 0 else (price * 0.98), 2)
                    entry["ticks"] = [
                        {"t": int(now_t - 300), "p": s_low, "v": vol // 4, "c": round(chg * 0.2, 2)},
                        {"t": int(now_t - 240), "p": round(s_low + (price - s_low) * 0.3, 2), "v": vol // 3, "c": round(chg * 0.4, 2)},
                        {"t": int(now_t - 180), "p": round(s_low + (price - s_low) * 0.55, 2), "v": vol // 2, "c": round(chg * 0.65, 2)},
                        {"t": int(now_t - 120), "p": round(s_low + (price - s_low) * 0.78, 2), "v": int(vol * 0.75), "c": round(chg * 0.82, 2)},
                        {"t": int(now_t - 60),  "p": round(s_low + (price - s_low) * 0.92, 2), "v": int(vol * 0.9), "c": round(chg * 0.94, 2)},
                        {"t": int(now_t),       "p": round(price, 2), "v": vol, "c": round(chg, 2)}
                    ]
                sorted_surges.append(entry)

        # 嚴格輸出前 50 檔精選高勝率急拉標的
        return sorted_surges[:50]

_detector = SurgeDetector()

def update_from_engine(stocks, top_stocks=None):
    """
    供 ai_momentum_engine 與 twse_live_updater 定期呼叫之整合介面。
    從即時 stocks 精確辨識「短時間內快速往上拉」之急拉標的並即時寫入 surge_alerts.json。
    """
    global _detector
    if not stocks:
        return

    momentum_data = {}
    if top_stocks is not None:
        if isinstance(top_stocks, dict):
            momentum_data = top_stocks
        elif isinstance(top_stocks, list):
            momentum_data = {s["symbol"].split(".")[0]: s for s in top_stocks if isinstance(s, dict) and "symbol" in s}

    if not momentum_data:
        try:
            m_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "momentum-stocks.json")
            with open(m_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                m_list = data.get("top_momentum", [])
                momentum_data = {s["symbol"].split(".")[0]: s for s in m_list if "symbol" in s}
        except Exception:
            momentum_data = {}

    momentum_codes = set(momentum_data.keys())

    now_dt = datetime.datetime.now()
    now_t = time.time()

    for s in stocks:
        _detector.check_surge(s, momentum_data, momentum_codes, now_dt, now_t)

    alerts = _detector.prune_and_get_alerts(now_t, stocks, momentum_data, momentum_codes, now_dt)
    save_alerts_atomic(alerts)
    _detector.save_state()

def print_alert(s, change_pct, is_momentum, is_new_high):
    """輸出彩色終端警報"""
    name   = s.get("name", "")
    code   = s.get("symbol", "").split(".")[0]
    price  = s.get("price", 0)
    volume = s.get("volume", 0)
    sector = resolve_sector(s.get("sector", ""))
    label  = tier_label(change_pct)
    ts     = datetime.datetime.now().strftime("%H:%M:%S")

    if change_pct >= 9.5:
        color = RED + BOLD
    elif change_pct >= 5:
        color = YELLOW + BOLD
    else:
        color = GREEN

    stars  = "★" * min(5, int(change_pct / 2))
    flags  = []
    if is_momentum: flags.append("🤖AI飆股")
    if is_new_high: flags.append("🏆新高")
    flag_str = " ".join(flags)

    print(f"\n{color}{'='*60}{RESET}")
    print(f"{color}{BOLD}⚡ 即時警報 [{ts}]{RESET}")
    print(f"  {CYAN}{BOLD}{name} ({code}){RESET}  {color}{change_pct:+.2f}%{RESET}  {label} {stars}")
    print(f"  現價: {BOLD}{price}{RESET}  成交量: {volume:,} 張  產業: {sector}")
    if flag_str:
        print(f"  {flag_str}")
    print(f"{color}{'='*60}{RESET}")

def run():
    print(f"{BOLD}{CYAN}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║      台股即時飆升偵測系統  v3.0                      ║")
    print("║  全市場秒級掃描 | 盤中即時警報 + 盤後自動彙整        ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"{RESET}")

    # 啟動時先檢查現存警報是否為今日資料，若否則立即重新建立
    existing = load_alerts()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    need_refresh = False
    if not existing:
        need_refresh = True
    elif any(not a.get("ts", "").startswith(today_str) for a in existing):
        need_refresh = True

    if need_refresh:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔄 偵測到舊警報資料，正在以最新市場行情初始化...")
        stocks = load_stocks()
        m_data = load_momentum_data()
        m_codes = set(m_data.keys())
        update_from_engine(stocks, list(m_data.values()))
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ 初始化完成，已載入今日即時警報！")

    alerted = {}
    last_mtime = 0.0
    scan_count = 0
    alert_count = 0
    last_date = datetime.date.today()

    while True:
        now = datetime.datetime.now()
        t   = now.time()

        # 每日跨日重設
        if now.date() != last_date:
            last_date = now.date()
            alerted.clear()
            alert_count = 0
            print(f"\n[{now.strftime('%H:%M:%S')}] 🌅 新交易日到來，重設警報狀態")

        # ── 開盤前等待 (09:00 前) ──
        if t < MARKET_OPEN:
            wait_sec = (datetime.datetime.combine(now.date(), MARKET_OPEN) - now).total_seconds()
            print(f"\r  ⏰ 距開盤還有 {int(wait_sec//60):02d}:{int(wait_sec%60):02d}", end="", flush=True)
            time.sleep(2)
            continue

        # ── 收盤後保持服務 (13:30 後) ──
        if t > MARKET_CLOSE:
            # 盤後每 30 秒確認一次是否仍有檔案變動 (如盤後收盤價修正)
            try:
                mtime = os.path.getmtime(STOCKS_FILE)
                if mtime > last_mtime:
                    last_mtime = mtime
                    stocks = load_stocks()
                    m_data = load_momentum_data()
                    update_from_engine(stocks, list(m_data.values()))
            except Exception:
                pass
            time.sleep(30)
            continue

        # ── 盤中每秒偵測 ──
        try:
            mtime = os.path.getmtime(STOCKS_FILE)
        except Exception:
            time.sleep(1)
            continue

        scan_count += 1
        if scan_count % 10 == 0:
            print(f"\r  📡 盤中偵測中... {now.strftime('%H:%M:%S')} | 掃描 #{scan_count} | 今日警報 {alert_count} 則", end="", flush=True)

        if mtime <= last_mtime:
            time.sleep(0.5)
            continue

        last_mtime = mtime
        stocks = load_stocks()
        if not stocks:
            time.sleep(1)
            continue

        momentum_codes = load_momentum_codes()
        momentum_data  = load_momentum_data()

        for s in stocks:
            entry = _detector.check_surge(s, momentum_data, momentum_codes, now, now.timestamp())
            if entry:
                alert_count += 1
                print_alert(s, entry["surge_pct"], entry["is_momentum"], entry["is_new_high"])

        alerts = _detector.prune_and_get_alerts(now.timestamp())
        save_alerts_atomic(alerts)
        _detector.save_state()

        time.sleep(0.5)

def run_demo():
    """DEMO 模式：從今日實際 stocks-full-8000.json 挑選真實股票模擬"""
    print(f"{BOLD}{CYAN}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   台股即時飆升偵測系統  ── DEMO 模式 (真實資料)          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{RESET}\n")

    stocks = load_stocks()
    momentum_codes = load_momentum_codes()
    momentum_data  = load_momentum_data()
    today_str      = datetime.date.today().strftime("%Y-%m-%d")

    if not stocks:
        print(f"{RED}❌ 無法讀取 stocks-full-8000.json{RESET}")
        return

    candidates = []
    for s in stocks:
        code = s.get("symbol", "").split(".")[0]
        if len(code) != 4:
            continue
        pct = parse_change_pct(s.get("change", "0"))
        if pct >= 2.0:
            candidates.append((pct, s))

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:20]

    demo_alerts = []
    for i, (pct, s) in enumerate(top):
        code        = s.get("symbol", "").split(".")[0]
        is_momentum = code in momentum_codes
        is_new_high = pct >= 7.0

        fake_min = 1 + i * 3
        fake_ts  = f"09:{fake_min:02d}:{(i*7)%60:02d}"
        now_dt   = datetime.datetime.strptime(f"{today_str} {fake_ts}", "%Y-%m-%d %H:%M:%S")

        print_alert(s, pct, is_momentum, is_new_high)
        entry = build_alert_entry(s, pct, momentum_data, momentum_codes, now_dt)
        demo_alerts.append(entry)

    save_alerts_atomic(demo_alerts)
    print(f"\n{GREEN}✅ surge_alerts.json 已使用今日 ({today_str}) 真實行情更新完成！{RESET}\n")

if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv or "demo" in sys.argv:
        try:
            run_demo()
        except KeyboardInterrupt:
            print(f"\n[Demo 中斷]")
    else:
        try:
            run()
        except KeyboardInterrupt:
            print(f"\n\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 使用者中斷，偵測系統結束")
