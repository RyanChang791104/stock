#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 超強飆股多因子評分引擎 (2026年量化升級版 - RSI/KD/MACD/ATR)
結合: 法人動向 + 技術線型 + 題材熱度 + 成交量能 + 股價動能 + 集保大戶籌碼
每 30 秒掃描全台股 6,000+ 標的，讀取 tech_cache.json 並輸出 momentum-stocks.json
"""

import json
import os
import time
import math
import re

INPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stocks-full-8000.json")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "momentum-stocks.json")

# ── 題材熱度關鍵字庫 ── (2026年7月最新 - 結合網路最新趨勢)
THEME_KEYWORDS = {
    # 頂級 AI 題材 (100分)
    "CPO|矽光子|1\.6T|co-packaged|800G.*雷射|Silicon Photonics|COUPE": 100,
    "CoWoS|GB200|NVL72|NVL36|Blackwell|B200|B300": 98,
    "ASIC.*AI|AI.*ASIC|雲端.*自研|CSP.*晶片": 96,
    "BMC|伺服器管理|遠端管理晶片": 95,
    # 高熱 AI 伺服器鏈 (90分)
    "水冷|CDU|冷却分配|液冷散熱|均熱|兩相散熱": 92,
    "AI.*伺服器|伺服器.*AI|機架|Rack|機櫃": 90,
    "ABF.*載板|FC-BGA|先進封裝": 88,
    "CCL|銅箔基板|高階.*基板": 87,
    # 重電 / 電網 (86分)
    "超高壓.*變壓器|GIS.*開關|電網|強韌.*電網": 86,
    "NAND.*SSD|企業級.*SSD|Flash.*控制": 85,
    # 半導體設備材料 (83分)
    "CMP|鑽石碟|拋光墊|探針卡|測試介面": 83,
    "濕製程|清洗設備|點膠.*設備": 81,
    "USB4|PCIe|高速.*介面|Ethernet.*晶片": 80,
    # ==== 2026年7月新增熱門題材 ====
    # 漲價概念股 (2026年7月最熱題材之一)
    "漲價|調漲|報價.*調漲|供給緊張|產能排擠|缺貨|庫存補庫": 84,
    # HBM/記憶體 (AI核心)
    "HBM|DDR5|高頻寬記憶體|SLC.*NAND|利基型記憶體": 88,
    # 功率半導體 / 被動元件
    "功率半導體|MOSFET|IGBT|SiC|被動元件|MLCC|電感|電阻": 78,
    # 機器人 / 智慧自動化
    "機器人|自動化|人形機器人|Humanoid|Cobot|機械手臂": 82,
    # 金融防禦 (美股崩盤後的避風港)
    "金控|銀行|保險|證券|投信": 65,
    # 生技醫療 (7月營收概念)
    "生技|醫療|新藥|原料藥|疫苗|醫材": 68,
    # 一般 AI/半導體 (72分)
    "AI|半導體|晶片|製程|封裝|Nvidia|TSMC|台積電": 72,
    # 光電通訊 (75分)
    "光收發|光纖|WDM|帶狀光纖|FA": 76,
}

# ── 法人動向關鍵字評分 ──
INST_SCORES = {
    "外資投信雙買": 100, "三大法人同步買": 100,
    "投信連買6日": 98,  "投信連買5日": 97,  "外資連買4日": 95,
    "投信連買3日": 92,  "投信鎖碼3日": 90,
    "外資大舉加碼": 90, "外資大買": 88,
    "投信連買": 87,     "投信鎖碼": 87,
    "法人加碼": 85,     "外資加碼": 83,     "投信加碼": 83,
    "外資買進": 80,     "投信買進": 80,
    "主力連續加碼": 82, "主力放量突破": 80,
    "主力鎖碼": 78,     "外資回補": 70,     "法人回補": 68,
    "外資買超": 78,     "外資關注": 60,
    "-": 30,
}

def parse_change_pct(change_str):
    """解析漲跌幅字串為浮點數"""
    if not change_str:
        return 0.0
    try:
        return float(re.sub(r'[+%]', '', change_str))
    except:
        return 0.0

def score_institutional(inst_str):
    """法人動向評分 (0-100)"""
    if not inst_str or inst_str == "-":
        return 30
    for keyword, score in INST_SCORES.items():
        if keyword in inst_str:
            return score
    return 40

def score_theme(desc_str, sector_str):
    """題材熱度評分 (0-100)"""
    combined = (desc_str or "") + " " + (sector_str or "")
    best = 55  # 最低基礎分
    for pattern, score in THEME_KEYWORDS.items():
        if re.search(pattern, combined, re.IGNORECASE):
            best = max(best, score)
    return best

def score_technical_quant(change_pct, price, t_data):
    """均線 + 布林通道 + RSI + KD + MACD 綜合量化技術指標評分"""
    if not t_data:
        # Fallback 舊的日漲跌幅評分
        if change_pct >= 8:     base = 90
        elif change_pct >= 6:   base = 85
        elif change_pct >= 4:   base = 80
        elif change_pct >= 2:   base = 72
        elif change_pct >= 0.5: base = 65
        elif change_pct >= 0:   base = 55
        elif change_pct >= -2:  base = 45
        elif change_pct >= -5:  base = 35
        else:                   base = 20
        return base
        
    sma5 = t_data.get("sma5", 0)
    sma10 = t_data.get("sma10", 0)
    sma20 = t_data.get("sma20", 0)
    upper_band = t_data.get("upper_band", 0)
    band_width = t_data.get("band_width", 99.0)
    
    rsi = t_data.get("rsi", 50.0)
    k = t_data.get("k", 50.0)
    d = t_data.get("d", 50.0)
    macd_hist = t_data.get("macd_hist", 0.0)
    
    kd_gc = t_data.get("kd_golden_cross", False)
    macd_gc = t_data.get("macd_golden_cross", False)
    sma_gc = t_data.get("golden_cross_5_20", False)
    
    score = 50.0  # 基礎分
    
    # 1. 均線排列與黃金交叉
    if price > sma5 > sma10 > sma20:
        score += 12
    if sma_gc:
        score += 10
        
    # 2. 布林通道緊縮後向上突破
    if band_width < 0.12 and price >= upper_band * 0.99:
        score += 20
        
    # 3. RSI 動能指標
    if 50.0 <= rsi <= 70.0:
        score += 15  # 強勢多頭段
    elif rsi >= 80.0:
        score -= 25  # 極度超買，高檔阻力大，防追高
    elif rsi < 35.0:
        score -= 15  # 極度弱勢
        
    # 4. KD 隨機指標黃金交叉
    if kd_gc:
        if k <= 35.0:
            score += 25  # 低檔黃金交叉，極強轉折買訊
        else:
            score += 10  # 中檔強勢黃金交叉
            
    # 5. MACD 趨勢指標
    if macd_gc:
        score += 15  # 柱狀圖翻紅，趨勢翻多買點
    elif macd_hist > 0:
        score += 8   # 多頭趨勢持續
        
    # 6. 回測月線支撐
    bias = (price - sma20) / sma20 if sma20 > 0 else 0
    if -0.02 <= bias <= 0.03:
        score += 10
        
    # 7. 極大乖離懲罰
    if bias > 0.25:
        score -= 20
        
    # 微調
    score += change_pct * 0.3
    
    return min(100.0, max(10.0, score))

def score_capital_quant(inst_str, volume, market_avg_vol, whale_pct, retail_exiting, t_data):
    """資金籌碼評分: 結合量能爆發比例、大戶吸籌、投信外資動向"""
    inst_s = score_institutional(inst_str)
    
    # 計算量能爆量比率 (以個股自體 SMA20 均量為對照基準，最為精準)
    vol_s = 50.0
    if t_data and t_data.get("vol_sma20", 0) > 0:
        vol_sma20 = t_data["vol_sma20"]
        ratio = volume / vol_sma20
        if ratio >= 2.0:
            vol_s = 98.0
        elif ratio >= 1.5:
            vol_s = 88.0
        elif ratio >= 1.0:
            vol_s = 75.0
        elif ratio >= 0.5:
            vol_s = 55.0
        else:
            vol_s = 40.0
    else:
        # Fallback 到大盤平均成交量
        if volume <= 0:
            vol_s = 30.0
        elif market_avg_vol <= 0:
            vol_s = 50.0
        else:
            ratio = volume / market_avg_vol
            if ratio >= 4:   vol_s = 90.0
            elif ratio >= 2: vol_s = 80.0
            elif ratio >= 1: vol_s = 68.0
            else:            vol_s = 50.0
            
    # 大戶持股比例加權
    whale_s = 50.0
    if whale_pct > 0:
        if whale_pct >= 75:   whale_s = 100.0
        elif whale_pct >= 60: whale_s = 85.0
        elif whale_pct >= 40: whale_s = 65.0
        else:                 whale_s = 45.0
        
    if retail_exiting:
        whale_s = min(100.0, whale_s + 15.0)  # 散戶退場大戶吸籌
        
    # 資金 = 35% 法人 + 30% 爆量比率 + 35% 大戶集保鎖碼度
    return (inst_s * 0.35) + (vol_s * 0.30) + (whale_s * 0.35)

def score_macro(sector, change_pct):
    """大環境/板塊分析"""
    if "半導體" in sector or "電腦" in sector or "電子" in sector:
        base = 80
    elif "電機" in sector or "電纜" in sector or "綠能" in sector:
        base = 78
    elif "金融" in sector or "保險" in sector or "銀行" in sector:
        base = 72
    elif "生技" in sector or "醫療" in sector:
        base = 70
    else:
        base = 60
        
    if change_pct > 3:
        base += 15
    elif change_pct > 0:
        base += 8
    elif change_pct > -2:
        base += 0
    elif change_pct > -5:
        base -= 5
    else:
        base -= 15
        
    return min(100, max(20, base))

def score_trend(yoy, pe):
    """基本面與估值趨勢評分"""
    if yoy > 50: fund_s = 95
    elif yoy > 20: fund_s = 85
    elif yoy > 0:  fund_s = 70
    elif yoy > -10: fund_s = 50
    else: fund_s = 30
    
    if 0 < pe < 20: val_s = 90
    elif 20 <= pe < 40: val_s = 72
    elif pe >= 40: val_s = 50
    else: val_s = 40
    
    return (fund_s * 0.7) + (val_s * 0.3)

def compute_composite_score(theme_s, capital_s, tech_s, macro_s, trend_s):
    """最終飆股綜合評分 (0-100) — 依題材、資金、線型、大環境、趨勢加權"""
    weights = {
        "theme":   0.25,  # 題材
        "capital": 0.25,  # 資金
        "tech":    0.20,  # 線型
        "macro":   0.15,  # 大環境
        "trend":   0.15,  # 趨勢
    }
    score = (theme_s * weights["theme"] +
             capital_s * weights["capital"] +
             tech_s * weights["tech"] +
             macro_s * weights["macro"] +
             trend_s * weights["trend"])
    return round(score, 1)

def generate_bull_reason(scores, inst_str, theme_tag, yoy, change_pct, whale_pct, retail_exiting, tech_flags, t_data, volume, price):
    reasons = []
    
    # 1. 檢查技術型態
    if "乖離過高" in tech_flags:
        reasons.append("⚠️短期乖離過大防拉回")
    elif "布林軌道強攻" in tech_flags:
        reasons.append("🚀布林通道窄幅緊縮後帶量突破上軌(波動爆發)")
    elif "突破月線" in tech_flags:
        reasons.append("📈帶量突破月均線(中期波段起漲)")
    elif "跌深起漲" in tech_flags:
        reasons.append("📉股價超跌回穩，帶量低檔強勢反彈")
    elif "月線上檔" in tech_flags:
        reasons.append("🛡️回測月均線確認有守")
        
    # 進階量化技術指標訊號
    if t_data:
        sma5 = t_data.get("sma5", 0)
        sma10 = t_data.get("sma10", 0)
        sma20 = t_data.get("sma20", 0)
        if sma5 > sma10 > sma20:
            reasons.append("📊均線呈現完美多頭排列")
            
        rsi = t_data.get("rsi", 50)
        if rsi >= 65 and "乖離過高" not in tech_flags:
            reasons.append("RSI多頭增強")
        elif rsi <= 35:
            reasons.append("RSI低檔鈍化")
            
        if t_data.get("kd_golden_cross", False):
            if t_data.get("k", 50) <= 35:
                reasons.append("KD低檔強勢黃金交叉(轉折點)")
            else:
                reasons.append("KD黃金交叉")
                
        if t_data.get("macd_golden_cross", False):
            reasons.append("MACD翻紅買訊")
            
    # 2. 籌碼大戶集中
    if retail_exiting:
        reasons.append("🚨股民總數減少但千張大戶持股增加(籌碼大清洗)")
    elif whale_pct >= 70:
        reasons.append(f"🐳千張大戶重度鎖碼({whale_pct}%)")
        
    # 3. 量能爆發
    if t_data and t_data.get("vol_sma20", 0) > 0:
        ratio = volume / t_data["vol_sma20"]
        if ratio >= 2.0:
            reasons.append("🔥今日成交量達月均量2倍以上")
            
    # 4. 法人與營收題材
    if scores["資金"] >= 80 and inst_str != "-":
        reasons.append(f"籌碼面{inst_str}")
    if scores["題材"] >= 85:
        reasons.append(f"聚焦熱門題材【{theme_tag}】")
    if yoy > 25:
        reasons.append(f"基本面月營收高速成長(YoY+{yoy}%)")
        
    # 5. 結合 Wilder's ATR 量化交易帶
    if t_data and t_data.get("atr", 0) > 0:
        atr = t_data["atr"]
        entry_min = price - 0.5 * atr
        entry_max = price + 0.2 * atr
        stop = price - 2.0 * atr
        reasons.append(f"🔑量化目標區:{entry_min:.1f}~{entry_max:.1f}，停損防線:{stop:.1f}")
        
    if not reasons:
        reasons.append("多方趨勢格局穩定，籌碼集中度佳")
        
    return "，".join(reasons) + "。"

def get_signal_label(score):
    if score >= 90: return "🔥 超強飆股"
    elif score >= 82: return "🚀 強勢突破"
    elif score >= 75: return "⚡ 攻勢蓄積"
    elif score >= 65: return "📈 緩步向上"
    else: return "😴 觀望中"

def get_theme_tag(desc, sector):
    combined = (desc or "") + " " + (sector or "")
    if re.search(r"CPO|矽光子|1\.6T|COUPE", combined): return "矽光子 CPO"
    if re.search(r"CoWoS|GB200|NVL", combined): return "CoWoS AI伺服器"
    if re.search(r"水冷|CDU|液冷|兩相散熱", combined): return "AI水冷散熱"
    if re.search(r"BMC|伺服器管理", combined): return "伺服器管理晶片"
    if re.search(r"ASIC.*AI|AI.*ASIC", combined): return "雲端自研ASIC"
    if re.search(r"CCL|銅箔基板", combined): return "AI高階基板"
    if re.search(r"超高壓.*變壓器|電網|強韌", combined): return "強網重電"
    if re.search(r"ABF|FC-BGA|先進封裝", combined): return "先進封裝載板"
    if re.search(r"光收發|800G|光纖", combined): return "高速光通訊"
    if re.search(r"NAND|SSD|Flash", combined): return "AI企業SSD"
    if re.search(r"HBM|DDR5|記憶體", combined): return "HBM/DDR5記憶體"
    if re.search(r"漲價|調漲|缺貨|補庫", combined): return "漲價概念"
    if re.search(r"機器人|自動化|Humanoid", combined): return "機器人/自動化"
    if re.search(r"MOSFET|IGBT|SiC|功率半導體", combined): return "功率半導體"
    if re.search(r"MLCC|被動元件|電阻|電感", combined): return "被動元件"
    if re.search(r"金控|銀行|保險|證券", combined): return "金融避風港"
    if re.search(r"生技|醫療|新藥", combined): return "生技醫療"
    if re.search(r"半導體", combined): return "半導體"
    return sector or "其他"

def run_momentum_scan():
    try:
        with open(INPUT_FILE, encoding="utf-8") as f:
            stocks = json.load(f)
    except Exception as e:
        print(f"[Momentum] 讀取輸入檔失敗: {e}")
        return

    # 讀取大戶籌碼快取
    current_smart = {}
    prev_smart = {}
    try:
        whale_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_money_cache.json")
        with open(whale_path, encoding="utf-8") as f:
            whale_data = json.load(f)
            current_smart = whale_data.get("current", {})
            prev_smart = whale_data.get("prev", {})
    except Exception as e:
        print(f"[Momentum] 無法讀取大戶籌碼快取: {e}")

    # 讀取技術指標快取 (MA5/10/20, 布林通道, vol_sma20, rsi, kd, macd, atr)
    tech_map = {}
    try:
        tech_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tech_cache.json")
        with open(tech_path, encoding="utf-8") as f:
            tech_data = json.load(f)
            tech_map = tech_data.get("data", {})
    except Exception as e:
        print(f"[Momentum] 無法讀取技術指標快取: {e}")

    # 計算市場平均成交量
    volumes = [s.get("volume", 0) for s in stocks if s.get("volume", 0) > 0]
    market_avg_vol = sum(volumes) / len(volumes) if volumes else 1000

    # 盤中預估量計算輔助
    import datetime
    now = datetime.datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=13, minute=30, second=0, microsecond=0)
    is_intraday = market_open < now < market_close
    elapsed_minutes = (now - market_open).total_seconds() / 60.0
    if elapsed_minutes < 1: elapsed_minutes = 1

    results = []
    for s in stocks:
        vol = s.get("volume", 0) or 0
        change_pct = parse_change_pct(s.get("change", "0"))
        price = s.get("price", 0) or 0
        desc = s.get("desc", "")
        sector = s.get("sector", "")
        inst_str = s.get("inst", "-")
        yoy = s.get("yoy", 0)
        pe = s.get("pe", 0)
        code = s["symbol"].split(".")[0]
        
        # 獲取集保大戶籌碼資料
        c_data = current_smart.get(code, {})
        p_data = prev_smart.get(code, {})
        whale_pct = c_data.get("whale_pct", 0.0)
        c_holders = c_data.get("total_holders", 0)
        p_holders = p_data.get("total_holders", 0)
        
        # 散戶退場判定：總人數減少且大戶持股比例上升
        retail_exiting = False
        if p_holders > 0 and c_holders > 0:
            if c_holders < p_holders and whale_pct > p_data.get("whale_pct", 0.0):
                retail_exiting = True

        # 技術型態訊號判定 (結合布林與 MA 乖離)
        tech_flags = []
        t_data = tech_map.get(code)
        if t_data:
            sma20 = t_data.get("sma20", 0)
            upper_band = t_data.get("upper_band", 0)
            
            if sma20 > 0:
                bias = (price - sma20) / sma20
                if bias > 0.25:
                    tech_flags.append("乖離過高")
                elif 0 < bias < 0.05:
                    tech_flags.append("突破月線")
                elif bias < -0.05 and change_pct > 2:
                    tech_flags.append("跌深起漲")
                elif -0.03 <= bias <= 0:
                    tech_flags.append("月線上檔")
            
            if upper_band > 0 and price >= upper_band * 0.98:
                tech_flags.append("布林軌道強攻")
                
        # 盤中點火爆量判定
        if is_intraday and vol > 1000:
            est_vol = vol * (270 / elapsed_minutes)
            if est_vol > 5000 and change_pct > 2:
                tech_flags.append("盤中點火")

        # 5大維度量化評分
        theme_s   = score_theme(desc, sector)
        capital_s = score_capital_quant(inst_str, vol, market_avg_vol, whale_pct, retail_exiting, t_data)
        
        # 若乖離率過高，強制扣資金分數，避免高檔追逐
        if "乖離過高" in tech_flags:
            capital_s = max(20, capital_s - 30)

        tech_s    = score_technical_quant(change_pct, price, t_data)
        if "突破月線" in tech_flags or "布林軌道強攻" in tech_flags:
            tech_s = min(100.0, tech_s + 15.0)
            
        macro_s   = score_macro(sector, change_pct)
        trend_s   = score_trend(yoy, pe)
        
        composite = compute_composite_score(theme_s, capital_s, tech_s, macro_s, trend_s)

        # 過濾掉權證與反向ETF，只保留實體股票
        if len(code) > 4 or "反1" in s["name"]:
            continue

        scores_dict = {
            "題材": round(theme_s),
            "資金": round(capital_s),
            "線型": round(tech_s),
            "大環境": round(macro_s),
            "趨勢": round(trend_s),
        }
        theme_tag = get_theme_tag(desc, sector)

        results.append({
            **s,
            "ai_score": composite,
            "signal": get_signal_label(composite),
            "theme_tag": theme_tag,
            "whale_pct": whale_pct,
            "scores": scores_dict,
            "reason": generate_bull_reason(scores_dict, inst_str, theme_tag, yoy, change_pct, whale_pct, retail_exiting, tech_flags, t_data, vol, price),
            "history5d": t_data.get("history5d", []) if t_data else []
        })

    # 按 ai_score 降序排列，取前 50 名
    results.sort(key=lambda x: x["ai_score"], reverse=True)
    top_stocks = results[:50]

    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "market_avg_volume": round(market_avg_vol),
        "total_scanned": len(stocks),
        "top_momentum": top_stocks
    }

    # 原子寫入輸出檔
    tmp_output = OUTPUT_FILE + ".tmp"
    with open(tmp_output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp_output, OUTPUT_FILE)

    print(f"[{time.strftime('%H:%M:%S')}] 🔥 AI 飆股引擎量化計算完成 (掃描 {len(stocks)} 檔，取前 50 名輸出):")
    for i, s in enumerate(top_stocks[:5], 1):
        print(f"  #{i} {s['symbol']} {s['name']:8s} AI評分={s['ai_score']} 題材={s['theme_tag']} 原因={s['reason']}")

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 AI 飆股多因子量化評分引擎啟動...")
    run_momentum_scan()
    while True:
        time.sleep(30)
        try:
            run_momentum_scan()
        except Exception as e:
            print(f"[Momentum] 掃描例外: {e}")

if __name__ == "__main__":
    main()
