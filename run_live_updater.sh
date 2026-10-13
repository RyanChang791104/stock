#!/bin/bash
cd /home/rychang/taiwan-stock-app
pkill -9 -f twse_live_updater.py
sleep 1
exec /home/rychang/.local/bin/python3 -u twse_live_updater.py >> /home/rychang/taiwan-stock-app/updater.log 2>&1
