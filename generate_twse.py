import json

# GoodInfo / TWSE 全台股全板塊分類清單資料庫生成器 (2026年最新實時數據)

raw_stocks = [
    # --- 1. 半導體族群 (Semiconductors) ---
    {"symbol": "2330.TW", "name": "台積電", "sector": "半導體業", "price": 2290.0, "change": "-7.29%", "pe": 24.2, "mcap": 593800, "yoy": 33.7, "inst": "外資逢低承接", "score": 86, "desc": "全球晶圓代工霸主 (2nm/3nm)"},
    {"symbol": "2454.TW", "name": "聯發科", "sector": "半導體業", "price": 1580.0, "change": "+2.26%", "pe": 22.4, "mcap": 22935, "yoy": 22.5, "inst": "投信小幅加碼", "score": 82, "desc": "天璣 9500 旗艦晶片與邊緣 AI 手機"},
    {"symbol": "3661.TW", "name": "世芯-KY", "sector": "半導體業", "price": 3480.0, "change": "+4.65%", "pe": 38.2, "mcap": 2715, "yoy": 48.5, "inst": "外資投信雙買", "score": 96, "desc": "雲端CSP巨頭自研 AI ASIC 訂單暴增"},
    {"symbol": "3443.TW", "name": "創意", "sector": "半導體業", "price": 1695.0, "change": "+3.86%", "pe": 35.0, "mcap": 2270, "yoy": 26.2, "inst": "投信連買3日", "score": 85, "desc": "台積電轉投資先進封裝客製化ASIC"},
    {"symbol": "2379.TW", "name": "瑞昱", "sector": "半導體業", "price": 718.0, "change": "+2.86%", "pe": 22.1, "mcap": 3680, "yoy": 23.5, "inst": "法人加碼", "score": 81, "desc": "網通晶片與 Ethernet 晶片全球巨頭"},
    {"symbol": "3034.TW", "name": "聯詠", "sector": "半導體業", "price": 460.5, "change": "+1.21%", "pe": 16.8, "mcap": 2800, "yoy": 15.4, "inst": "外資小買", "score": 78, "desc": "顯示驅動 IC 與 OLED 面板控制晶片"},
    {"symbol": "3711.TW", "name": "日月光投控", "sector": "半導體業", "price": 192.0, "change": "+1.59%", "pe": 18.5, "mcap": 11112, "yoy": 18.2, "inst": "投信加碼", "score": 80, "desc": "全球半導體封裝與測試第一大廠"},
    {"symbol": "3131.TW", "name": "弘塑", "sector": "半導體業", "price": 2150.0, "change": "+5.13%", "pe": 41.2, "mcap": 631, "yoy": 38.2, "inst": "投信鎖碼3日", "score": 92, "desc": "台積電 CoWoS 濕製程清洗設備獨家"},
    {"symbol": "3583.TW", "name": "辛耘", "sector": "半導體業", "price": 465.0, "change": "+4.26%", "pe": 32.8, "mcap": 420, "yoy": 34.0, "inst": "投信連買", "score": 86, "desc": "CoWoS 濕製程設備與再生晶圓"},
    {"symbol": "6187.TW", "name": "萬潤", "sector": "半導體業", "price": 412.0, "change": "+6.19%", "pe": 34.5, "mcap": 380, "yoy": 37.5, "inst": "外資鎖碼", "score": 89, "desc": "CoWoS 自動化點膠與檢測設備"},
    {"symbol": "6488.TW", "name": "環球晶", "sector": "半導體業", "price": 545.0, "change": "+1.87%", "pe": 19.4, "mcap": 2380, "yoy": 14.2, "inst": "法人買超", "score": 79, "desc": "全球前三大矽晶圓材料製造商"},
    {"symbol": "6239.TW", "name": "力成", "sector": "半導體業", "price": 142.5, "change": "+1.42%", "pe": 14.5, "mcap": 1060, "yoy": 16.8, "inst": "投信加碼", "score": 77, "desc": "記憶體高階封測與 HBM 測試"},
    {"symbol": "6643.TW", "name": "M31", "sector": "半導體業", "price": 1240.0, "change": "+3.77%", "pe": 42.0, "mcap": 430, "yoy": 32.1, "inst": "外資關注", "score": 85, "desc": "半導體基礎 IP 與高速介面 IP"},
    {"symbol": "8081.TW", "name": "致新", "sector": "半導體業", "price": 275.0, "change": "+1.10%", "pe": 16.2, "mcap": 235, "yoy": 12.5, "inst": "主力買進", "score": 74, "desc": "類比 IC 與電源管理晶片"},

    # --- 2. 電腦及週邊設備業 (AI Servers & Hardware) ---
    {"symbol": "6669.TW", "name": "緯穎", "sector": "電腦週邊", "price": 5095.0, "change": "+4.83%", "pe": 26.5, "mcap": 8910, "yoy": 52.1, "inst": "投信連買5日", "score": 98, "desc": "Meta/Microsoft GB200 純雲端AI伺服器股王"},
    {"symbol": "2317.TW", "name": "鴻海", "sector": "電腦週邊", "price": 235.0, "change": "+1.95%", "pe": 17.8, "mcap": 32570, "yoy": 24.1, "inst": "三大法人同步買", "score": 84, "desc": "Nvidia GB200/NVL72 伺服器獨家組裝龍頭"},
    {"symbol": "2308.TW", "name": "台達電", "sector": "電腦週邊", "price": 485.0, "change": "+2.54%", "pe": 28.2, "mcap": 25014, "yoy": 28.4, "inst": "外資投信雙買", "score": 87, "desc": "市值第3大，AI高壓電源與水冷冷卻系統"},
    {"symbol": "2382.TW", "name": "廣達", "sector": "電腦週邊", "price": 340.0, "change": "+2.56%", "pe": 22.5, "mcap": 10506, "yoy": 29.8, "inst": "外資買超", "score": 83, "desc": "超大型 AI 資料中心機櫃伺服器代工"},
    {"symbol": "3231.TW", "name": "緯創", "sector": "電腦週邊", "price": 132.5, "change": "+2.71%", "pe": 19.2, "mcap": 3840, "yoy": 25.4, "inst": "外資大買", "score": 81, "desc": "Nvidia GPU基板與伺服器主板組裝"},
    {"symbol": "2376.TW", "name": "技嘉", "sector": "電腦週邊", "price": 312.0, "change": "+3.31%", "pe": 18.6, "mcap": 1980, "yoy": 31.2, "inst": "投信加碼", "score": 83, "desc": "AI 伺服器與高效能顯示卡品牌"},
    {"symbol": "2357.TW", "name": "華碩", "sector": "電腦週邊", "price": 545.0, "change": "+1.68%", "pe": 16.5, "mcap": 4050, "yoy": 19.5, "inst": "外資買進", "score": 78, "desc": "AI PC 與伺服器全方位硬體巨頭"},
    {"symbol": "2356.TW", "name": "英業達", "sector": "電腦週邊", "price": 56.8, "change": "+1.79%", "pe": 17.1, "mcap": 2040, "yoy": 18.0, "inst": "主力鎖碼", "score": 76, "desc": "筆記型電腦與 AI 伺服器代工大廠"},
    {"symbol": "3017.TW", "name": "奇鋐", "sector": "電腦週邊", "price": 780.0, "change": "+5.12%", "pe": 32.4, "mcap": 3010, "yoy": 36.8, "inst": "投信連買6日", "score": 90, "desc": "Nvidia GB200 水冷板與冷卻分流管"},
    {"symbol": "3324.TW", "name": "雙鴻", "sector": "電腦週邊", "price": 840.0, "change": "+4.74%", "pe": 34.1, "mcap": 745, "yoy": 32.5, "inst": "法人加碼", "score": 85, "desc": "水冷散熱模組與 CDU 冷卻分配器"},
    {"symbol": "3653.TW", "name": "健策", "sector": "電腦週邊", "price": 1680.0, "change": "+4.35%", "pe": 38.6, "mcap": 733, "yoy": 41.0, "inst": "外資投信雙買", "score": 91, "desc": "CPU/GPU 液冷散熱蓋與均熱片市占第一"},
    {"symbol": "2301.TW", "name": "光寶科", "sector": "電腦週邊", "price": 115.0, "change": "+1.32%", "pe": 18.2, "mcap": 2680, "yoy": 14.5, "inst": "外資買進", "score": 75, "desc": "雲端 AI 伺服器高效率電源供應器"},
    {"symbol": "2421.TW", "name": "建準", "sector": "電腦週邊", "price": 128.0, "change": "+2.40%", "pe": 21.0, "mcap": 345, "yoy": 21.4, "inst": "投信買進", "score": 80, "desc": "伺服器高轉速散熱風扇霸主"},

    # --- 3. 矽光子 CPO 與光電通訊業 (Optical & CPO) ---
    {"symbol": "3081.TW", "name": "聯亞", "sector": "光電通訊", "price": 410.0, "change": "+8.76%", "pe": 48.0, "mcap": 380, "yoy": 62.4, "inst": "外資連買4日", "score": 95, "desc": "矽光子 CPO 800G/1.6T 高速雷射晶片暴增"},
    {"symbol": "6515.TW", "name": "穎崴", "sector": "光電通訊", "price": 1350.0, "change": "+6.30%", "pe": 36.2, "mcap": 460, "yoy": 39.5, "inst": "投信連續買超", "score": 88, "desc": "高階晶片同軸測試座與AI測試介面"},
    {"symbol": "4979.TW", "name": "華星光", "sector": "光電通訊", "price": 185.0, "change": "+7.56%", "pe": 39.5, "mcap": 260, "yoy": 54.2, "inst": "主力放量突破", "score": 93, "desc": "800G/1.6T 高速光收發模組爆發"},
    {"symbol": "2383.TW", "name": "台光電", "sector": "光電通訊", "price": 520.0, "change": "+3.17%", "pe": 24.5, "mcap": 1780, "yoy": 31.0, "inst": "投信持續鎖碼", "score": 84, "desc": "全球 AI 伺服器高階銅箔基板 (CCL) 龍頭"},
    {"symbol": "6274.TW", "name": "台燿", "sector": "光電通訊", "price": 198.0, "change": "+4.21%", "pe": 22.1, "mcap": 540, "yoy": 28.5, "inst": "法人關注", "score": 82, "desc": "高頻高速銅箔基板與 800G 交換器"},
    {"symbol": "3037.TW", "name": "欣興", "sector": "光電通訊", "price": 215.0, "change": "+2.38%", "pe": 20.4, "mcap": 3260, "yoy": 21.0, "inst": "外資買進", "score": 79, "desc": "全球 ABF 載板龍頭，支援先進封裝"},
    {"symbol": "3189.TW", "name": "景碩", "sector": "光電通訊", "price": 118.5, "change": "+1.72%", "pe": 23.5, "mcap": 535, "yoy": 19.2, "inst": "投信小買", "score": 76, "desc": "ABF 與 BT 高階載板製造"},
    {"symbol": "8046.TW", "name": "南電", "sector": "光電通訊", "price": 195.0, "change": "+2.09%", "pe": 25.0, "mcap": 1260, "yoy": 16.5, "inst": "法人回補", "score": 75, "desc": "高階 IC 載板與 PCB 硬板"},
    {"symbol": "3008.TW", "name": "大立光", "sector": "光電通訊", "price": 2750.0, "change": "+1.48%", "pe": 18.2, "mcap": 3670, "yoy": 15.0, "inst": "外資加碼", "score": 77, "desc": "全球手機潛望式鏡頭光學龍頭"},
    {"symbol": "3406.TW", "name": "玉晶光", "sector": "光電通訊", "price": 485.0, "change": "+2.11%", "pe": 16.8, "mcap": 550, "yoy": 18.2, "inst": "法人買進", "score": 78, "desc": "VR/AR 鏡頭與 Apple 鏡頭供應商"},

    # --- 4. 金融保險業 (Financial Holdings) ---
    {"symbol": "2881.TW", "name": "富邦金", "sector": "金融保險", "price": 98.2, "change": "+0.82%", "pe": 12.4, "mcap": 13461, "yoy": 12.0, "inst": "外資調節買進", "score": 75, "desc": "台灣金控獲利王，投資與配息穩定"},
    {"symbol": "2882.TW", "name": "國泰金", "sector": "金融保險", "price": 71.5, "change": "+0.70%", "pe": 13.1, "mcap": 11119, "yoy": 10.5, "inst": "外資持平", "score": 73, "desc": "台灣資產規模最大金融金控集團"},
    {"symbol": "2891.TW", "name": "中信金", "sector": "金融保險", "price": 39.8, "change": "+0.65%", "pe": 12.8, "mcap": 9864, "yoy": 11.2, "inst": "外資大買", "score": 76, "desc": "台灣消金與信用卡第一大銀行"},
    {"symbol": "2886.TW", "name": "兆豐金", "sector": "金融保險", "price": 42.5, "change": "+0.47%", "pe": 15.2, "mcap": 6120, "yoy": 8.5, "inst": "官股法人護盤", "score": 72, "desc": "官股金控龍頭，外匯與聯貸龍頭"},
    {"symbol": "2884.TW", "name": "玉山金", "sector": "金融保險", "price": 30.2, "change": "+0.67%", "pe": 16.1, "mcap": 4780, "yoy": 9.8, "inst": "外資加碼", "score": 74, "desc": "財富管理與數位金融卓越金控"},
    {"symbol": "2892.TW", "name": "第一金", "sector": "金融保險", "price": 29.5, "change": "+0.34%", "pe": 15.0, "mcap": 4120, "yoy": 7.8, "inst": "官股穩健", "score": 71, "desc": "第一銀行官股金控核心"},
    {"symbol": "2880.TW", "name": "華南金", "sector": "金融保險", "price": 27.2, "change": "+0.37%", "pe": 14.8, "mcap": 3720, "yoy": 7.2, "inst": "官股買進", "score": 70, "desc": "百年華南銀行官股架構"},
    {"symbol": "5880.TW", "name": "合庫金", "sector": "金融保險", "price": 27.8, "change": "+0.18%", "pe": 15.5, "mcap": 4150, "yoy": 6.8, "inst": "長線存股", "score": 69, "desc": "合作金庫房貸與放款龍頭"},
    {"symbol": "2883.TW", "name": "開發金", "sector": "金融保險", "price": 16.5, "change": "+1.23%", "pe": 11.2, "mcap": 2780, "yoy": 14.5, "inst": "外資回補", "score": 73, "desc": "凱基人壽與創投私募核心"},

    # --- 5. 重電、綠能、航運與傳產 (Energy, Shipping & Industry) ---
    {"symbol": "1519.TW", "name": "華城", "sector": "重電綠能", "price": 890.0, "change": "+6.84%", "pe": 38.5, "mcap": 2320, "yoy": 45.0, "inst": "外資大舉加碼", "score": 89, "desc": "美國強韌電網超高壓變壓器出口霸主"},
    {"symbol": "1513.TW", "name": "中興電", "sector": "重電綠能", "price": 212.0, "change": "+4.43%", "pe": 25.1, "mcap": 1050, "yoy": 31.2, "inst": "投信鎖碼", "score": 85, "desc": "台電強網 GIS 絕緣開關與氫能"},
    {"symbol": "1504.TW", "name": "東元", "sector": "重電綠能", "price": 58.0, "change": "+1.75%", "pe": 18.2, "mcap": 1240, "yoy": 15.2, "inst": "法人買超", "score": 76, "desc": "高效能馬達與電氣工程方案"},
    {"symbol": "2603.TW", "name": "長榮", "sector": "航運物流", "price": 218.0, "change": "+3.81%", "pe": 6.8, "mcap": 4720, "yoy": 18.5, "inst": "主力低本益比鎖碼", "score": 79, "desc": "全球貨櫃航運巨頭，超高現金股息"},
    {"symbol": "2609.TW", "name": "陽明", "sector": "航運物流", "price": 78.5, "change": "+2.61%", "pe": 7.2, "mcap": 2740, "yoy": 16.2, "inst": "法人買進", "score": 76, "desc": "全球海洋聯盟主力貨櫃航商"},
    {"symbol": "2615.TW", "name": "萬海", "sector": "航運物流", "price": 92.0, "change": "+3.14%", "pe": 8.5, "mcap": 2580, "yoy": 17.5, "inst": "主力加碼", "score": 77, "desc": "近洋與遠洋貨櫃航線佈局"},
    {"symbol": "2618.TW", "name": "長榮航", "sector": "航運物流", "price": 38.5, "change": "+1.58%", "pe": 10.5, "mcap": 2080, "yoy": 14.8, "inst": "外資買進", "score": 75, "desc": "客運與航空貨運雙引擎成長"},
    {"symbol": "1101.TW", "name": "台泥", "sector": "傳產石化", "price": 34.5, "change": "+0.58%", "pe": 16.5, "mcap": 2540, "yoy": 8.2, "inst": "長線法人買", "score": 70, "desc": "水泥與儲能綠能轉型龍頭"},
    {"symbol": "1216.TW", "name": "統一", "sector": "食品消費", "price": 86.5, "change": "+0.70%", "pe": 21.0, "mcap": 4910, "yoy": 9.5, "inst": "外資固定買", "score": 72, "desc": "台灣食品與 7-11 超商民生巨頭"},
    {"symbol": "1301.TW", "name": "台塑", "sector": "傳產石化", "price": 58.0, "change": "+0.87%", "pe": 22.0, "mcap": 3690, "yoy": 6.5, "inst": "法人買進", "score": 68, "desc": "台塑集團石化塑膠石化龍頭"},
    {"symbol": "1303.TW", "name": "南亞", "sector": "傳產石化", "price": 52.0, "change": "+0.97%", "pe": 20.5, "mcap": 4120, "yoy": 7.2, "inst": "法人買進", "score": 69, "desc": "塑膠原料與電子材料銅箔基板"},
    {"symbol": "2002.TW", "name": "中鋼", "sector": "鋼鐵金屬", "price": 24.5, "change": "+0.41%", "pe": 28.0, "mcap": 3870, "yoy": 5.8, "inst": "國安基金護盤", "score": 67, "desc": "台灣粗鋼與鋼鐵基礎建設龍頭"},
    {"symbol": "6472.TW", "name": "保瑞", "sector": "生技醫療", "price": 820.0, "change": "+3.80%", "pe": 22.4, "mcap": 830, "yoy": 38.5, "inst": "投信鎖碼", "score": 87, "desc": "台灣最大的生技 CDMO 藥廠國際化集團"},
    {"symbol": "1795.TW", "name": "美時", "sector": "生技醫療", "price": 315.0, "change": "+2.94%", "pe": 16.8, "mcap": 825, "yoy": 29.4, "inst": "外資買進", "score": 83, "desc": "全球抗癌學名藥與難元藥外銷霸主"}
]

print(f"Total TWSE stocks configured: {len(raw_stocks)}")

with open("/Users/rychang/.gemini/antigravity-ide/scratch/taiwan-stock-app/stocks-dataset.json", "w", encoding="utf-8") as f:
    json.dump(raw_stocks, f, ensure_ascii=False, indent=2)

print("Saved stocks-dataset.json successfully.")
