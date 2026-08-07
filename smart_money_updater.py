import json
import csv
import urllib.request
import os
import time

URL = "https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart_money_cache.json")

def build_smart_money_cache():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🐳 開始抓取集保大戶籌碼(千張以上大戶持股比例)...")
    try:
        req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read().decode('utf-8').splitlines()
        
        reader = csv.reader(content)
        header = next(reader, None)
        
        # 讀取舊資料作為歷史參考
        old_cache = {}
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    old_cache = old_data.get("current", {})
            except Exception:
                pass
        
        whale_map = {}
        total_holders_map = {}
        
        for row in reader:
            if len(row) < 6:
                continue
            
            code = row[1].strip()
            level = row[2].strip()
            
            # 累加總人數
            try:
                holders = int(row[3].strip())
                total_holders_map[code] = total_holders_map.get(code, 0) + holders
            except ValueError:
                pass
                
            # 15 代表 1,000,001 股以上 (千張大戶)
            if level == "15":
                try:
                    pct = float(row[5].strip())
                    whale_map[code] = pct
                except ValueError:
                    pass
        
        # 組合最新資料
        current_data = {}
        for code in set(list(whale_map.keys()) + list(total_holders_map.keys())):
            current_data[code] = {
                "whale_pct": whale_map.get(code, 0.0),
                "total_holders": total_holders_map.get(code, 0)
            }
            
        out = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "current": current_data,
            "prev": old_cache if old_cache else current_data  # 第一次執行時 prev = current
        }
        
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
            
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ 大戶籌碼快取建立完成！共 {len(current_data)} 檔標的")
        
    except Exception as e:
        print(f"⚠️ 抓取集保資料失敗: {e}")

if __name__ == "__main__":
    build_smart_money_cache()
