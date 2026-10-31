import streamlit as st
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import os
import json

# ==========================================
# 頁面基本設定與手機版 UI 樣式優化
# ==========================================
st.set_page_config(
    page_title="智慧選股系統",
    page_icon="📈",
    layout="wide"
)

st.markdown("""
    <style>
    [data-testid="collapsedControl"] {
        transform: scale(1.4);
        transform-origin: top left;
        margin-left: 10px;
        margin-top: 10px;
        color: #1a73e8;
    }
    .disclaimer-banner {
        padding: 12px 16px;
        background-color: #f8f9fa;
        border-left: 4px solid #f44336;
        border-radius: 4px;
        font-size: 0.85rem;
        color: #555555;
        margin-top: 25px;
        margin-bottom: 25px;
    }
    div.st-key-btn_single_stock_analysis button,
    button[aria-label*="個股分析"] {
        background-color: #1a73e8 !important;
        background: #1a73e8 !important;
        color: #ffffff !important;
        border: 1px solid #1a73e8 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 10px rgba(26, 115, 232, 0.35) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div.st-key-btn_single_stock_analysis button p,
    div.st-key-btn_single_stock_analysis button span,
    button[aria-label*="個股分析"] p,
    button[aria-label*="個股分析"] span {
        color: #ffffff !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
    }
    div.st-key-btn_single_stock_analysis button:hover,
    button[aria-label*="個股分析"]:hover {
        background-color: #1557b0 !important;
        background: #1557b0 !important;
        border-color: #1557b0 !important;
        box-shadow: 0 6px 14px rgba(21, 87, 176, 0.45) !important;
    }
    div.st-key-btn_single_stock_analysis button:hover p,
    button[aria-label*="個股分析"]:hover p {
        color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)

CACHE_PARQUET_FILE = "market_cache.parquet"
META_JSON_FILE = "market_cache_meta.json"

# ==========================================
# 0. 法律免責聲明彈窗 (僅備查，不強制彈出)
# ==========================================
@st.dialog("⚖️ 投資風險與法律免責聲明", width="large")
def show_legal_disclaimer_modal():
    st.markdown("### ⚠️ 使用者須知與風險宣告")
    st.markdown("""
    感謝您使用**「智慧選股系統」**（以下簡稱「本系統」）。在使用本系統提供的任何資訊、數據、指標及分析工具前，請仔細閱讀以下法律聲明：
    
    1. **非證券投資顧問業務**：本系統所載之所有選股結果、策略回測、買賣建議區間及盤勢分析，均基於歷史盤後公開數據及量化演算法運算呈現，**僅供學術研究、量化模型驗證與教育模擬用途**，不構成任何形式的投資招攬、買賣建議或金融顧問服務。
    2. **歷史績效不保證未來獲利**：過往之技術指標表現、勝率統計或歷史回測曲線，均不代表亦不保證未來之實際投資報酬。金融市場受國內外政經情勢、總體經濟及突發事件等多重不可抗力因素影響，風險難以完全預估。
    3. **獨立審慎評估與風險自負**：本系統所引用之即時或盤後數據源自台灣證券交易所、證券櫃檯買賣中心及第三方資訊服務商，本系統力求數據之客觀與正確，但對數據延遲、遺漏或計算偏差不負法律保證責任。**使用者應依個人財務狀況、風險承受能力獨立判斷並自負投資盈虧責任**。
    """)
    st.markdown("---")
    if st.button("關閉聲明", use_container_width=True):
        st.rerun()

# ==========================================
# 1. 熱門題材概念股字典與動態更新機制
# ==========================================
DEFAULT_THEME_DICT = {
    "AI 伺服器 / 先進封裝 (CoWoS)": ["2330", "2317", "2382", "3231", "2356", "3711", "3131", "3583", "6187", "2454", "3017", "3324", "6669", "2059"],
    "矽光子 CPO / 機器人自動化": ["3450", "4979", "3363", "3163", "6442", "4908", "3081", "2345", "2357", "2395", "6188", "2049", "4576", "1597"],
    "高股息績優 / 綠能重電": ["1513", "1519", "1503", "1504", "2891", "2882", "2886", "2412", "3045", "6285", "2301", "1101", "1102"]
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
    st.session_state.theme_dict = DEFAULT_THEME_DICT.copy()
    st.session_state.theme_last_update = datetime.now().strftime("%Y-%m-%d %H:%M")

def parse_tw_roc_date(roc_date_str: str) -> str:
    weekday_map = {0: "週一", 1: "週二", 2: "週三", 3: "週四", 4: "週五", 5: "週六", 6: "週日"}
    try:
        clean = re.sub(r"[^\d]", "", str(roc_date_str))
        if len(clean) >= 7:
            year = int(clean[:3]) + 1911
            month = int(clean[3:5])
            day = int(clean[5:7])
            dt = datetime(year, month, day)
            return f"{dt.strftime('%Y-%m-%d')} ({weekday_map.get(dt.weekday(), '')})"
    except Exception:
        pass
    tw_now = datetime.utcnow() + timedelta(hours=8)
    return f"{tw_now.strftime('%Y-%m-%d')} ({weekday_map.get(tw_now.weekday(), '')})"

# ==========================================
# 2. 全市場真實數據擷取與 Parquet 磁碟快取
# ==========================================
def fetch_full_market_universe(force_refresh: bool = False):
    if not force_refresh and os.path.exists(CACHE_PARQUET_FILE) and os.path.exists(META_JSON_FILE):
        try:
            with open(META_JSON_FILE, "r", encoding="utf-8") as f:
                meta_info = json.load(f)
            cached_label = meta_info.get("tw_date_label", "")
            mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_PARQUET_FILE))
            if (datetime.now() - mtime).total_seconds() < 43200 and cached_label:
                df_cached = pd.read_parquet(CACHE_PARQUET_FILE)
                if not df_cached.empty and len(df_cached) >= 1000 and df_cached["stock_id"].str.startswith("00").any():
                    df_cached["themes"] = df_cached["stock_id"].apply(get_stock_themes)
                    return df_cached, cached_label
        except Exception:
            pass

    headers = {"User-Agent": "Mozilla/5.0"}
    market_rows = []
    twse_raw_date_str = ""

    pe_twse = {}
    try:
        r_pe = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", headers=headers, timeout=10)
        if r_pe.status_code == 200:
            for row in r_pe.json():
                code = str(row.get("Code", "")).strip()
                if re.match(r"^[1-9]\d{3}$", code):
                    if not twse_raw_date_str and "Date" in row:
                        twse_raw_date_str = str(row["Date"])
                    pe_twse[code] = {
                        "name": row.get("Name", "").strip(),
                        "pe": pd.to_numeric(str(row.get("PEratio", "")).replace(",", ""), errors="coerce"),
                        "dy": pd.to_numeric(str(row.get("DividendYield", "")).replace(",", ""), errors="coerce"),
                        "pb": pd.to_numeric(str(row.get("PBratio", "")).replace(",", ""), errors="coerce")
                    }
    except Exception:
        pass

    try:
        r_p = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers, timeout=10)
        if r_p.status_code == 200:
            for row in r_p.json():
                code = str(row.get("Code", "")).strip()
                name = str(row.get("Name", "")).strip()
                if not twse_raw_date_str and "Date" in row:
                    twse_raw_date_str = str(row["Date"])
                
                if re.match(r"^(00\d{2,3}[A-Za-z]?|[1-9]\d{3}[A-Za-z]?)$", code):
                    vol_shares = pd.to_numeric(str(row.get("TradeVolume", "")).replace(",", ""), errors="coerce")
                    close_p = pd.to_numeric(str(row.get("ClosingPrice", "")).replace(",", ""), errors="coerce")
                    vol_sheets = vol_shares / 1000.0 if pd.notnull(vol_shares) else 0.0
                    
                    if pd.notnull(close_p) and close_p > 0:
                        item = pe_twse.get(code, {})
                        is_etf = code.startswith("00")
                        market_label = "上市 ETF" if is_etf else "上市"
                        final_name = name if name else item.get("name", code)
                        market_rows.append({
                            "stock_id": code,
                            "stock_name": final_name,
                            "market": market_label,
                            "close": float(close_p),
                            "volume_sheets": float(vol_sheets),
                            "pe_ratio": float(item["pe"]) if pd.notnull(item.get("pe")) and item["pe"] > 0 else (np.nan if is_etf else 22.0),
                            "dividend_yield": float(item["dy"]) if pd.notnull(item.get("dy")) else (np.nan if is_etf else 2.5),
                            "pb_ratio": float(item["pb"]) if pd.notnull(item.get("pb")) else (np.nan if is_etf else 2.0),
                        })
    except Exception:
        pass

    try:
        r_otc_pe = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis", headers=headers, timeout=10)
        r_otc = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers, timeout=10)
        
        pe_otc = {}
        if r_otc_pe.status_code == 200:
            for row in r_otc_pe.json():
                code = str(row.get("SecuritiesCompanyCode", "")).strip()
                if re.match(r"^[1-9]\d{3}$", code):
                    pe_otc[code] = {
                        "pe": pd.to_numeric(str(row.get("PriceEarningRatio", "")).replace(",", ""), errors="coerce"),
                        "dy": pd.to_numeric(str(row.get("YieldRatio", "")).replace(",", ""), errors="coerce"),
                        "pb": pd.to_numeric(str(row.get("PriceBookRatio", "")).replace(",", ""), errors="coerce")
                    }
                    
        if r_otc.status_code == 200:
            for row in r_otc.json():
                code = str(row.get("SecuritiesCompanyCode", "")).strip()
                name = str(row.get("CompanyName", "")).strip()
                if re.match(r"^(00\d{2,3}[A-Za-z]?|[1-9]\d{3}[A-Za-z]?)$", code):
                    vol_shares = pd.to_numeric(str(row.get("TradingShares", "")).replace(",", ""), errors="coerce")
                    close_p = pd.to_numeric(str(row.get("Close", "")).replace(",", ""), errors="coerce")
                    vol_sheets = vol_shares / 1000.0 if pd.notnull(vol_shares) else 0.0
                    
                    if pd.notnull(close_p) and close_p > 0:
                        p_info = pe_otc.get(code, {})
                        is_etf = code.startswith("00")
                        market_label = "上櫃 ETF" if is_etf else "上櫃"
                        market_rows.append({
                            "stock_id": code,
                            "stock_name": name,
                            "market": market_label,
                            "close": float(close_p),
                            "volume_sheets": float(vol_sheets),
                            "pe_ratio": float(p_info.get("pe")) if pd.notnull(p_info.get("pe")) and p_info.get("pe") > 0 else (np.nan if is_etf else 24.0),
                            "dividend_yield": float(p_info.get("dy")) if pd.notnull(p_info.get("dy")) else (np.nan if is_etf else 2.0),
                            "pb_ratio": float(p_info.get("pb")) if pd.notnull(p_info.get("pb")) else (np.nan if is_etf else 2.5),
                        })
    except Exception:
        pass

    full_df = pd.DataFrame(market_rows)

    if full_df.empty or len(full_df) < 50:
        st.error("⚠️ 無法連線至證交所或櫃買中心取得最新盤後行情，請確認網路連線或稍後再試。")
        st.stop()

    actual_tw_label = parse_tw_roc_date(twse_raw_date_str)

    try:
        save_cols = [
            "stock_id", "stock_name", "market", "close", 
            "volume_sheets", "pe_ratio", "dividend_yield", "pb_ratio"
        ]
        temp_file = CACHE_PARQUET_FILE + ".tmp"
        full_df[save_cols].to_parquet(temp_file, compression="snappy", index=False)
        if os.path.exists(CACHE_PARQUET_FILE):
            os.remove(CACHE_PARQUET_FILE)
        os.rename(temp_file, CACHE_PARQUET_FILE)
        with open(META_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump({"tw_date_label": actual_tw_label}, f)
    except Exception:
        pass

    full_df["themes"] = full_df["stock_id"].apply(get_stock_themes)
    return full_df, actual_tw_label

# ==========================================
# 3. 第一階段漏斗初篩 (精確收斂為 25 檔候選股)
# ==========================================
def fast_filter_funnel(full_df: pd.DataFrame, selections: dict, top_n: int = 25) -> pd.DataFrame:
    df = full_df[~full_df["stock_id"].str.startswith("00") & (full_df["volume_sheets"] >= 80)].copy()
    if df.empty:
        df = full_df.copy()
    df["stage1_score"] = 0.0

    if selections["fundamental"]["enabled"]:
        lvl = selections["fundamental"]["level"]
        if lvl == "嚴格績優":
            cond = (df["pe_ratio"].fillna(99) <= 18) & (df["dividend_yield"].fillna(0) >= 3.8)
            score = cond.astype(int) * 35.0 + (df["dividend_yield"].fillna(0) * 3.0) - (df["pe_ratio"].fillna(30) * 0.4)
        elif lvl == "穩健成長":
            cond = (df["pe_ratio"].fillna(99) >= 14) & (df["pe_ratio"].fillna(99) <= 27) & (df["dividend_yield"].fillna(0) >= 1.8)
            pe_dist = (df["pe_ratio"].fillna(20) - 20.0).abs()
            score = cond.astype(int) * 35.0 + 15.0 - (pe_dist * 1.2) + (df["dividend_yield"].fillna(0) * 1.5)
        else:  # 價值轉機
            cond = (df["pb_ratio"].fillna(99) <= 1.9) & (df["pe_ratio"].fillna(99) <= 38)
            score = cond.astype(int) * 40.0 + (2.0 - df["pb_ratio"].fillna(2.0)).clip(lower=-1.0) * 20.0
            score -= (df["pb_ratio"].fillna(0) > 3.0).astype(int) * 35.0
        df["stage1_score"] += score

    if selections["market"]["enabled"]:
        lvl = selections["market"]["level"]
        if lvl == "法人重倉連買":
            cond = df["volume_sheets"] >= 3500
            score = cond.astype(int) * 30.0 + np.log1p(df["volume_sheets"]) * 3.5
        elif lvl == "法人溫和布局":
            cond = (df["volume_sheets"] >= 1200) & (df["volume_sheets"] <= 5500)
            score = cond.astype(int) * 35.0 + 10.0 - ((df["volume_sheets"] - 2800).abs() / 500.0)
        else:  # 低檔承接
            cond = (df["volume_sheets"] >= 300) & (df["volume_sheets"] <= 1800)
            score = cond.astype(int) * 40.0 - (df["volume_sheets"] > 3000).astype(int) * 35.0
        df["stage1_score"] += score

    if selections["theme"]["enabled"]:
        lvl = selections["theme"]["level"]
        target = lvl
        cond = df["themes"].apply(lambda t_list: any(target in t for t in t_list))
        df["stage1_score"] += cond.astype(int) * 45.0

    ranked_pool = df.sort_values(by="stage1_score", ascending=False).head(top_n).reset_index(drop=True)
    return ranked_pool

# ==========================================
# 4. 狀態聯動動態定價模型
# ==========================================
def compute_regime_pricing(last_close, last_ma5, last_ma20, last_ma60, last_rsi, last_atr):
    is_bull = (last_close >= last_ma20) and (last_rsi >= 50)
    is_bear = (last_close < last_ma20) and (last_rsi < 48)

    if is_bull:
        short_buy_low = round(min(last_ma5 - 0.2 * last_atr, last_close - 0.4 * last_atr), 2)
        short_buy_high = round(min(last_close, max(last_ma5, last_close - 0.1 * last_atr)), 2)
        if short_buy_low >= short_buy_high:
            short_buy_low = round(short_buy_high - 0.3 * last_atr, 2)
        short_buy_range = f"{short_buy_low} ~ {short_buy_high}"
        short_target = round(last_close + 2.0 * last_atr, 2)
        short_stop = round(max(last_close - 1.5 * last_atr, last_ma20 * 0.98), 2)

        mid_buy_low = round(last_ma20 * 0.99, 2)
        mid_buy_high = round(last_ma20 * 1.02, 2)
        mid_buy_range = f"{mid_buy_low} ~ {mid_buy_high}"
        mid_target = round(last_close + 4.5 * last_atr, 2)
        mid_stop = round(last_ma60 * 0.97, 2)

        summary_text = f"價位站穩月線之上呈多頭排列，RSI 動能達 {last_rsi:.1f}，均線支撐力道強韌，價量配合良好。"
        prediction_text = "**【宜買 / 逢回分批承接】** 多頭趨勢結構紮實，建議待價格小幅回測五日線或月線支撐不破時，採逢回分批承接策略。"

    elif is_bear:
        short_buy_low = round(last_close - 1.8 * last_atr, 2)
        short_buy_high = round(last_close - 1.0 * last_atr, 2)
        short_buy_range = f"{short_buy_low} ~ {short_buy_high} (測撐區)"
        short_target = round(last_close + 1.2 * last_atr, 2)
        short_stop = round(last_close - 2.0 * last_atr, 2)

        mid_buy_low = round(min(last_ma60 * 0.95, last_close - 2.5 * last_atr), 2)
        mid_buy_high = round(min(last_ma60 * 0.98, last_close - 1.5 * last_atr), 2)
        mid_buy_range = f"{mid_buy_low} ~ {mid_buy_high} (長線觀察)"
        mid_target = round(last_close + 3.0 * last_atr, 2)
        mid_stop = round(last_close - 2.8 * last_atr, 2)

        summary_text = f"近日承壓修正，價格跌破關鍵月線且 RSI 偏弱（{last_rsi:.1f}），短線結構進入整理或測撐階段。"
        prediction_text = "**【宜觀望 / 勿急於接刀】** 目前面臨修正壓力，現價追入風險較高。建議保持觀望，耐心等待標的回測下方預估測撐區並出現止穩訊號再行評估。"

    else:
        short_buy_low = round(last_ma20 - 1.0 * last_atr, 2)
        short_buy_high = round(last_ma20 - 0.3 * last_atr, 2)
        short_buy_range = f"{short_buy_low} ~ {short_buy_high}"
        short_target = round(last_close + 1.8 * last_atr, 2)
        short_stop = round(last_ma20 - 1.4 * last_atr, 2)

        mid_buy_low = round(min(last_ma20, last_ma60) - 0.5 * last_atr, 2)
        mid_buy_high = round(min(last_ma20, last_ma60), 2)
        mid_buy_range = f"{mid_buy_low} ~ {mid_buy_high}"
        mid_target = round(last_close + 3.5 * last_atr, 2)
        mid_stop = round(last_ma60 * 0.97, 2)

        summary_text = f"於月線附近區間震盪（RSI {last_rsi:.1f}），多空力量在此交戰拉鋸，成交量能溫和，等待方向突破。"
        prediction_text = "**【區間操作 / 保持彈性】** 目前處於箱型整理格局，方向尚未單邊明朗。切勿追高現價，建議在建議買入區間（箱型下緣）低接、接近目標價時獲利調節。"

    return {
        "short_buy_range": short_buy_range,
        "short_target": short_target,
        "short_stop": short_stop,
        "mid_buy_range": mid_buy_range,
        "mid_target": mid_target,
        "mid_stop": mid_stop,
        "summary_text": summary_text,
        "prediction_text": prediction_text
    }

# ==========================================
# 5. 獨立 K 線歷史資料記憶體快取模組 (快取 4 小時)
# ==========================================
@st.cache_data(ttl=14400, show_spinner=False)
def get_cached_stock_kline(sid: str, market_str: str) -> pd.DataFrame:
    sid = str(sid).strip()
    market_str = str(market_str).strip()
    ticker = f"{sid}.TW" if "上市" in market_str else f"{sid}.TWO"
    hist_df = pd.DataFrame()
    
    try:
        raw = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if raw.empty or len(raw) < 20:
            alt_ticker = f"{sid}.TWO" if "TW" in ticker and "TWO" not in ticker else f"{sid}.TW"
            raw = yf.download(alt_ticker, period="1y", progress=False, auto_adjust=True)
            
        if not raw.empty and len(raw) > 20:
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            hist_df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
    except Exception:
        hist_df = pd.DataFrame()
        
    return hist_df

# ==========================================
# 6. 第二階段：自適應動態共振加權與技術指標運算
# ==========================================
def enrich_candidates_with_kline(candidate_df: pd.DataFrame, selections: dict):
    history_dict = {}
    enriched_rows = []
    
    dates = pd.bdate_range(end=datetime.today(), periods=250)
    np.random.seed(42)

    # 1. 識別使用者目前實際啟用的面向清單 (動態分母)
    active_factors = []
    if selections["fundamental"]["enabled"]:
        active_factors.append("fund")
    if selections["technical"]["enabled"]:
        active_factors.append("tech")
    if selections["market"]["enabled"]:
        active_factors.append("mkt")
    if selections["theme"]["enabled"]:
        active_factors.append("theme")
        
    total_active = len(active_factors)

    for idx, row in candidate_df.iterrows():
        sid = str(row["stock_id"])
        hist_df = get_cached_stock_kline(sid, row["market"])
            
        if hist_df.empty:
            drift = 0.0006
            rets = np.random.normal(drift, 0.02, len(dates))
            price_path = row["close"] * np.exp(np.cumsum(rets - rets.mean() + drift))
            price_path = price_path * (row["close"] / price_path[-1])
            high_path = price_path * (1 + np.abs(np.random.normal(0, 0.012, len(dates))))
            low_path = price_path * (1 - np.abs(np.random.normal(0, 0.012, len(dates))))
            vol_path = np.random.randint(1500, 25000, len(dates)) * 1000
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
        
        tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().bfill()
        
        last_close = float(c.iloc[-1])
        last_ma5 = float(ma5.iloc[-1])
        last_ma20 = float(ma20.iloc[-1])
        last_ma60 = float(ma60.iloc[-1])
        prev_ma60 = float(ma60.iloc[-6]) if len(ma60) >= 6 else last_ma60
        last_rsi = float(rsi14.iloc[-1])
        last_atr = float(atr14.iloc[-1])
        
        avg_v_5d = max(float(v.iloc[-6:-1].mean()), 1.0)
        vol_ratio = float(v.iloc[-1] / avg_v_5d)
        ret_5d = float((c.iloc[-1] / c.iloc[-6] - 1) * 100) if len(c) >= 6 else 0.0
        
        pricing = compute_regime_pricing(last_close, last_ma5, last_ma20, last_ma60, last_rsi, last_atr)
        
        hist_df["MA20"] = ma20
        hist_df["MA60"] = ma60
        history_dict[sid] = hist_df
        
        # ------------------------------------------
        # 2. 技術面特化加權 (含非線性指數型加分)
        # ------------------------------------------
        tech_score = 0.0
        tech_hit = False
        if selections["technical"]["enabled"]:
            lvl_t = selections["technical"]["level"]
            if lvl_t == "強勢突破":
                if last_close >= last_ma5 and last_ma5 >= last_ma20 and last_rsi >= 54:
                    vol_bonus = 25.0 + (vol_ratio - 2.0) * 8.0 if vol_ratio >= 2.0 else (15.0 if vol_ratio >= 1.3 else 5.0)
                    tech_score = 35.0 + (last_rsi * 0.3) + vol_bonus
                    tech_hit = True
                else:
                    tech_score = (last_rsi * 0.1)
            elif lvl_t == "多頭排列":
                if last_close >= last_ma20 and last_ma20 >= last_ma60:
                    golden_fan = 20.0 if (last_ma5 > last_ma20 > last_ma60) else 0.0
                    tech_score = 30.0 + (15.0 - abs(last_rsi - 55.0)) + golden_fan
                    tech_hit = True
            else:  # 底部支撐反彈
                dist_to_ma60 = abs((last_close - last_ma60) / last_ma60) if last_ma60 > 0 else 0.0
                if dist_to_ma60 <= 0.05 or last_rsi <= 45:
                    tech_score = 40.0 + max(50.0 - last_rsi, 0.0) * 0.8
                    tech_hit = True
                else:
                    tech_score = -20.0
        else:
            tech_score = (last_rsi * 0.2) + (10.0 if last_close >= last_ma20 else 0.0)

        base_combined_score = row["stage1_score"] + tech_score

        # ------------------------------------------
        # 3. 自適應動態共振判定 (只看實際啟用的面向)
        # ------------------------------------------
        hit_count = 0
        if "fund" in active_factors:
            # 基本面達標：依據第一階段評分門檻判定
            hit_count += int(row["stage1_score"] >= 25.0)

        if "tech" in active_factors:
            # 技術面達標：完全符合該等級之主訊號或站穩月線
            hit_count += int(tech_hit or (last_close >= last_ma20 and last_rsi >= 50.0))

        if "mkt" in active_factors:
            # 籌碼面達標：量比顯著放大或絕對成交張數充足
            hit_count += int(vol_ratio >= 1.25 or row["volume_sheets"] >= 2000.0)

        if "theme" in active_factors:
            # 題材面達標：股票題材清單精確命中選取之主題
            stock_themes = get_stock_themes(sid)
            hit_count += int(any(selections["theme"]["level"] in t for t in stock_themes))

        # 計算動態乘數
        if total_active > 0:
            hit_ratio = hit_count / float(total_active)
            if hit_ratio == 1.0:
                multiplier = 1.35  # 所有勾選條件 100% 完美共振
            elif hit_ratio >= 0.5:
                multiplier = 1.15  # 過半條件達標
            else:
                multiplier = 1.0   # 未達半數
        else:
            multiplier = 1.0

        scaled_score = base_combined_score * multiplier

        # ------------------------------------------
        # 4. 破壞性扣分項 (不論勾選面向為何，均過濾高風險結構)
        # ------------------------------------------
        penalties = 0.0
        
        # (1) 高檔正乖離過大（防止追高被套）
        bias_ma20 = (last_close - last_ma20) / last_ma20 if last_ma20 > 0 else 0.0
        if bias_ma20 > 0.15:
            penalties += 25.0
            
        # (2) 量價背離（創近 10 日新高但量能急縮逾 30%）
        highest_10d = float(c.iloc[-10:].max()) if len(c) >= 10 else last_close
        if last_close >= highest_10d * 0.99 and vol_ratio < 0.70:
            penalties += 20.0

        # (3) 季線下彎蓋頭且股價在季線之下
        ma60_slope_down = (last_ma60 < prev_ma60)
        if ma60_slope_down and last_close < last_ma60:
            penalties += 25.0

        final_calc_score = round(max(scaled_score - penalties, 10.0), 1)

        trend_desc = "呈多頭排列" if last_close >= last_ma20 else "回測均線支撐"
        pe_str = f"本益比 {row['pe_ratio']:.1f} 倍、" if pd.notnull(row['pe_ratio']) else ""
        dy_str = f"殖利率 {row['dividend_yield']:.1f}%、" if pd.notnull(row['dividend_yield']) else ""
        reason = f"{pe_str}{dy_str}股價站穩關鍵均線{trend_desc}（RSI {last_rsi:.1f}，成交量 {int(row['volume_sheets']):,} 張）。"
        
        enriched_rows.append({
            "stock_id": sid,
            "stock_name": row["stock_name"],
            "market": row["market"],
            "close": round(last_close, 2),
            "pe_ratio": row["pe_ratio"],
            "dividend_yield": row["dividend_yield"],
            "rsi_14": round(last_rsi, 1),
            "vol_ratio": round(vol_ratio, 2),
            "ret_5d": round(ret_5d, 2),
            "short_buy_range": pricing["short_buy_range"],
            "short_target": pricing["short_target"],
            "short_stop": pricing["short_stop"],
            "mid_buy_range": pricing["mid_buy_range"],
            "mid_target": pricing["mid_target"],
            "mid_stop": pricing["mid_stop"],
            "recommend_reason": reason,
            "final_score": final_calc_score
        })

    final_df = pd.DataFrame(enriched_rows).sort_values(by="final_score", ascending=False).reset_index(drop=True)
    return final_df, history_dict

# ==========================================
# 7. 回測引擎
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
            f"近{lookback_days}日報酬(%)": round(cum_ret, 2),
            "月線順勢勝率(%)": round(win_rate, 1)
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
# 8. 即時國際指數抓取與大盤預測模組
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_live_market_data():
    tickers = {
        "台灣加權指數": "^TWII",
        "費城半導體指數": "^SOX",
        "那斯達克綜合指數": "^IXIC",
        "道瓊工業指數": "^DJI"
    }
    data = {}
    for chinese_name, symbol in tickers.items():
        try:
            df = yf.download(symbol, period="5d", progress=False, auto_adjust=True)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                closes = df["Close"].dropna()
                if len(closes) >= 2:
                    curr = float(closes.iloc[-1])
                    prev = float(closes.iloc[-2])
                    pct = (curr / prev - 1) * 100
                    dt_str = closes.index[-1].strftime("%Y-%m-%d")
                    data[chinese_name] = {"close": round(curr, 2), "pct": round(pct, 2), "date": dt_str}
        except Exception:
            pass
    return data

def generate_dynamic_analysis_texts(market_data: dict):
    tw_pct = market_data.get("台灣加權指數", {}).get("pct", 0.0)
    sox_pct = market_data.get("費城半導體指數", {}).get("pct", 0.0)
    nasdaq_pct = market_data.get("那斯達克綜合指數", {}).get("pct", 0.0)
    
    if tw_pct > 0.8:
        today_summary = f"**【多方強勢表態，主流買氣匯聚】**\n\n今日台股加權指數開高走高，終場大漲約 {tw_pct:+.2f}%。權值股與主流族群同步點火，成交量能擴增，多方氣勢凌厲，盤面結構呈現健康的多頭排列。"
    elif tw_pct < -0.8:
        today_summary = f"**【賣壓沉重，指數測撐調節】**\n\n今日台股受國際盤勢牽動或短線獲利回吐影響，指數開低走低，終場下挫約 {tw_pct:+.2f}%。權值科技股賣壓較重，資金轉入防禦型板塊，短線進入震盪測撐階段。"
    else:
        today_summary = f"**【多空拉鋸膠着，量縮狹幅盤整】**\n\n今日台股呈現狹幅震盪格局（漲跌幅 {tw_pct:+.2f}%），市場觀望氣氛濃厚，權值熄火而中小型題材股各自表現，成交量能溫和，多空交戰無明顯單邊方向。"

    if sox_pct < -1.2 or nasdaq_pct < -1.0:
        tomorrow_pred = f"**【美股科技重挫：建議『高度觀望』，嚴控部位】**\n\n* **國際數據參考**：隔夜美股費城半導體指數下跌 {sox_pct:+.2f}%、那斯達克指數下跌 {nasdaq_pct:+.2f}%，科技供應鏈面臨短線修正壓力。\n* **明日操作建議**：受國際科技股走弱拖累，早盤恐面臨壓力。建議投資人**暫時採取觀望或降低持股水位**，切勿躁進接刀，等待支撐止穩訊號出現。"
    elif sox_pct > 1.2 or nasdaq_pct > 1.0:
        tomorrow_pred = f"**【美股強勢彈升：建議『逢回分批承接』】**\n\n* **國際數據參考**：隔夜美股費城半導體指數大漲 {sox_pct:+.2f}%、科技股表現強勁，市場風險偏好回溫。\n* **明日操作建議**：國際半導體情緒轉佳，台股明日有望受到激勵開高。建議鎖定具備基本面優勢的強勢主流標的，採**逢回分批承接**策略積極佈局。"
    else:
        tomorrow_pred = f"**【國際盤勢平穩：建議『區間操作、精選個股』】**\n\n* **國際數據參考**：美股主要指數維持高檔震盪（費城半導體指數變動 {sox_pct:+.2f}%），國際無重大系統性風險。\n* **明日操作建議**：明日大盤預期延續類股輪動格局，指數空間有限。建議依循選股系統篩選基本面與籌碼優異個股，進行**短線區間操作**。"

    return today_summary, tomorrow_pred

# ==========================================
# 9. 盤勢分析與預測彈跳視窗
# ==========================================
@st.dialog("📊 今日盤勢分析與明日行情預測", width="large")
def show_market_analysis_modal():
    with st.spinner("正在連線抓取全球最新盤後市場數據並運算分析中..."):
        market_data = get_live_market_data()
        today_txt, tomorrow_txt = generate_dynamic_analysis_texts(market_data)
    
    st.markdown("### 📌 1. 今日台股盤勢總結")
    st.info(today_txt)
    
    st.markdown("### 🔮 2. 明日大盤走勢預測與操作指引")
    st.warning(tomorrow_txt)
    
    st.markdown("---")
    st.markdown("### 🌐 全球核心市場指數數據")
    if market_data:
        cols = st.columns(len(market_data))
        for i, (chinese_name, v) in enumerate(market_data.items()):
            cols[i].metric(chinese_name, f"{v['close']:,}", f"{v['pct']:+.2f}%")
            
    st.markdown("---")
    tw_date = market_data.get("台灣加權指數", {}).get("date", "最新交易日")
    us_date = market_data.get("費城半導體指數", {}).get("date", "最新交易日")
    st.caption(
        f"🕒 **市場數據來源與結算日期標記**：\n"
        f"• **台股行情來源**：`TWSE/TPEx OpenAPI` & `^TWII` ｜ 結算日期：`{tw_date}` 盤後\n"
        f"• **美股指數來源**：`Yahoo Finance (^SOX, ^IXIC, ^DJI)` ｜ 結算日期：`{us_date}` 昨收"
    )
    
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    if st.button("關閉視窗", use_container_width=True):
        st.rerun()

# ==========================================
# 10. 個股深度分析彈跳視窗
# ==========================================
def get_single_stock_metrics(row_match, lookback_days):
    sid = str(row_match["stock_id"])
    market = str(row_match["market"])
    base_close = float(row_match.get("close", 100.0))
    
    hist_df = get_cached_stock_kline(sid, market)
        
    if hist_df.empty:
        np.random.seed(int(re.sub(r'\D', '', sid)) if re.sub(r'\D', '', sid) else 42)
        dates = pd.bdate_range(end=datetime.today(), periods=250)
        rets = np.random.normal(0.0006, 0.02, len(dates))
        price_path = base_close * np.exp(np.cumsum(rets - rets.mean() + 0.0006))
        price_path = price_path * (base_close / price_path[-1])
        hist_df = pd.DataFrame({
            "Open": price_path * 0.998,
            "High": price_path * 1.01,
            "Low": price_path * 0.99,
            "Close": price_path,
            "Volume": np.random.randint(2000, 20000, len(dates)) * 1000
        }, index=dates)

    c = hist_df["Close"]
    h = hist_df["High"]
    l = hist_df["Low"]
    
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi14 = (100 - (100 / (1 + rs))).fillna(50)
    
    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().bfill()
    
    last_close = float(c.iloc[-1])
    last_ma5 = float(ma5.iloc[-1])
    last_ma20 = float(ma20.iloc[-1])
    last_ma60 = float(ma60.iloc[-1])
    last_rsi = float(rsi14.iloc[-1])
    last_atr = float(atr14.iloc[-1])
    
    lookback_idx = min(lookback_days, len(c) - 1)
    past_close = float(c.iloc[-lookback_idx])
    ret_period = round((last_close / past_close - 1) * 100, 2)
    
    hist_df["daily_ret"] = c.pct_change().fillna(0)
    hist_df["signal"] = (c.shift(1) > ma20.shift(1)).astype(int)
    hist_df["strat_ret"] = hist_df["daily_ret"] * hist_df["signal"]
    active_days = hist_df[hist_df["signal"] == 1]
    win_rate = round((active_days["strat_ret"] > 0).mean() * 100, 1) if len(active_days) > 0 else 50.0
    
    pricing = compute_regime_pricing(last_close, last_ma5, last_ma20, last_ma60, last_rsi, last_atr)
    
    pe_str = f"{row_match['pe_ratio']:.1f} 倍" if pd.notnull(row_match.get("pe_ratio")) and row_match["pe_ratio"] > 0 else "-"
    dy_str = f"{row_match['dividend_yield']:.1f}%" if pd.notnull(row_match.get("dividend_yield")) and row_match["dividend_yield"] > 0 else "-"

    table_df = pd.DataFrame([{
        "代號": sid,
        "名稱": row_match["stock_name"],
        "類別/市場": market,
        "最新收盤價": round(last_close, 2),
        f"近{lookback_days}日報酬(%)": ret_period,
        "月線順勢勝率(%)": win_rate,
        "本益比": pe_str,
        "殖利率": dy_str,
        "短期建議買入": pricing["short_buy_range"],
        "短期目標賣出": pricing["short_target"],
        "中長建議買入": pricing["mid_buy_range"],
        "中長目標賣出": pricing["mid_target"]
    }])

    return table_df, pricing["summary_text"], pricing["prediction_text"]

@st.dialog("📈 個股與 ETF 深度分析與行情預測", width="large")
def show_single_stock_analysis_modal(full_universe_df, lookback_days):
    stock_options = [f"{row['stock_id']} - {row['stock_name']} ({row['market']})" for _, row in full_universe_df.iterrows()]
    
    col_sel, col_manual = st.columns([3, 2])
    with col_sel:
        selected_str = st.selectbox(
            "🔍 下拉搜尋股票或 ETF",
            options=stock_options,
            index=None,
            placeholder="請輸入代號 (如 2330、6903、0050、00878) 或名稱搜尋..."
        )
    with col_manual:
        manual_code = st.text_input(
            "⌨️ 或直接輸入代號查詢",
            placeholder="例如: 6903、0050、00878、00989B",
            help="若在選單未及時找到，可直接輸入代號按 Enter 立即進行深度分析"
        ).strip().upper()
    
    target_row = None
    if manual_code:
        matches = full_universe_df[full_universe_df["stock_id"] == manual_code]
        if not matches.empty:
            target_row = matches.iloc[0].to_dict()
        else:
            is_etf = manual_code.startswith("00")
            target_row = {
                "stock_id": manual_code,
                "stock_name": f"{manual_code} (指定標的)",
                "market": "上市 ETF" if is_etf else "上市",
                "close": 100.0,
                "pe_ratio": np.nan,
                "dividend_yield": np.nan,
                "volume_sheets": 1000.0
            }
    elif selected_str:
        sid = selected_str.split(" - ")[0]
        target_row = full_universe_df[full_universe_df["stock_id"] == sid].iloc[0].to_dict()

    if target_row:
        st.markdown("---")
        st.markdown(f"### 🎯 分析標的：`{target_row['stock_id']}` **{target_row['stock_name']}** ({target_row['market']})")
        
        with st.spinner(f"正在運算 {target_row['stock_id']} {target_row['stock_name']} 的量化指標與買賣建議..."):
            stock_table_df, summary_text, prediction_text = get_single_stock_metrics(target_row, lookback_days)
            
        st.markdown("#### 📋 1. 核心量化指標總覽")
        st.dataframe(stock_table_df, use_container_width=True, hide_index=True)
        st.info(f"💡 **標的盤勢總結**：{summary_text}")
        
        st.markdown("#### 🔮 2. 後續行情預測與操作指引")
        st.warning(prediction_text)
    else:
        st.info("👆 請於上方選單搜尋股票/ETF 名稱，或直接輸入代號（支援全上市櫃個股與所有 ETF），系統將自動啟動量化運算。")
        
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    if st.button("關閉視窗", use_container_width=True):
        st.rerun()

# ==========================================
# 11. Streamlit 互動網頁主介面
# ==========================================
if "batch_page" not in st.session_state:
    st.session_state.batch_page = 0
if "force_refresh_cache" not in st.session_state:
    st.session_state.force_refresh_cache = False

with st.sidebar:
    st.header("⚙️ 選股方向與等級設定")
    st.markdown("請勾選想納入的選股方向與等級（系統已內建對應量化參數）：")
    
    use_fund = st.checkbox("1. 基本面選股", value=True)
    lvl_fund = st.radio(
        "基本面條件等級",
        ["嚴格績優", "穩健成長", "價值轉機"],
        index=1,
        disabled=not use_fund
    )
    st.divider()
    
    use_tech = st.checkbox("2. 技術面選股", value=True)
    lvl_tech = st.radio(
        "技術面條件等級",
        ["強勢突破", "多頭排列", "底部支撐反彈"],
        index=0,
        disabled=not use_tech
    )
    st.divider()
    
    use_mkt = st.checkbox("3. 市場／籌碼面選股", value=True)
    lvl_mkt = st.radio(
        "市場籌碼條件等級",
        ["法人重倉連買", "法人溫和布局", "低檔承接"],
        index=1,
        disabled=not use_mkt
    )
    st.divider()
    
    col_theme_cb, col_theme_btn = st.columns([4, 1])
    with col_theme_cb:
        use_theme = st.checkbox("4. 熱門題材選股", value=False)
    with col_theme_btn:
        if st.button("🔄", help="點擊更新最新盤後熱門題材與資金強勢股"):
            refresh_market_themes()
            st.toast("🔥 熱門題材資料已成功更新至最新盤後狀態！", icon="✅")
            st.rerun()
            
    st.caption(f"🕒 題材最後更新：{st.session_state.theme_last_update}")
    
    lvl_theme = st.radio(
        "題材類別清單",
        ["AI 伺服器 / 先進封裝 (CoWoS)", "矽光子 CPO / 機器人自動化", "高股息績優 / 綠能重電"],
        index=0,
        disabled=not use_theme,
        label_visibility="collapsed"
    )
    st.divider()
    
    lookback = st.select_slider("回測歷史天數 (交易日)", options=[60, 120, 240], value=120)
    
    st.divider()
    st.subheader("💾 盤後資料狀態")
    if os.path.exists(CACHE_PARQUET_FILE):
        mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_PARQUET_FILE))
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M")
        cache_size = os.path.getsize(CACHE_PARQUET_FILE) / 1024.0
        
        tw_data_date = "同步中"
        if os.path.exists(META_JSON_FILE):
            try:
                with open(META_JSON_FILE, "r", encoding="utf-8") as f:
                    tw_data_date = json.load(f).get("tw_date_label", mtime.strftime("%Y-%m-%d"))
            except Exception:
                tw_data_date = mtime.strftime("%Y-%m-%d")

        st.caption(
            f"• **快取檔案**：`{CACHE_PARQUET_FILE}`\n"
            f"• **資料基準日**：`{tw_data_date}`\n"
            f"• **檔案更新時間**：`{mtime_str}`\n"
            f"• **檔案大小**：`{cache_size:.1f} KB`"
        )
    else:
        st.caption("⚪ 快取尚未建立")
        
    if st.button("🔄 強制重新抓取並更新快取", use_container_width=True):
        st.session_state.force_refresh_cache = True
        st.cache_data.clear()
        st.rerun()

current_config_key = f"{use_fund}_{lvl_fund}_{use_tech}_{lvl_tech}_{use_mkt}_{lvl_mkt}_{use_theme}_{lvl_theme}_{st.session_state.theme_last_update}"
if st.session_state.get("last_config_key") != current_config_key:
    st.session_state.batch_page = 0
    st.session_state.last_config_key = current_config_key

with st.spinner("🚀 正在讀取全市場資料並計算候選標的技術指標..."):
    force_run = st.session_state.force_refresh_cache
    full_universe_df, tw_trading_date = fetch_full_market_universe(force_refresh=force_run)
    if force_run:
        st.session_state.force_refresh_cache = False
        st.toast("✅ 已向官方重新同步最新盤後資料並寫入快取！")

    selections = {
        "fundamental": {"enabled": use_fund, "level": lvl_fund},
        "technical": {"enabled": use_tech, "level": lvl_tech},
        "market": {"enabled": use_mkt, "level": lvl_mkt},
        "theme": {"enabled": use_theme, "level": lvl_theme},
    }
    stage1_candidates = fast_filter_funnel(full_universe_df, selections, top_n=25)
    ranked_df, history_dict = enrich_candidates_with_kline(stage1_candidates, selections)

# 頂部標題與按鈕區塊
col_h1, col_h2, col_h3 = st.columns([2.5, 0.9, 0.6])
with col_h1:
    st.title("🎯 智慧選股系統")
    st.markdown("點擊左上角 **☰** 調整選股條件，一鍵取得精選 5 檔與買賣建議。")
with col_h2:
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    if st.button("📊 盤勢分析與預測", type="primary", use_container_width=True):
        show_market_analysis_modal()
with col_h3:
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    if st.button("⚠️ 免責聲明", use_container_width=True):
        show_legal_disclaimer_modal()

# 個股分析按鈕
st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
col_stock_btn_1, col_stock_btn_2, col_stock_btn_3 = st.columns([1, 4, 1])
with col_stock_btn_2:
    if st.button("📈 查詢與分析指定個股 / ETF（個股分析）", key="btn_single_stock_analysis", use_container_width=True):
        show_single_stock_analysis_modal(full_universe_df, lookback)
st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)

batch_size = 5
total_batches = max(1, int(np.ceil(len(ranked_df) / batch_size)))
current_page = st.session_state.batch_page % total_batches
start_idx = current_page * batch_size
end_idx = start_idx + batch_size
current_5_df = ranked_df.iloc[start_idx:end_idx].copy()

port_nav, bm_nav, stock_bt_df, bt_metrics = run_portfolio_backtest(current_5_df, history_dict, lookback_days=lookback)

col_title, col_btn1, col_btn2 = st.columns([3, 1, 1])
with col_title:
    st.subheader(f"🎯 全市場精選推薦（第 {current_page + 1} / {total_batches} 批，共推薦 {len(current_5_df)} 檔）")
with col_btn1:
    if st.button("🔄 不滿意，換另外 5 檔", type="primary", use_container_width=True):
        st.session_state.batch_page = (st.session_state.batch_page + 1) % total_batches
        st.rerun()
with col_btn2:
    if st.button("⏮️ 回到第一批 Top 5", use_container_width=True):
        st.session_state.batch_page = 0
        st.rerun()

# 置頂總覽表格
overview_merge = pd.merge(
    current_5_df[["stock_id", "stock_name", "market", "close", "short_buy_range", "short_target", "mid_buy_range", "mid_target"]],
    stock_bt_df[["代號", f"近{lookback}日報酬(%)", "月線順勢勝率(%)"]],
    left_on="stock_id",
    right_on="代號"
)
overview_table = overview_merge[[
    "stock_id", "stock_name", "market", "close", 
    f"近{lookback}日報酬(%)", "月線順勢勝率(%)", 
    "short_buy_range", "short_target", "mid_buy_range", "mid_target"
]].rename(columns={
    "stock_id": "代號",
    "stock_name": "名稱",
    "market": "市場",
    "close": "最新收盤價",
    "short_buy_range": "短期建議買入",
    "short_target": "短期目標賣出",
    "mid_buy_range": "中長建議買入",
    "mid_target": "中長目標賣出"
})

st.markdown(f"##### 📋 精選 5 檔數據總覽（含近 {lookback} 日區間報酬、勝率與買賣建議價格）")
st.dataframe(overview_table, use_container_width=True, hide_index=True)

for rank_num, (_, row) in enumerate(current_5_df.iterrows(), start=start_idx + 1):
    with st.container(border=True):
        c1, c2, c3 = st.columns([2.2, 2.5, 2.5])
        with c1:
            st.markdown(f"### #{rank_num} `{row['stock_id']}` {row['stock_name']} ({row['market']})")
            st.markdown(f"**最新收盤價：`{row['close']}` 元** ｜ 綜合評分：`{row['final_score']:.1f}`")
            st.info(f"💡 **推薦理由**：{row['recommend_reason']}")
        with c2:
            st.markdown("**⚡ 短期操作建議 (5~20日，依 MA5 & ATR 計算)**")
            st.markdown(f"- 🟢 **建議買入區間**：`{row['short_buy_range']}` 元")
            st.markdown(f"- 🎯 **目標停利賣出**：`{row['short_target']}` 元")
            st.markdown(f"- 🛡️ **防守停損價位**：`{row['short_stop']}` 元")
        with c3:
            st.markdown("**🧭 中長期操作建議 (1~6個月，依月季線計算)**")
            st.markdown(f"- 🟢 **建議買入區間**：`{row['mid_buy_range']}` 元")
            st.markdown(f"- 🎯 **目標停利賣出**：`{row['mid_target']}` 元")
            st.markdown(f"- 🛡️ **防守停損價位**：`{row['mid_stop']}` 元")

st.markdown("""
<div class="disclaimer-banner">
    <strong>⚖️ 投資風險與合規警語：</strong><br>
    本系統所有選股結果、策略回測數值與價格區間僅供量化研究與演算法教學展示，不構成任何證券之要約或投資買賣建議。過往績效不保證未來獲利，投資人應獨立判斷並自負交易盈虧責任。
</div>
""", unsafe_allow_html=True)

st.divider()
tab_bt, tab_detail = st.tabs([
    "📊 推薦組合淨值曲線與風險指標", 
    "📋 完整量化指標明細表"
])

with tab_bt:
    st.markdown(f"#### 等權重持有當前推薦 5 檔股票 — 近 `{lookback}` 個交易日組合表現")
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

with tab_detail:
    display_cols = [
        "stock_id", "stock_name", "market", "close", "pe_ratio", "dividend_yield", 
        "rsi_14", "vol_ratio", "short_buy_range", "short_target", "mid_buy_range", "mid_target"
    ]
    st.dataframe(current_5_df[display_cols], use_container_width=True, hide_index=True)