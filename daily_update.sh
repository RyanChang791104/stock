#!/bin/bash
# 每日自動更新台股基本面與大戶籌碼快取

LOG_FILE="/home/rychang/taiwan-stock-app/update.log"
APP_DIR="/home/rychang/taiwan-stock-app"

echo "======================================" >> "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 啟動每日快取資料更新作業" >> "$LOG_FILE"

# 切換到應用程式目錄
cd "$APP_DIR" || exit

# 1. 更新 PE 與 YoY 快取 (FinMind + 證交所 API)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 pe_yoy_cache_builder.py..." >> "$LOG_FILE"
/usr/bin/python3 pe_yoy_cache_builder.py >> "$LOG_FILE" 2>&1

# 2. 更新大戶籌碼快取 (TDCC 集保中心)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 smart_money_updater.py..." >> "$LOG_FILE"
/usr/bin/python3 smart_money_updater.py >> "$LOG_FILE" 2>&1

# 3. 更新技術指標 (MA20 / 布林通道)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 執行 tech_indicator_builder.py..." >> "$LOG_FILE"
/usr/bin/python3 tech_indicator_builder.py >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 每日更新作業完成！" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"
