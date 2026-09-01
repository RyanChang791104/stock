#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股飆股預測每日自我校正系統
─────────────────────────────────────────────────────────────────
每日流程:
  1. 盤後執行: 讀取前日快照 → 比對今日實際漲跌 → 計算各因子相關係數
  2. 用指數加權平均 (EWA) 更新 weight_override.json
  3. 儲存今日預測快照供明日使用
  4. 將校正結果寫入 correction_log.json (保留 90 天)

ai_momentum_engine.py 每次掃描時讀取 weight_override.json，
實現「每天根據市場實際結果自動修正評分邏輯」。
"""

import json
import os
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_FILE  = os.path.join(BASE_DIR, "prediction_snapshot.json")
WEIGHT_FILE    = os.path.join(BASE_DIR, "weight_override.json")
CORRECTION_LOG = os.path.join(BASE_DIR, "correction_log.json")
STOCKS_FILE    = os.path.join(BASE_DIR, "stocks-full-8000.json")
MOMENTUM_FILE  = os.path.join(BASE_DIR, "momentum-stocks.json")

# 預設權重 (各因子初始值)
DEFAULT_WEIGHTS = {
    "theme":    0.20,
    "capital":  0.25,
    "tech":     0.25,
    "macro":    0.15,
    "trend":    0.15,
}

# 學習率: 新觀察資料影響舊權重的比例 (0.3 = 較積極學習)
ALPHA = 0.30

# 各因子權重的上下限，避免過度集中
WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.40

# ── 因子分數鍵值對照 ──
FACTOR_KEY_MAP = {
    "theme":   "題材",
    "capital": "資金",
    "tech":    "線型",
    "macro":   "大環境",
    "trend":   "趨勢",
}

def pearson_correlation(xs, ys):
    """計算 Pearson 相關係數"""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / n
    var_x = sum((x - mean_x) ** 2 for x in xs) / n
    var_y = sum((y - mean_y) ** 2 for y in ys) / n
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / ((var_x ** 0.5) * (var_y ** 0.5))

def load_weights():
    """讀取現有動態權重，若不存在則回傳預設值"""
    try:
        with open(WEIGHT_FILE, encoding="utf-8") as f:
            w = json.load(f)
        # 確保所有鍵都存在
        for k, v in DEFAULT_WEIGHTS.items():
            w.setdefault(k, v)
        return w
    except Exception:
        return DEFAULT_WEIGHTS.copy()

def save_snapshot():
    """儲存今日預測快照 (含每個股票的各因子分數)"""
    try:
        with open(MOMENTUM_FILE, encoding="utf-8") as f:
            data = json.load(f)
        snapshot = {
            "date": datetime.date.today().isoformat(),
            "stocks": [
                {
                    "symbol":        s["symbol"],
                    "name":          s.get("name", ""),
                    "price":         s.get("price", 0),
                    "ai_score":      s.get("ai_score", 0),
                    "scores":        s.get("scores", {}),
                    "breakout_score": s.get("breakout_score", 50),
                    "theme_tag":     s.get("theme_tag", ""),
                    "change":        s.get("change", "0"),
                }
                for s in data.get("top_momentum", [])
            ]
        }
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        print(f"[Corrector] 📸 快照儲存完成: {len(snapshot['stocks'])} 檔 ({snapshot['date']})")
        return True
    except Exception as e:
        print(f"[Corrector] ❌ 快照儲存失敗: {e}")
        return False

def evaluate_and_correct():
    """
    主校正流程:
    1. 讀取前日快照
    2. 查詢今日實際股價
    3. 計算各因子與實際漲跌幅的 Pearson 相關係數
    4. 用 EWA 更新權重
    5. 儲存今日快照
    """
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔧 啟動每日飆股預測校正系統...")

    # ── 讀取前日快照 ──
    if not os.path.exists(SNAPSHOT_FILE):
        print("[Corrector] 無前日快照，初次執行 → 直接儲存今日快照")
        save_snapshot()
        return

    try:
        with open(SNAPSHOT_FILE, encoding="utf-8") as f:
            snapshot = json.load(f)
    except Exception as e:
        print(f"[Corrector] ❌ 讀取快照失敗: {e}")
        save_snapshot()
        return

    prev_date = snapshot.get("date", "")
    today = datetime.date.today().isoformat()

    if prev_date == today:
        print(f"[Corrector] ⚠️  快照日期與今日相同 ({today})，盤中無需校正，已跳過")
        return

    # ── 讀取今日股票資料 ──
    try:
        with open(STOCKS_FILE, encoding="utf-8") as f:
            stocks = json.load(f)
    except Exception as e:
        print(f"[Corrector] ❌ 讀取 stocks JSON 失敗: {e}")
        return

    price_map = {s["symbol"]: s for s in stocks}
    current_weights = load_weights()

    # ── 逐一評估預測結果 ──
    evaluated = []
    factor_data = {k: {"xs": [], "ys": []} for k in DEFAULT_WEIGHTS}

    for pred in snapshot.get("stocks", []):
        sym = pred["symbol"]
        prev_price = pred.get("price", 0) or 0
        current_stock = price_map.get(sym, {})
        curr_price = current_stock.get("price", 0) or 0

        if prev_price <= 0 or curr_price <= 0:
            continue

        actual_return = (curr_price - prev_price) / prev_price * 100
        scores = pred.get("scores", {})

        # 記錄各因子分數 vs 實際漲跌
        for factor, key in FACTOR_KEY_MAP.items():
            fscore = scores.get(key, 50)
            factor_data[factor]["xs"].append(fscore)
            factor_data[factor]["ys"].append(actual_return)

        # 記錄評估結果
        evaluated.append({
            "symbol": sym,
            "name": pred.get("name", ""),
            "prev_price": prev_price,
            "curr_price": curr_price,
            "actual_return": round(actual_return, 2),
            "ai_score": pred.get("ai_score", 0),
            "theme_tag": pred.get("theme_tag", ""),
        })

    if not evaluated:
        print("[Corrector] ⚠️  無有效評估資料 (可能休市或股價尚未更新)")
        save_snapshot()
        return

    # ── 計算各因子相關係數 ──
    factor_correlations = {}
    for factor, d in factor_data.items():
        if len(d["xs"]) >= 5:
            corr = pearson_correlation(d["xs"], d["ys"])
        else:
            corr = 0.0
        # 只保留正相關; 相關不佳的因子不增加其權重
        factor_correlations[factor] = max(0.0, corr)

    # ── EWA 更新權重 ──
    total_corr = sum(factor_correlations.values()) or 1.0
    new_weights = {}
    for factor in DEFAULT_WEIGHTS:
        target_weight = factor_correlations[factor] / total_corr
        old_weight = current_weights.get(factor, DEFAULT_WEIGHTS[factor])
        # Exponential Weighted Average
        updated = ALPHA * target_weight + (1.0 - ALPHA) * old_weight
        # 限制上下限
        new_weights[factor] = max(WEIGHT_MIN, min(WEIGHT_MAX, updated))

    # 正規化到總和 = 1.0
    total = sum(new_weights.values()) or 1.0
    new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    # 儲存新權重
    try:
        with open(WEIGHT_FILE, "w", encoding="utf-8") as f:
            json.dump(new_weights, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Corrector] ❌ 儲存權重失敗: {e}")

    # ── 統計命中率 ──
    hits   = [e for e in evaluated if e["actual_return"] > 0]
    misses = [e for e in evaluated if e["actual_return"] <= 0]
    hit_rate = len(hits) / len(evaluated) * 100

    avg_return = sum(e["actual_return"] for e in evaluated) / len(evaluated)
    top_hits   = sorted(hits,   key=lambda x: x["actual_return"], reverse=True)[:5]
    top_misses = sorted(misses, key=lambda x: x["actual_return"])[:5]

    # ── 寫入校正日誌 ──
    log_entry = {
        "date":            today,
        "prev_date":       prev_date,
        "total_evaluated": len(evaluated),
        "hit_rate_pct":    round(hit_rate, 1),
        "avg_return_pct":  round(avg_return, 2),
        "hits":            len(hits),
        "misses":          len(misses),
        "top_hits":        top_hits,
        "top_misses":      top_misses,
        "factor_correlation": {k: round(v, 4) for k, v in factor_correlations.items()},
        "old_weights":     current_weights,
        "new_weights":     new_weights,
    }

    try:
        try:
            with open(CORRECTION_LOG, encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
        log.append(log_entry)
        log = log[-90:]  # 保留最近 90 天
        with open(CORRECTION_LOG, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Corrector] ❌ 日誌寫入失敗: {e}")

    # ── 輸出摘要 ──
    print(f"[Corrector] ✅ 校正完成 | {prev_date} → {today}")
    print(f"[Corrector]    評估: {len(evaluated)} 檔 | 命中率: {hit_rate:.1f}% | 平均報酬: {avg_return:+.2f}%")
    print(f"[Corrector]    各因子相關係數: { {k: round(v,3) for k,v in factor_correlations.items()} }")
    print(f"[Corrector]    舊權重: {current_weights}")
    print(f"[Corrector]    新權重: {new_weights}")
    if top_hits:
        print(f"[Corrector]    ✅ 最強命中: " + " | ".join(f"{e['name']}({e['actual_return']:+.1f}%)" for e in top_hits))
    if top_misses:
        print(f"[Corrector]    ❌ 最大失誤: " + " | ".join(f"{e['name']}({e['actual_return']:+.1f}%)" for e in top_misses))

    # ── 儲存今日快照供明日使用 ──
    save_snapshot()


if __name__ == "__main__":
    evaluate_and_correct()
