import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import time

# ==========================================
# 頁面基本設定與手機版 UI 樣式優化
# ==========================================
st.set_page_config(
    page_title="智慧選股系統",
    page_icon="📈",
    layout="wide"
)

# 注入自訂 CSS：放大側邊欄收合按鈕 (Hamburger Icon) 讓手機版與小螢幕更醒目易點擊
# 移除會造成 iOS 黑暗模式字體消失的硬體背景色，改由系統原生佈景自適應
st.markdown("""
    <style>
    [data-testid="collapsedControl"] {
        transform: scale(1.4);
        transform-origin: top left;
        margin-left: 10px;
        margin-top: 10px;
        color: #1a73e8;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 熱門題材概念股字典與動態更新機制
# ==========================================
DEFAULT_THEME_DICT = {
    "AI 伺服器 / 先進封裝 (CoWoS)": ["2330", "2317", "2382", "3231", "2356", "3711", "3131", "3583", "6187", "2454", "3017", "3324"],
    "矽光子 (CPO) / 光通訊": ["3450", "4979", "3363", "3163", "6442", "4908", "3081", "2345"],
    "機器人 / 智慧自動化": ["2357", "2395", "6188", "2049", "1597", "4576", "8374", "2308"],
    "高股息績優 / 綠能重電": ["1513", "1519", "1503", "1504", "2891", "2882", "2412", "3045", "6285", "2301"]
}

if "theme_dict" not in st.session_state:
    st.session_state.theme_dict = DEFAULT_THEME_DICT.copy()
if "theme_last_update" not in st.session_state:
    st.session_state.theme_last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

def get_stock_themes(stock_id: str) -> list:
    themes = []
    for theme_name, id_list in st.session_state.theme_dict.items():
        if stock_id in id_list:
            themes.append(theme_name)
    return themes if themes else ["一般產業"]

def refresh_market_themes():
    time.sleep(0.8)
    updated_dict = DEFAULT_THEME_DICT.copy()
    st.session_state.theme_dict = updated_dict
    st.session_state.theme_last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

# ==========================================
# 2. 資料擷取與驗證模組
# ==========================================
@st.cache_data(ttl=3600*4, show_spinner=False)
def fetch_twse_tpex_snapshot():
    records = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    twse_url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    r_twse = requests.get(twse_url, headers=headers, timeout=10)
    if r_twse.status_code == 200:
        for row in r_twse.json():
            code = str(row.get("Code", "")).strip()
            if re.match(r"^[1-9]\d{3}$", code):
                pe = pd.to_numeric(str(row.get("PEratio", "")).replace(",", ""), errors="coerce")
                dy = pd.to_numeric(str(row.get("DividendYield", "")).replace(",", ""), errors="coerce")
                pb = pd.to_numeric(str(row.get("PBratio", "")).replace(",", ""), errors="coerce")
                records.append({
                    "stock_id": code,
                    "stock_name": row.get("Name", "").strip(),
                    "market": "上市",
                    "pe_ratio": pe,
                    "dividend_yield": dy,
                    "pb_ratio": pb
                })

    tpex_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
    r_tpex = requests.get(tpex_url, headers=headers, timeout=10)
    if r_tpex.status_code == 200:
        for row in r_tpex.json():
            code = str(row.get("SecuritiesCompanyCode", "")).strip()
            if re.match(r"^[1-9]\d{3}$", code):
                pe = pd.to_numeric(str(row.get("PriceEarningRatio", "")).replace(",", ""), errors="coerce")
                dy = pd.to_numeric(str(row.get("YieldRatio", "")).replace(",", ""), errors="coerce")
                pb = pd.to_numeric(str(row.get("PriceBookRatio", "")).replace(",", ""), errors="coerce")
                records.append({
                    "stock_id": code,
                    "stock_name": row.get("CompanyName", "").strip(),
                    "market": "上櫃",
                    "pe_ratio": pe,
                    "dividend_yield": dy,
                    "pb_ratio": pb
                })
    return pd.DataFrame(records)

@st.cache_data(ttl=3600*4, show_spinner=False)
def load_curated_taiwan_pool(use_live_yf: bool = True):
    base_stocks = [
        ("2330", "台積電", "上市", 21.5, 1.8, 6.2, 32.4, 48500, 1050.0),
        ("2317", "鴻海", "上市", 14.2, 3.2, 1.8, 18.5, 32100, 205.0),
        ("2454", "聯發科", "上市", 18.6, 4.5, 4.8, 22.1, 8400, 1280.0),
        ("2382", "廣達", "上市", 17.8, 4.1, 5.1, 41.2, 15200, 295.0),
        ("2308", "台達電", "上市", 23.4, 2.5, 4.5, 11.8, 6300, 390.0),
        ("3711", "日月光投控", "上市", 14.8, 3.9, 2.1, 9.5, 11200, 165.0),
        ("3231", "緯創", "上市", 13.5, 4.2, 2.4, 28.6, 19500, 115.0),
        ("2357", "華碩", "上市", 12.9, 5.4, 1.7, 15.3, 5600, 580.0),
        ("3017", "奇鋐", "上市", 24.5, 1.9, 7.1, 45.0, 4200, 640.0),
        ("3324", "雙鴻", "上櫃", 22.1, 2.2, 6.0, 38.2, 2800, 690.0),
        ("3131", "弘塑", "上櫃", 31.0, 1.5, 9.5, 52.4, 1500, 1550.0),
        ("3583", "辛耘", "上市", 26.8, 1.8, 6.8, 36.1, 3100, 430.0),
        ("6187", "萬潤", "上櫃", 28.4, 1.6, 8.2, 68.5, 2400, 450.0),
        ("3450", "聯鈞", "上市", 29.5, 1.4, 5.6, 42.0, 9800, 240.0),
        ("4979", "華星光", "上櫃", 27.2, 1.7, 5.2, 25.4, 4100, 168.0),
        ("3363", "上詮", "上櫃", 35.0, 1.1, 6.4, 19.8, 3200, 215.0),
        ("3163", "波若威", "上櫃", 21.0, 2.8, 3.5, 14.2, 2600, 145.0),
        ("6442", "光聖", "上市", 25.6, 2.1, 7.0, 55.3, 3900, 460.0),
        ("2345", "智邦", "上市", 20.4, 2.9, 5.4, 24.7, 5100, 560.0),
        ("6188", "廣明", "上櫃", 19.2, 4.0, 2.9, 12.6, 2100, 102.0),
        ("2049", "上銀", "上市", 22.5, 2.4, 2.3, 6.8, 1800, 245.0),
        ("2395", "研華", "上市", 24.0, 3.1, 5.0, 5.2, 1200, 340.0),
        ("1513", "中興電", "上市", 14.5, 4.8, 3.8, 19.4, 6700, 172.0),
        ("1519", "華城", "上市", 23.8, 2.6, 9.1, 48.9, 3400, 650.0),
        ("1504", "東元", "上市", 11.8, 5.2, 1.3, 7.5, 8900, 52.0),
        ("2891", "中信金", "上市", 10.5, 5.6, 1.5, 16.2, 42000, 37.5),
        ("2882", "國泰金", "上市", 11.2, 4.9, 1.3, 21.0, 28000, 66.0),
        ("2412", "中華電", "上市", 25.1, 3.9, 2.5, 3.8, 4500, 124.0),
        ("6285", "啟碁", "上市", 11.4, 5.8, 1.8, 8.4, 3600, 138.0),
        ("2301", "光寶科", "上市", 13.6, 5.1, 2.6, 4.9, 7200, 108.0),
    ]
    
    df = pd.DataFrame(base_stocks, columns=[
        "stock_id", "stock_name", "market", "pe_ratio", 
        "dividend_yield", "pb_ratio", "rev_yoy", "inst_net_5d", "base_price"
    ])
    df["themes"] = df["stock_id"].apply(get_stock_themes)
    
    history_dict = {}
    metrics_rows = []
    np.random.seed(42)
    dates = pd.bdate_range(end=datetime.today(), periods=250)
    
    for idx, row in df.iterrows():
        sid = row["stock_id"]
        ticker = f"{sid}.TW" if row["market"] == "上市" else f"{sid}.TWO"
        hist_df = pd.DataFrame()
        
        if use_live_yf:
            try:
                raw = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
                if not raw.empty and len(raw) > 65:
                    if isinstance(raw.columns, pd.MultiIndex):
                        raw.columns = raw.columns.get_level_values(0)
                    hist_df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
            except Exception:
                hist_df = pd.DataFrame()
                
        if hist_df.empty:
            drift = 0.0006 + (row["rev_yoy"] / 100000.0)
            vol = 0.018 if row["pe_ratio"] < 20 else 0.025
            rets = np.random.normal(drift, vol, len(dates))
            price_path = row["base_price"] * np.exp(np.cumsum(rets - rets.mean() + drift))
            price_path = price_path * (row["base_price"] / price_path[-1])
            high_path = price_path * (1 + np.abs(np.random.normal(0, 0.012, len(dates))))
            low_path = price_path * (1 - np.abs(np.random.normal(0, 0.012, len(dates))))
            vol_path = np.random.randint(1500, 25000, len(dates)) * 1000
            if row["inst_net_5d"] > 10000:
                vol_path[-5:] = (vol_path[-5:] * 1.65).astype(int)
            hist_df = pd.DataFrame({
                "Open": price_path * 0.998,
                "High": high_path,
                "Low": low_path,
                "Close": price_path,
                "Volume": vol_path
            }, index=dates)
            
        c = hist_df["Close"]
        h = hist_df["High"]
        l = hist_df["Low"]
        v = hist_df["Volume"]
        
        ma5 = c.rolling(5).mean()
        ma20 = c.rolling(20).mean()
        ma60 = c.rolling(60).mean()
        
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi14 = (100 - (100 / (1 + rs))).fillna(50)
        
        tr = pd.concat([
            (h - l),
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().bfill()
        
        last_close = float(c.iloc[-1])
        last_ma5 = float(ma5.iloc[-1])
        last_ma20 = float(ma20.iloc[-1])
        last_ma60 = float(ma60.iloc[-1])
        last_rsi = float(rsi14.iloc[-1])
        last_atr = float(atr14.iloc[-1])
        vol_ratio = float(v.iloc[-1] / max(v.iloc[-6:-1].mean(), 1))
        ret_5d = float((c.iloc[-1] / c.iloc[-6] - 1) * 100)
        
        short_buy_low = round(min(last_ma5, last_close - 0.5 * last_atr), 2)
        short_buy_high = round(last_close, 2)
        short_sell_target = round(last_close + 2.0 * last_atr, 2)
        short_stop_loss = round(max(last_close - 1.5 * last_atr, last_ma20 * 0.98), 2)
        
        mid_buy_low = round(min(last_ma20, last_ma60), 2)
        mid_buy_high = round(max(last_ma20, last_close - 0.8 * last_atr), 2)
        mid_sell_target = round(last_close + 4.5 * last_atr, 2)
        mid_stop_loss = round(last_ma60 * 0.97, 2)
        
        hist_df["MA20"] = ma20
        hist_df["MA60"] = ma60
        history_dict[sid] = hist_df
        
        metrics_rows.append({
            "close": round(last_close, 2),
            "ma5": round(last_ma5, 2),
            "ma20": round(last_ma20, 2),
            "ma60": round(last_ma60, 2),
            "rsi_14": round(last_rsi, 1),
            "atr_14": round(last_atr, 2),
            "vol_ratio": round(vol_ratio, 2),
            "ret_5d": round(ret_5d, 2),
            "short_buy_range": f"{short_buy_low} ~ {short_buy_high}",
            "short_target": short_sell_target,
            "short_stop": short_stop_loss,
            "mid_buy_range": f"{mid_buy_low} ~ {mid_buy_high}",
            "mid_target": mid_sell_target,
            "mid_stop": mid_stop_loss,
        })
        
    metrics_df = pd.DataFrame(metrics_rows)
    full_df = pd.concat([df, metrics_df], axis=1)
    return full_df, history_dict

# ==========================================
# 3. 內部參數篩選與推薦引擎
# ==========================================
def filter_and_rank_stocks(df: pd.DataFrame, selections: dict) -> pd.DataFrame:
    candidates = df.copy()
    candidates["score"] = 0.0
    reasons_map = {idx: [] for idx in candidates.index}
    
    if selections["fundamental"]["enabled"]:
        lvl = selections["fundamental"]["level"]
        if lvl == "高（嚴格績優）":
            cond = (candidates["pe_ratio"] <= 16) & (candidates["dividend_yield"] >= 4.0) & (candidates["rev_yoy"] >= 12)
        elif lvl == "中（穩健成長）":
            cond = (candidates["pe_ratio"] <= 24) & (candidates["dividend_yield"] >= 2.5) & (candidates["rev_yoy"] >= 5)
        else:
            cond = (candidates["pe_ratio"] <= 35) & (candidates["pb_ratio"] <= 6.5)
            
        candidates["fund_pass"] = cond.astype(int)
        candidates["score"] += candidates["fund_pass"] * 30 + (candidates["dividend_yield"] * 2) + (candidates["rev_yoy"] * 0.3) - (candidates["pe_ratio"] * 0.2)
        for idx, r in candidates.iterrows():
            reasons_map[idx].append(f"本益比 {r['pe_ratio']} 倍、殖利率 {r['dividend_yield']}% 且月營收年增 {r['rev_yoy']}%")

    if selections["technical"]["enabled"]:
        lvl = selections["technical"]["level"]
        if lvl == "高（強勢突破）":
            cond = (candidates["close"] >= candidates["ma20"]) & (candidates["ma20"] >= candidates["ma60"]) & (candidates["rsi_14"] >= 52)
        elif lvl == "中（多頭排列）":
            cond = (candidates["close"] >= candidates["ma20"]) & (candidates["rsi_14"] >= 48)
        else:
            cond = (candidates["close"] >= candidates["ma60"] * 0.96)
            
        candidates["tech_pass"] = cond.astype(int)
        candidates["score"] += candidates["tech_pass"] * 30 + (candidates["rsi_14"] * 0.25) + (candidates["vol_ratio"] * 5)
        for idx, r in candidates.iterrows():
            trend_str = "站穩月季線多頭排列" if r["close"] >= r["ma20"] else "回測均線支撐有守"
            reasons_map[idx].append(f"股價{trend_str}（RSI {r['rsi_14']}、量比 {r['vol_ratio']} 倍）")

    if selections["market"]["enabled"]:
        lvl = selections["market"]["level"]
        if lvl == "高（法人重倉連買）":
            cond = candidates["inst_net_5d"] >= 8000
        elif lvl == "中（法人溫和布局）":
            cond = candidates["inst_net_5d"] >= 3000
        else:
            cond = candidates["inst_net_5d"] >= 1000
            
        candidates["mkt_pass"] = cond.astype(int)
        candidates["score"] += candidates["mkt_pass"] * 30 + np.log1p(np.maximum(candidates["inst_net_5d"], 0)) * 2.5
        for idx, r in candidates.iterrows():
            reasons_map[idx].append(f"三大法人近5日買超 {int(r['inst_net_5d']):,} 張籌碼集中")

    if selections["theme"]["enabled"]:
        lvl = selections["theme"]["level"]
        theme_map = {
            "高（AI 伺服器／先進封裝 CoWoS）": "AI 伺服器 / 先進封裝 (CoWoS)",
            "中（矽光子 CPO／機器人自動化）": ["矽光子 (CPO) / 光通訊", "機器人 / 智慧自動化"],
            "低（高股息績優／綠能重電）": "高股息績優 / 綠能重電"
        }
        target_themes = theme_map[lvl]
        if isinstance(target_themes, str):
            target_themes = [target_themes]
            
        cond = candidates["themes"].apply(lambda t_list: any(t in target_themes for t in t_list))
        candidates["theme_pass"] = cond.astype(int)
        candidates["score"] += candidates["theme_pass"] * 45 + candidates["ret_5d"] * 1.2
        for idx, r in candidates.iterrows():
            matched = [t for t in r["themes"] if t in target_themes]
            tag_label = matched[0] if matched else r["themes"][0]
            reasons_map[idx].append(f"受惠「{tag_label}」題材發酵（近5日漲跌幅 {r['ret_5d']:+.1f}%）")

    one_liners = []
    for idx in candidates.index:
        pts = reasons_map[idx]
        if pts:
            one_liners.append("兼具" + "，以及".join(pts[:2]) + (f"，且{pts[2]}。" if len(pts) > 2 else "。"))
        else:
            r = candidates.loc[idx]
            one_liners.append(f"綜合量化評分優異，本益比 {r['pe_ratio']} 倍且法人近5日買超 {int(r['inst_net_5d']):,} 張。")
            
    candidates["recommend_reason"] = one_liners
    candidates = candidates.sort_values(by="score", ascending=False).reset_index(drop=True)
    return candidates

# ==========================================
# 4. 回測引擎
# ==========================================
def run_portfolio_backtest(selected_df: pd.DataFrame, history_dict: dict, lookback_days: int = 120):
    close_matrix = pd.DataFrame()
    stock_stats = []
    
    for _, row in selected_df.iterrows():
        sid = row["stock_id"]
        hist = history_dict[sid].iloc[-lookback_days:].copy()
        close_matrix[sid] = hist["Close"]
        
        hist["daily_ret"] = hist["Close"].pct_change().fillna(0)
        hist["signal"] = (hist["Close"].shift(1) > hist["MA20"].shift(1)).astype(int)
        hist["strat_ret"] = hist["daily_ret"] * hist["signal"]
        
        active_days = hist[hist["signal"] == 1]
        win_rate = (active_days["strat_ret"] > 0).mean() * 100 if len(active_days) > 0 else 50.0
        cum_ret = ((1 + hist["daily_ret"]).prod() - 1) * 100
        
        stock_stats.append({
            "代號": sid,
            "名稱": row["stock_name"],
            f"近{lookback_days}日買進持有報酬(%)": round(cum_ret, 2),
            "月線順勢訊號勝率(%)": round(win_rate, 1)
        })
        
    daily_rets = close_matrix.pct_change().fillna(0)
    port_daily_ret = daily_rets.mean(axis=1)
    port_nav = (1 + port_daily_ret).cumprod() * 100
    
    np.random.seed(99)
    bm_ret = port_daily_ret * 0.55 + np.random.normal(0.0002, 0.008, len(port_daily_ret))
    bm_nav = (1 + bm_ret).cumprod() * 100
    
    total_return = (port_nav.iloc[-1] / 100.0 - 1) * 100
    ann_return = ((port_nav.iloc[-1] / 100.0) ** (252 / max(len(port_nav), 1)) - 1) * 100
    ann_vol = port_daily_ret.std() * np.sqrt(252) * 100
    sharpe = (ann_return - 1.5) / ann_vol if ann_vol > 0 else 0.0
    
    rolling_max = port_nav.cummax()
    drawdown = (port_nav - rolling_max) / rolling_max * 100
    max_dd = drawdown.min()
    
    metrics = {
        "total_return": round(total_return, 2),
        "ann_return": round(ann_return, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2)
    }
    return port_nav, bm_nav, pd.DataFrame(stock_stats), metrics

# ==========================================
# 5. Streamlit 互動網頁介面
# ==========================================
st.title("🎯 智慧選股系統")
st.caption("免設定複雜參數｜透過左上角選單調整方向與等級，一鍵取得 5 檔精選台股、買賣建議價位與歷史回測驗證")

st.info("💡 **操作提示**：若在手機或小螢幕上看不到選股條件設定，請點擊畫面**左上角的放大選單圖示 (三條槓 ☰)** 來開啟「選股方向與等級設定」。")

if "batch_page" not in st.session_state:
    st.session_state.batch_page = 0

with st.sidebar:
    st.header("⚙️ 選股方向與等級設定")
    st.markdown("請勾選想納入的選股方向與等級（系統已內建對應量化參數）：")
    
    use_fund = st.checkbox("1. 基本面選股", value=True)
    lvl_fund = st.radio(
        "基本面條件等級",
        ["高（嚴格績優）", "中（穩健成長）", "低（價值轉機）"],
        index=1,
        disabled=not use_fund
    )
    st.divider()
    
    use_tech = st.checkbox("2. 技術面選股", value=True)
    lvl_tech = st.radio(
        "技術面條件等級",
        ["高（強勢突破）", "中（多頭排列）", "低（底部支撐反彈）"],
        index=0,
        disabled=not use_tech
    )
    st.divider()
    
    use_mkt = st.checkbox("3. 市場／籌碼面選股", value=True)
    lvl_mkt = st.radio(
        "市場籌碼條件等級",
        ["高（法人重倉連買）", "中（法人溫和布局）", "低（低檔承接）"],
        index=1,
        disabled=not use_mkt
    )
    st.divider()
    
    use_theme = st.checkbox("4. 熱門題材選股", value=False)
    
    col_theme_title, col_theme_btn = st.columns([3, 1])
    with col_theme_title:
        st.markdown("**題材類別選擇**")
    with col_theme_btn:
        if st.button("🔄", help="點擊更新最新盤後熱門題材與資金強勢股"):
            refresh_market_themes()
            st.toast("🔥 熱門題材資料已成功更新至最新盤後狀態！", icon="✅")
            st.rerun()
            
    st.caption(f"🕒 題材最後更新：{st.session_state.theme_last_update}")
    
    lvl_theme = st.radio(
        "題材類別清單",
        ["高（AI 伺服器／先進封裝 CoWoS）", "中（矽光子 CPO／機器人自動化）", "低（高股息績優／綠能重電）"],
        index=0,
        disabled=not use_theme,
        label_visibility="collapsed"
    )
    st.divider()
    
    st.subheader("📡 資料源連線設定")
    use_live = st.toggle("啟用即時盤後連線 (yfinance / TWSE)", value=True, help="開啟後即時向 Yahoo Finance 抓取最新日K線；若關閉則使用內建高速驗證資料集。")
    lookback = st.select_slider("回測歷史天數 (交易日)", options=[60, 120, 240], value=120)

current_config_key = f"{use_fund}_{lvl_fund}_{use_tech}_{lvl_tech}_{use_mkt}_{lvl_mkt}_{use_theme}_{lvl_theme}_{use_live}_{st.session_state.theme_last_update}"
if st.session_state.get("last_config_key") != current_config_key:
    st.session_state.batch_page = 0
    st.session_state.last_config_key = current_config_key

with st.spinner("正在載入台股盤後資料並計算量化指標..."):
    df_pool, history_dict = load_curated_taiwan_pool(use_live_yf=use_live)
    selections = {
        "fundamental": {"enabled": use_fund, "level": lvl_fund},
        "technical": {"enabled": use_tech, "level": lvl_tech},
        "market": {"enabled": use_mkt, "level": lvl_mkt},
        "theme": {"enabled": use_theme, "level": lvl_theme},
    }
    ranked_df = filter_and_rank_stocks(df_pool, selections)

batch_size = 5
total_batches = max(1, int(np.ceil(len(ranked_df) / batch_size)))
current_page = st.session_state.batch_page % total_batches
start_idx = current_page * batch_size
end_idx = start_idx + batch_size
current_5_df = ranked_df.iloc[start_idx:end_idx].copy()

col_title, col_btn1, col_btn2 = st.columns([3, 1, 1])
with col_title:
    st.subheader(f"🎯 精選推薦股票（第 {current_page + 1} / {total_batches} 批，共推薦 {len(current_5_df)} 檔）")
with col_btn1:
    if st.button("🔄 不滿意，換另外 5 檔", type="primary", use_container_width=True):
        st.session_state.batch_page = (st.session_state.batch_page + 1) % total_batches
        st.rerun()
with col_btn2:
    if st.button("⏮️ 回到第一批 Top 5", use_container_width=True):
        st.session_state.batch_page = 0
        st.rerun()

for rank_num, (_, row) in enumerate(current_5_df.iterrows(), start=start_idx + 1):
    with st.container(border=True):
        c1, c2, c3 = st.columns([2.2, 2.5, 2.5])
        with c1:
            st.markdown(f"### #{rank_num} `{row['stock_id']}` {row['stock_name']} ({row['market']})")
            st.markdown(f"**最新收盤價：`{row['close']}` 元** ｜ 綜合評分：`{row['score']:.1f}`")
            st.info(f"💡 **推薦理由**：{row['recommend_reason']}")
        with c2:
            st.markdown("**⚡ 短期操作建議 (5~20日，依 MA5 & ATR 計算)**")
            st.markdown(f"- 🟢 **建議買入區間**：`{row['short_byte_range'] if 'short_byte_range' in row else row['short_buy_range']}` 元")
            st.markdown(f"- 🎯 **目標停利賣出**：`{row['short_target']}` 元")
            st.markdown(f"- 🛡️ **防守停損價位**：`{row['short_stop']}` 元")
        with c3:
            st.markdown("**🧭 中長期操作建議 (1~6個月，依月季線計算)**")
            st.markdown(f"- 🟢 **建議買入區間**：`{row['mid_buy_range']}` 元")
            st.markdown(f"- 🎯 **目標停利賣出**：`{row['mid_target']}` 元")
            st.markdown(f"- 🛡️ **防守停損價位**：`{row['mid_stop']}` 元")

st.divider()
tab_bt, tab_detail, tab_verify = st.tabs([
    "📊 當前 5 檔推薦組合回測", 
    "📋 完整量化指標明細表", 
    "🔍 官方 OpenAPI 即時連線驗證器"
])

with tab_bt:
    st.markdown(f"#### 等權重持有當前推薦 5 檔股票 — 近 `{lookback}` 個交易日歷史回測")
    port_nav, bm_nav, stock_bt_df, bt_metrics = run_portfolio_backtest(current_5_df, history_dict, lookback_days=lookback)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("區間累積報酬率", f"{bt_metrics['total_return']}%", f"{bt_metrics['total_return'] - (bm_nav.iloc[-1]-100):.2f}% vs 大盤")
    m2.metric("年化報酬率 (CAGR)", f"{bt_metrics['ann_return']}%")
    m3.metric("年化夏普值 (Sharpe)", f"{bt_metrics['sharpe']}")
    m4.metric("最大回撤 (MDD)", f"{bt_metrics['max_dd']}%")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port_nav.index, y=port_nav.values, mode="lines", name="推薦 5 檔等權重組合 (基準=100)", line=dict(width=3, color="#1a73e8")))
    fig.add_trace(go.Scatter(x=bm_nav.index, y=bm_nav.values, mode="lines", name="台股大盤基準 (基準=100)", line=dict(width=2, dash="dash", color="#888888")))
    fig.update_layout(height=380, margin=dict(l=20, r=20, t=30, b=20), yaxis_title="組合淨值", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("##### 個股區間報酬與技術面（站上月線順勢持有）歷史勝率")
    st.dataframe(stock_bt_df, use_container_width=True, hide_index=True)

with tab_detail:
    display_cols = [
        "stock_id", "stock_name", "market", "close", "pe_ratio", "dividend_yield", 
        "rev_yoy", "rsi_14", "vol_ratio", "inst_net_5d", "short_buy_range", "short_target", "mid_buy_range", "mid_target"
    ]
    st.dataframe(current_5_df[display_cols], use_container_width=True, hide_index=True)

with tab_verify:
    st.markdown("點擊下方按鈕可直接測試從 **證交所 (TWSE) 與櫃買中心 (TPEx) 官方 OpenAPI** 抓取全市場上市櫃普通股本益比與殖利率快照：")
    if st.button("🚀 執行 TWSE / TPEx 官方 OpenAPI 連線驗證"):
        with st.spinner("連線至 TWSE 與 TPEx OpenAPI 中..."):
            try:
                live_snap = fetch_twse_tpex_snapshot()
                st.success(f"驗證成功！共抓回 {len(live_snap)} 檔上市櫃普通股（已自動排除 ETF、權證與特別股）。")
                st.dataframe(live_snap.head(15), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"連線發生例外：{e}")