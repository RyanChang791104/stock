#!/bin/bash
# 每日自動更新台股基本面、大戶籌碼、技術指標，並執行飆股預測校正

LOG_FILE="/home/rychang/taiwan-stock-app/update.log"
APP_DIR="/home/rychang/taiwan-stock-app"

echo "======================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 啟動每日快取資料更新作業" >> "$LOG_FILE"

cd "$APP_DIR" || exit

# 1. 更新 PE 與 YoY 快取 (FinMind + 證交所 API)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 pe_yoy_cache_builder.py..." >> "$LOG_FILE"
/usr/bin/python3 pe_yoy_cache_builder.py >> "$LOG_FILE" 2>&1

# 2. 更新大戶籌碼快取 (TDCC 集保中心)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 smart_money_updater.py..." >> "$LOG_FILE"
/usr/bin/python3 smart_money_updater.py >> "$LOG_FILE" 2>&1

# 3. 更新技術指標 (MA20/布林/RSI/KD/MACD/ATR + 新高偵測)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 tech_indicator_builder.py..." >> "$LOG_FILE"
/usr/bin/python3 tech_indicator_builder.py >> "$LOG_FILE" 2>&1

# 4. 每日飆股預測校正 (比對昨日預測 vs 今日實際漲跌，自動更新評分權重)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 pattern_corrector.py (每日自我校正)..." >> "$LOG_FILE"
/usr/bin/python3 pattern_corrector.py >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 每日更新作業完成！" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# ── 使用說明 ──
# 每日 09:00 前於終端執行以下指令啟動即時警報:
#   cd /home/rychang/taiwan-stock-app && python3 surge_alert.py
#
# 或加入 crontab 自動啟動:
#   0 9 * * 1-5 cd /home/rychang/taiwan-stock-app && python3 surge_alert.py &

