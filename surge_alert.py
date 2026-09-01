#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股即時飆升偵測系統 - 每秒監控全市場
─────────────────────────────────────────────────────────────────
功能:
  ‧ 早上 09:00 自動開始、13:30 自動結束
  ‧ 每秒讀取最新股價 (stocks-full-8000.json)
  ‧ 偵測任何股票「突然上漲 2%+」→ 立即彩色終端警報
  ‧ 將警報寫入 surge_alerts.json，供 Web UI 即時顯示
  ‧ 防重複: 同一股票同一漲幅區段 (2-4%, 5-7%, 8-9.9%, 10%) 只報一次
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

def save_alert(alert_entry):
    """追加寫入警報 JSON，Web UI 透過 polling 讀取"""
    try:
        try:
            with open(ALERTS_FILE, encoding="utf-8") as f:
                alerts = json.load(f)
        except Exception:
            alerts = []
        alerts.append(alert_entry)
        alerts = alerts[-MAX_ALERTS:]   # 只保留最新 MAX_ALERTS 筆
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts, f, ensure_ascii=False)
    except Exception as e:
        print(f"[Alert] 寫入警報失敗: {e}")

def print_alert(s, change_pct, is_momentum, is_new_high):
    """輸出彩色終端警報"""
    name   = s.get("name", "")
    code   = s.get("symbol", "").split(".")[0]
    price  = s.get("price", 0)
    volume = s.get("volume", 0)
    sector = s.get("sector", "")
    label  = tier_label(change_pct)
    ts     = datetime.datetime.now().strftime("%H:%M:%S")

    # 顏色: 漲停=紅, 強勢=黃, 一般=綠
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
    print("║      台股即時飆升偵測系統  v2.0                      ║")
    print("║  每秒掃描全市場 | 突然上漲 2%+ 立即警報              ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"{RESET}")

    # alerted[code] = 最後警報的漲幅級別 (tier)
    alerted = {}
    last_mtime = 0.0
    scan_count = 0
    alert_count = 0

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 等待開盤 (09:00)... 按 Ctrl+C 結束\n")

    while True:
        now = datetime.datetime.now()
        t   = now.time()

        # ── 開盤前等待 ──
        if t < MARKET_OPEN:
            wait_sec = (datetime.datetime.combine(now.date(), MARKET_OPEN) - now).total_seconds()
            print(f"\r  ⏰ 距開盤還有 {int(wait_sec//60):02d}:{int(wait_sec%60):02d}", end="", flush=True)
            time.sleep(1)
            continue

        # ── 收盤後結束 ──
        if t > MARKET_CLOSE:
            print(f"\n[{now.strftime('%H:%M:%S')}] 📊 收盤，今日共發出 {alert_count} 則警報，系統結束")
            break

        # ── 盤中每秒偵測 ──
        try:
            mtime = os.path.getmtime(STOCKS_FILE)
        except Exception:
            time.sleep(1)
            continue

        scan_count += 1
        if scan_count % 10 == 0:
            print(f"\r  📡 盤中偵測中... {now.strftime('%H:%M:%S')} | 掃描 #{scan_count} | 警報 {alert_count} 則", end="", flush=True)

        # 只在檔案有更新時重新分析 (節省 CPU)
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
            code = s.get("symbol", "").split(".")[0]
            # 只看 4 碼股票 (排除權證/ETF)
            if len(code) != 4:
                continue

            change_pct = parse_change_pct(s.get("change", "0"))

            if change_pct < ALERT_THRESHOLD:
                continue

            current_tier = alert_tier(change_pct)
            last_tier    = alerted.get(code, 0)

            # 防重複: 已報過且同一級別 → 跳過
            if current_tier <= last_tier:
                continue

            # ── 觸發警報 ──
            alerted[code] = current_tier
            alert_count  += 1

            is_momentum = code in momentum_codes
            is_new_high = False
            try:
                # 若 change_pct > yesterday's high (簡單判定)
                is_new_high = change_pct >= 8.0
            except Exception:
                pass

            # 終端警報
            print_alert(s, change_pct, is_momentum, is_new_high)

            # 從 AI 飆股漏斗讀取補充資料
            m = momentum_data.get(code, {})
            scores = m.get("scores", {})

            # 寫入 surge_alerts.json 供 Web UI 顯示 (完整欄位)
            alert_entry = {
                "ts":              now.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol":         s.get("symbol", ""),
                "code":           code,
                "name":           s.get("name", ""),
                "change_pct":     round(change_pct, 2),
                "price":          s.get("price", 0),
                "volume":         s.get("volume", 0),
                "sector":         s.get("sector", ""),
                "label":          tier_label(change_pct),
                "is_momentum":    is_momentum,
                "is_new_high":    is_new_high,
                # AI 飆股漏斗補充
                "ai_score":       m.get("ai_score", 0),
                "breakout_score": m.get("breakout_score", 0),
                "breakout_flags": m.get("breakout_flags", []),
                "signal":         m.get("signal", ""),
                "theme_tag":      m.get("theme_tag", ""),
                "reason":         m.get("reason", ""),
                "inst":           s.get("inst", m.get("inst", "-")),
                "whale_pct":      m.get("whale_pct", 0),
                "score_theme":    scores.get("題材", 0),
                "score_capital":  scores.get("資金", 0),
                "score_tech":     scores.get("線型", 0),
                "score_macro":    scores.get("大環境", 0),
                "score_trend":    scores.get("趨勢", 0),
            }
            save_alert(alert_entry)

        time.sleep(0.5)   # 每 0.5 秒偵測一次 (平衡 CPU 與即時性)

def run_demo():
    """
    DEMO 模式：從今日實際 stocks-full-8000.json 挑選漲幅 >= 2% 的真實股票，
    模擬盤中警報逐一觸發，讓使用者看到真實資料的呈現效果。
    """
    print(f"{BOLD}{CYAN}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   台股即時飆升偵測系統  ── DEMO 模式 (真實資料)          ║")
    print("║   從今日股價資料挑選漲幅 ≥ 2% 股票，模擬盤中警報觸發    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{RESET}\n")

    stocks        = load_stocks()
    momentum_codes = load_momentum_codes()

    if not stocks:
        print(f"{RED}❌ 無法讀取 stocks-full-8000.json{RESET}")
        return

    # 挑選今日實際漲幅 >= 2% 的 4 碼股票，按漲幅排序
    candidates = []
    for s in stocks:
        code = s.get("symbol", "").split(".")[0]
        if len(code) != 4:
            continue
        pct = parse_change_pct(s.get("change", "0"))
        if pct >= 2.0:
            candidates.append((pct, s))

    candidates.sort(key=lambda x: x[0], reverse=True)

    if not candidates:
        print(f"{YELLOW}⚠️  今日無漲幅 >= 2% 的股票（可能是非交易日或資料尚未更新）{RESET}")
        print(f"   改用內建範例資料示範...\n")
        # fallback 範例
        candidates = [
            (9.92, {"symbol":"3013.TW","name":"晟銘電","price":93.5,  "volume":45832,"sector":"電子零組件","change":"+9.92%"}),
            (7.31, {"symbol":"2368.TW","name":"金像電", "price":1285.0,"volume":12043,"sector":"光電",       "change":"+7.31%"}),
            (5.43, {"symbol":"3661.TW","name":"世芯-KY","price":1680.0,"volume":8921, "sector":"半導體",     "change":"+5.43%"}),
            (3.21, {"symbol":"6669.TW","name":"緯穎",   "price":7850.0,"volume":6230, "sector":"電腦週邊",   "change":"+3.21%"}),
            (2.45, {"symbol":"4908.TW","name":"前鼎",   "price":66.5,  "volume":31205,"sector":"電子零組件","change":"+2.45%"}),
        ]

    top = candidates[:15]  # 最多顯示 15 筆
    print(f"{BOLD}📋 今日偵測到 {len(candidates)} 檔漲幅 ≥ 2% 股票，示範前 {len(top)} 檔觸發流程：{RESET}\n")
    time.sleep(0.8)

    demo_alerts = []
    for i, (pct, s) in enumerate(top):
        code        = s.get("symbol","").split(".")[0]
        is_momentum = code in momentum_codes
        is_new_high = pct >= 7.0

        # 模擬時間戳（從 09:01 開始每筆間隔 2~5 分鐘）
        fake_min  = 1 + i * 3
        fake_ts   = f"09:{fake_min:02d}:{(i*7)%60:02d}"
        fake_dt   = f"2026-09-01 {fake_ts}"

        # 終端輸出
        print_alert(s, pct, is_momentum, is_new_high)
        time.sleep(0.7)

        # 同步寫入 surge_alerts.json 讓 Web UI 也能看到
        entry = {
            "ts":          fake_dt,
            "symbol":      s.get("symbol",""),
            "code":        code,
            "name":        s.get("name",""),
            "change_pct":  round(pct, 2),
            "price":       s.get("price", 0),
            "volume":      s.get("volume", 0),
            "sector":      s.get("sector",""),
            "label":       tier_label(pct),
            "is_momentum": is_momentum,
            "is_new_high": is_new_high,
        }
        demo_alerts.append(entry)
        save_alert(entry)

    # 統計摘要
    limit_up = sum(1 for p,_ in top if p >= 9.5)
    ai_hits  = sum(1 for _,s in top if s.get("symbol","").split(".")[0] in momentum_codes)
    print(f"\n{BOLD}{'─'*62}{RESET}")
    print(f"{BOLD}📊 DEMO 摘要{RESET}")
    print(f"   總警報數 : {len(top)} 則")
    print(f"   漲停板   : {limit_up} 檔 🚨")
    print(f"   AI飆股命中: {ai_hits} 檔 🤖")
    print(f"   最強漲幅 : {top[0][0]:+.2f}% ({top[0][1].get('name','')})")
    print(f"{BOLD}{'─'*62}{RESET}")
    print(f"\n{GREEN}✅ surge_alerts.json 已更新 — 開啟瀏覽器 http://172.22.31.23:8090/ 查看右下角警報面板{RESET}\n")


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

