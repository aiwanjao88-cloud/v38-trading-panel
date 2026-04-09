from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="上帝視角 V10.2", page_icon="📈", layout="wide")

# =========================================================
# 固定策略參數（側欄不顯示）
# =========================================================
DEFAULT_CAPITAL = 200000
FIXED_STOP_LOSS_PCT = 0.05
FIXED_TAKE_PROFIT_PCT = 0.10
FIXED_MAX_RECOMMEND = 3
FIXED_REFRESH_SECONDS = 60

TWSE_STOCK_DAY_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

CORE_TW_POOL = [
    "2330", "2317", "2454", "2382", "2308", "2412", "3231", "3037",
    "3443", "3661", "3017", "2379", "3034", "2408", "2357", "2383",
    "2881", "2882", "2886", "2884", "2891", "5871",
    "2603", "2609", "1301", "1303", "2002", "2207",
    "0050", "0056", "00713", "00878", "00919", "00929", "00940"
]

SECTOR_BUCKETS = {
    "半導體/AI": {"2330", "2454", "2308", "3443", "3661", "3017", "3034"},
    "電子代工/硬體": {"2317", "2382", "2379", "2357", "2408", "2383", "3231", "3037"},
    "金融": {"2881", "2882", "2886", "2884", "2891", "5871"},
    "航運": {"2603", "2609"},
    "傳產": {"1301", "1303", "2002", "2207"},
    "ETF": {"0050", "0056", "00713", "00878", "00919", "00929", "00940"},
}


# =========================================================
# 基本工具
# =========================================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_symbol(symbol: str) -> str:
    if symbol is None:
        return ""
    return str(symbol).strip().upper()


def to_tw_code(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    if symbol.endswith(".TW"):
        return symbol[:-3]
    return symbol


def to_yf_symbol(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    return symbol if symbol.endswith(".TW") else f"{to_tw_code(symbol)}.TW"


def safe_float(x):
    try:
        if x in [None, "", "-", "--", "None", "nan", "NaN"]:
            return None
        val = float(str(x).replace(",", ""))
        if pd.isna(val):
            return None
        return val
    except Exception:
        return None


def display_str(x, digits: int = 2) -> str:
    val = safe_float(x)
    if val is None:
        return ""
    return str(round(val, digits))


def clean_text(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


def get_sector_for_symbol(symbol: str) -> str:
    code = to_tw_code(symbol)
    for sector, members in SECTOR_BUCKETS.items():
        if code in members:
            return sector
    return "其他"


def get_confidence_label(score: Optional[float]) -> str:
    score = safe_float(score)
    if score is None:
        return "未知"
    if score >= 90:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    if score >= 45:
        return "C"
    return "D"


def get_confidence_color(score: Optional[float]) -> str:
    score = safe_float(score)
    if score is None:
        return "#64748b"
    if score >= 90:
        return "#22c55e"
    if score >= 75:
        return "#10b981"
    if score >= 60:
        return "#f59e0b"
    if score >= 45:
        return "#fb923c"
    return "#ef4444"


# =========================================================
# 深色專業介面
# =========================================================
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(59,130,246,.12), transparent 25%),
            radial-gradient(circle at top right, rgba(16,185,129,.08), transparent 22%),
            linear-gradient(180deg, #060b16 0%, #0b1220 40%, #0f172a 100%);
        color: #e5e7eb;
    }

    .block-container {
        max-width: 1320px;
        padding-top: 1.1rem;
        padding-bottom: 4rem;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1220 0%, #111827 100%);
        border-right: 1px solid rgba(148,163,184,.15);
    }

    [data-testid="stSidebar"] * {
        color: #e5e7eb !important;
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(15,23,42,.96), rgba(17,24,39,.96));
        border: 1px solid rgba(148,163,184,.12);
        border-radius: 18px;
        padding: 12px 14px;
        box-shadow: 0 10px 25px rgba(2,6,23,.35);
    }

    .hero-card {
        background: linear-gradient(135deg, rgba(15,23,42,.96), rgba(17,24,39,.95));
        border: 1px solid rgba(96,165,250,.18);
        border-radius: 24px;
        padding: 20px 20px 16px 20px;
        box-shadow: 0 18px 40px rgba(2,6,23,.38);
        margin-bottom: 10px;
    }

    .title-xl {
        font-size: 1.2rem;
        font-weight: 900;
        color: #f8fafc;
        margin-bottom: 6px;
        letter-spacing: .2px;
    }

    .muted {
        color: #94a3b8;
        font-size: .92rem;
    }

    .soft-box {
        background: linear-gradient(180deg, rgba(30,41,59,.95), rgba(15,23,42,.95));
        border: 1px solid rgba(59,130,246,.16);
        border-radius: 16px;
        padding: 14px 16px;
        margin-bottom: 10px;
        color: #e2e8f0;
        box-shadow: 0 8px 20px rgba(2,6,23,.28);
    }

    .signal-card {
        background: linear-gradient(145deg, rgba(15,23,42,.98), rgba(17,24,39,.98));
        border: 1px solid rgba(148,163,184,.14);
        border-radius: 22px;
        padding: 18px;
        min-height: 320px;
        box-shadow: 0 14px 30px rgba(2,6,23,.4);
    }

    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 800;
        margin-right: 6px;
        margin-bottom: 6px;
    }

    .kpi {
        font-size: 1.18rem;
        font-weight: 800;
        color: #f8fafc;
        margin: 6px 0;
    }

    .top-btn button {
        border-radius: 15px !important;
        height: 3.1rem !important;
        font-weight: 900 !important;
        background: linear-gradient(90deg, #2563eb, #3b82f6) !important;
        border: none !important;
        color: white !important;
        box-shadow: 0 10px 22px rgba(37,99,235,.35) !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        padding: 10px 14px;
        background: rgba(15,23,42,.88);
        border: 1px solid rgba(148,163,184,.10);
        color: #cbd5e1;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, rgba(37,99,235,.18), rgba(59,130,246,.18)) !important;
        border: 1px solid rgba(59,130,246,.25) !important;
        color: #f8fafc !important;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(148,163,184,.10);
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 10px 22px rgba(2,6,23,.22);
    }

    .stTextInput input, .stTextArea textarea, .stNumberInput input {
        background: rgba(15,23,42,.92) !important;
        color: #e5e7eb !important;
        border-radius: 12px !important;
        border: 1px solid rgba(148,163,184,.16) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 市場資料
# =========================================================
@st.cache_data(ttl=120)
def fetch_twse_stock_day_all() -> pd.DataFrame:
    try:
        r = requests.get(TWSE_STOCK_DAY_ALL_URL, timeout=15)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        if df.empty:
            return pd.DataFrame()

        rename_map = {
            "Code": "代碼",
            "Name": "股名",
            "TradeVolume": "成交股數",
            "TradeValue": "成交金額",
            "OpeningPrice": "開盤價",
            "HighestPrice": "最高價",
            "LowestPrice": "最低價",
            "ClosingPrice": "收盤價",
            "Change": "漲跌價差",
            "Transaction": "成交筆數",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df["代碼"] = df["代碼"].astype(str).str.strip()

        for col in ["成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"]:
            if col in df.columns:
                df[col] = df[col].apply(safe_float)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=180)
def get_yf_info(symbol: str) -> Dict[str, object]:
    yf_symbol = to_yf_symbol(symbol)
    result = {"股名": normalize_symbol(symbol), "目前價": None, "成交股數": None}

    try:
        t = yf.Ticker(yf_symbol)
        hist = t.history(period="5d")
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            result["目前價"] = safe_float(last.get("Close"))
            result["成交股數"] = safe_float(last.get("Volume"))
        info = t.info if hasattr(t, "info") else {}
        result["股名"] = info.get("shortName") or info.get("longName") or result["股名"]
    except Exception:
        pass

    return result


@st.cache_data(ttl=180)
def fetch_price_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    yf_symbol = to_yf_symbol(symbol)
    try:
        df = yf.download(yf_symbol, period=period, interval="1d", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[keep].copy()
        if "Close" not in df.columns:
            return pd.DataFrame()

        df["MA5"] = df["Close"].rolling(5).mean()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA60"] = df["Close"].rolling(60).mean()
        df["VOL20"] = df["Volume"].rolling(20).mean()
        df["RSI14"] = rsi(df["Close"], 14)
        df["Prev20High"] = df["High"].rolling(20).max().shift(1)
        df["Prev20Low"] = df["Low"].rolling(20).min().shift(1)
        df["Ret1D%"] = df["Close"].pct_change() * 100
        df["Ret5D%"] = df["Close"].pct_change(5) * 100
        df["VolumeRatio"] = df["Volume"] / df["VOL20"].replace(0, pd.NA)
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()


# =========================================================
# 掃描與推薦
# =========================================================
def calc_score(symbol: str, stop_loss_pct: float, take_profit_pct: float) -> Dict[str, object]:
    info = get_yf_info(symbol)
    df = fetch_price_history(symbol, "6mo")

    if df.empty or len(df) < 65:
        return {
            "代碼": to_tw_code(symbol),
            "股名": clean_text(info.get("股名", symbol)),
            "收盤": display_str(info.get("目前價")),
            "評分": -999,
            "等級": "資料不足",
            "訊號": "資料不足",
            "建議進場價": "",
            "停損價": "",
            "第一停利價": "",
            "風險報酬比": "",
            "異常事件": "",
            "族群": get_sector_for_symbol(symbol),
            "RSI": "",
        }

    last = df.iloc[-1]
    close = safe_float(last["Close"])
    ma5 = safe_float(last["MA5"])
    ma20 = safe_float(last["MA20"])
    ma60 = safe_float(last["MA60"])
    rsi14 = safe_float(last["RSI14"])
    vol_ratio = safe_float(last["VolumeRatio"])
    ret1d = safe_float(last["Ret1D%"])
    prev20h = safe_float(last["Prev20High"])
    prev20l = safe_float(last["Prev20Low"])

    score = 0
    anomaly = []

    if close and ma5 and ma20 and ma60:
        if close > ma5 > ma20 > ma60:
            score += 30
        elif close > ma5 > ma60:
            score += 20
        elif close < ma60:
            score -= 20

    if rsi14 is not None:
        if 55 <= rsi14 <= 75:
            score += 15
        elif rsi14 < 40:
            score -= 10
        elif rsi14 > 80:
            score -= 5

    if vol_ratio and vol_ratio >= 1.8:
        score += 15
        anomaly.append("放量")

    if close and prev20h and close > prev20h:
        score += 20
        anomaly.append("突破")

    if close and prev20l and close < prev20l:
        score -= 15
        anomaly.append("跌破")

    if ret1d and ret1d >= 4:
        score += 5
        anomaly.append("急拉")

    if ret1d and ret1d <= -4:
        anomaly.append("急殺")

    if score >= 60:
        level = "強勢"
        signal = "候選進攻"
    elif score >= 30:
        level = "觀察"
        signal = "續追蹤"
    else:
        level = "保守"
        signal = "不追價"

    entry = round(close, 2) if close else None
    stop = round(close * (1 - stop_loss_pct), 2) if close else None
    tp1 = round(close * (1 + take_profit_pct), 2) if close else None

    rr = ""
    if close and stop and tp1 and close > stop:
        risk = close - stop
        reward = tp1 - close
        if risk > 0:
            rr = round(reward / risk, 2)

    return {
        "市場": "台股",
        "代碼": to_tw_code(symbol),
        "股名": clean_text(info.get("股名", symbol)),
        "族群": get_sector_for_symbol(symbol),
        "收盤": display_str(close),
        "訊號": signal,
        "建議進場價": display_str(entry),
        "停損價": display_str(stop),
        "第一停利價": display_str(tp1),
        "風險報酬比": rr,
        "評分": int(score),
        "信心": get_confidence_label(score),
        "等級": level,
        "理由": " / ".join(anomaly) if anomaly else "趨勢正常",
        "異常事件": " / ".join(anomaly),
        "RSI": display_str(rsi14),
    }


def build_sector_rotation_df(scan_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(scan_df).copy()
    if df.empty:
        return pd.DataFrame(columns=["族群", "平均評分", "強勢檔數", "樣本數"])

    df["評分_num"] = pd.to_numeric(df["評分"], errors="coerce").fillna(-999)
    grp = (
        df.groupby("族群")
        .agg(
            平均評分=("評分_num", "mean"),
            強勢檔數=("評分_num", lambda x: int((x >= 60).sum())),
            樣本數=("代碼", "count"),
        )
        .reset_index()
        .sort_values(["平均評分", "強勢檔數"], ascending=False)
        .reset_index(drop=True)
    )
    grp["平均評分"] = grp["平均評分"].round(2)
    return as_object_df(grp)


def get_sector_strength_map(scan_df: pd.DataFrame) -> Dict[str, float]:
    sector_df = build_sector_rotation_df(scan_df)
    strength = {}
    if sector_df.empty:
        return strength
    for _, row in sector_df.iterrows():
        strength[clean_text(row["族群"])] = safe_float(row["平均評分"]) or 0
    return strength


def build_dynamic_tw_scan_pool(top_n_value: int = 100, top_n_volume: int = 80) -> List[str]:
    df = fetch_twse_stock_day_all()
    pool = []

    if not df.empty:
        work = df.copy()
        work = work[work["代碼"].notna()]
        work["代碼"] = work["代碼"].astype(str).str.strip()
        work = work[work["收盤價"].fillna(0) > 0]

        pool.extend(work.sort_values("成交金額", ascending=False).head(top_n_value)["代碼"].tolist())
        pool.extend(work.sort_values("成交股數", ascending=False).head(top_n_volume)["代碼"].tolist())

    pool.extend(CORE_TW_POOL)

    seen = set()
    final_pool = []
    for s in pool:
        code = to_tw_code(s)
        if code and code not in seen:
            final_pool.append(code)
            seen.add(code)
    return final_pool


def build_market_state(scan_df: pd.DataFrame) -> str:
    df = pd.DataFrame(scan_df)
    if df.empty:
        return "資料不足"

    scores = pd.to_numeric(df["評分"], errors="coerce").dropna()
    if scores.empty:
        return "資料不足"

    avg_score = scores.mean()
    strong_ratio = (scores >= 55).mean()

    if avg_score >= 45 and strong_ratio >= 0.25:
        return "強勢盤"
    elif avg_score >= 20:
        return "震盪盤"
    return "弱勢盤"


def recommend_qty(capital: float, weight: float, entry: Optional[float]) -> Tuple[float, int]:
    budget = capital * weight
    entry = safe_float(entry)
    if entry is None or entry <= 0:
        return budget, 0
    qty = int(budget // (entry * 1000))
    return budget, max(qty, 0)


def build_order_df(top_df: pd.DataFrame, capital: float, market_state: str) -> pd.DataFrame:
    rows = []
    weights = [0.4, 0.35, 0.25] if market_state == "強勢盤" else [0.35, 0.33, 0.32]

    for idx, (_, row) in enumerate(pd.DataFrame(top_df).iterrows()):
        weight = weights[idx] if idx < len(weights) else 0.2
        entry = safe_float(row.get("建議進場價"))
        budget, qty = recommend_qty(capital, weight, entry)

        open_low = round(entry * 0.995, 2) if entry else None
        open_high = round(entry * 1.005, 2) if entry else None
        stop = safe_float(row.get("停損價"))
        tp1 = safe_float(row.get("第一停利價"))

        single_profit = ""
        if qty > 0 and entry and tp1:
            single_profit = round((tp1 - entry) * qty * 1000, 0)

        rows.append({
            "代碼": clean_text(row.get("代碼")),
            "股名": clean_text(row.get("股名")),
            "族群": clean_text(row.get("族群")),
            "信心": clean_text(row.get("信心")),
            "評分": clean_text(row.get("評分")),
            "開盤可進場區": f"{open_low} ~ {open_high}" if open_low and open_high else "",
            "建議進場價": display_str(entry),
            "停損價": display_str(stop),
            "第一停利價": display_str(tp1),
            "建議資金": round(budget, 0),
            "建議張數": qty,
            "預估單筆收益": single_profit,
        })

    return as_object_df(pd.DataFrame(rows))


def build_weekly_summary(order_df: pd.DataFrame, capital: float) -> Dict[str, object]:
    if pd.DataFrame(order_df).empty:
        return {
            "預估週總收益": 0,
            "預估週收益率%": 0,
            "總建議投入": 0,
        }

    df = pd.DataFrame(order_df).copy()
    df["預估單筆收益_num"] = pd.to_numeric(df["預估單筆收益"], errors="coerce").fillna(0)
    df["建議資金_num"] = pd.to_numeric(df["建議資金"], errors="coerce").fillna(0)

    total_profit = df["預估單筆收益_num"].sum()
    total_budget = df["建議資金_num"].sum()
    weekly_pct = round((total_profit / capital) * 100, 2) if capital > 0 else 0

    return {
        "預估週總收益": round(total_profit, 0),
        "預估週收益率%": weekly_pct,
        "總建議投入": round(total_budget, 0),
    }


def run_auto_market_scan_v10_2(capital: float):
    candidate_pool = build_dynamic_tw_scan_pool()
    results = []

    for symbol in candidate_pool:
        row = calc_score(symbol, FIXED_STOP_LOSS_PCT, FIXED_TAKE_PROFIT_PCT)
        score = safe_float(row.get("評分"))
        if score is None or score < 25:
            continue
        results.append(row)

    scan_df = pd.DataFrame(results)
    if scan_df.empty:
        st.session_state["scan_df"] = pd.DataFrame()
        st.session_state["top3_df"] = pd.DataFrame()
        st.session_state["order_df"] = pd.DataFrame()
        st.session_state["weekly_summary"] = {}
        st.session_state["market_state"] = "資料不足"
        st.session_state["sector_df"] = pd.DataFrame()
        return

    sector_df = build_sector_rotation_df(scan_df)
    strength_map = get_sector_strength_map(scan_df)

    scan_df["族群強度加分"] = scan_df["族群"].apply(lambda x: round((strength_map.get(x, 0) - 30) / 5, 2) if strength_map.get(x, 0) else 0)
    scan_df["評分_num"] = pd.to_numeric(scan_df["評分"], errors="coerce").fillna(-999)
    scan_df["風險報酬比_num"] = pd.to_numeric(scan_df["風險報酬比"], errors="coerce").fillna(0)
    scan_df["最終排序"] = scan_df["評分_num"] + scan_df["族群強度加分"] + (scan_df["風險報酬比_num"] * 3)

    scan_df = scan_df.sort_values(["最終排序", "評分_num"], ascending=False).reset_index(drop=True)
    market_state = build_market_state(scan_df)
    top3_df = scan_df.head(FIXED_MAX_RECOMMEND).copy()

    order_df = build_order_df(top3_df, capital, market_state)
    weekly_summary = build_weekly_summary(order_df, capital)

    st.session_state["scan_df"] = as_object_df(scan_df)
    st.session_state["top3_df"] = as_object_df(top3_df)
    st.session_state["order_df"] = as_object_df(order_df)
    st.session_state["weekly_summary"] = weekly_summary
    st.session_state["market_state"] = market_state
    st.session_state["sector_df"] = as_object_df(sector_df)


# =========================================================
# 持倉 / 推播
# =========================================================
def ensure_position_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    for col in POSITION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    return as_object_df(out[POSITION_COLUMNS])


def positions_df() -> pd.DataFrame:
    rows = st.session_state.get("positions", [])
    if rows:
        return ensure_position_columns(pd.DataFrame(rows))
    return ensure_position_columns(pd.DataFrame())


def enrich_positions_auto(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_position_columns(df)
    if out.empty:
        return out

    for idx, row in out.iterrows():
        symbol = normalize_symbol(row.get("代碼", ""))
        if not symbol:
            continue

        info = get_yf_info(symbol)
        out.at[idx, "市場"] = "台股"
        out.at[idx, "代碼"] = to_tw_code(symbol)
        out.at[idx, "股名"] = clean_text(info.get("股名", symbol))
        out.at[idx, "目前價"] = display_str(info.get("目前價"))

        current_price = safe_float(info.get("目前價"))
        cost = safe_float(row.get("成本價"))
        stop = safe_float(row.get("停損價"))
        tp1 = safe_float(row.get("第一停利價"))

        if current_price is not None and cost and cost > 0:
            out.at[idx, "報酬率%"] = str(round(((current_price / cost) - 1) * 100, 2))
        else:
            out.at[idx, "報酬率%"] = ""

        status = "持有中"
        if current_price is None:
            status = "查無資料"
        elif stop is not None and current_price <= stop:
            status = "觸發停損"
        elif tp1 is not None and current_price >= tp1:
            status = "到達停利一"

        out.at[idx, "狀態"] = status

    return as_object_df(out)


def build_position_scan_df(pos_df: pd.DataFrame) -> pd.DataFrame:
    pos_df = ensure_position_columns(pos_df)
    if pos_df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in pos_df.iterrows():
        symbol = normalize_symbol(row.get("代碼", ""))
        if not symbol:
            continue

        health = calc_score(symbol, FIXED_STOP_LOSS_PCT, FIXED_TAKE_PROFIT_PCT)
        rows.append({
            "代碼": health["代碼"],
            "股名": health["股名"],
            "收盤": health["收盤"],
            "訊號": health["訊號"],
            "建議進場價": health["建議進場價"],
            "停損價": health["停損價"],
            "第一停利價": health["第一停利價"],
            "評分": health["評分"],
            "理由": health["理由"],
        })

    return as_object_df(pd.DataFrame(rows).sort_values(["評分"], ascending=False).reset_index(drop=True))


def line_enabled() -> bool:
    return "line_channel_access_token" in st.secrets and "line_to" in st.secrets


def send_line(text: str) -> Tuple[bool, str]:
    if not line_enabled():
        return False, "尚未設定 line_channel_access_token / line_to"

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {st.secrets['line_channel_access_token']}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": st.secrets["line_to"],
        "messages": [{"type": "text", "text": text[:5000]}],
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if 200 <= r.status_code < 300:
            return True, "LINE 推播成功"
        return False, f"推播失敗：HTTP {r.status_code}"
    except Exception as e:
        return False, f"推播失敗：{e}"


def build_priority_alerts(top3_df: pd.DataFrame, weekly_summary: Dict[str, object]) -> str:
    lines = [f"上帝視角 V10.2 推薦 {now_str()}"]
    if pd.DataFrame(top3_df).empty:
        lines.append("目前尚無推薦標的。")
        return "\n".join(lines)

    for _, row in pd.DataFrame(top3_df).iterrows():
        lines.append(
            f"{clean_text(row.get('代碼'))} {clean_text(row.get('股名'))}｜"
            f"{clean_text(row.get('訊號'))}｜進場 {clean_text(row.get('建議進場價'))}｜"
            f"停損 {clean_text(row.get('停損價'))}｜停利 {clean_text(row.get('第一停利價'))}"
        )

    lines.append(
        f"預估週總收益：{weekly_summary.get('預估週總收益', 0)} / "
        f"預估週收益率：{weekly_summary.get('預估週收益率%', 0)}%"
    )
    return "\n".join(lines)


def auto_refresh_script(seconds: int):
    ms = max(int(seconds), 10) * 1000
    components.html(
        f"""
        <script>
            setTimeout(function() {{
                window.parent.location.reload();
            }}, {ms});
        </script>
        """,
        height=0,
    )


# =========================================================
# Session 初始化
# =========================================================
def init_state():
    st.session_state.setdefault("scan_df", pd.DataFrame())
    st.session_state.setdefault("top3_df", pd.DataFrame())
    st.session_state.setdefault("order_df", pd.DataFrame())
    st.session_state.setdefault("weekly_summary", {})
    st.session_state.setdefault("positions", [])
    st.session_state.setdefault("position_scan_df", pd.DataFrame())
    st.session_state.setdefault("market_state", "資料不足")
    st.session_state.setdefault("sector_df", pd.DataFrame())
    st.session_state.setdefault("auto_refresh", False)


init_state()

# =========================================================
# Sidebar：只保留總資金
# =========================================================
st.sidebar.title("📊 上帝視角 V10.2 設定")
capital = st.sidebar.number_input("總資金", min_value=10000, value=DEFAULT_CAPITAL, step=10000)

# =========================================================
# Header
# =========================================================
st.markdown(
    """
    <div class="hero-card">
        <div class="title-xl">🌙 上帝視角 V10.2 簡化實戰版</div>
        <div class="muted">側欄只保留總資金，系統自動依資金推薦三檔、開盤進場區、下單張數與預估週收益</div>
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("總資金", f"{capital:,.0f}")
m2.metric("固定停損", f"{int(FIXED_STOP_LOSS_PCT * 100)}%")
m3.metric("第一停利", f"{int(FIXED_TAKE_PROFIT_PCT * 100)}%")
m4.metric("推薦檔數", f"{FIXED_MAX_RECOMMEND} 檔")

i1, i2, i3 = st.columns(3)
with i1:
    st.markdown(f'<div class="soft-box"><b>最後刷新時間</b><br>{now_str()}</div>', unsafe_allow_html=True)
with i2:
    st.markdown(f'<div class="soft-box"><b>模式</b><br>開盤進出場試算</div>', unsafe_allow_html=True)
with i3:
    st.markdown(f'<div class="soft-box"><b>盤面狀態</b><br>{st.session_state.get("market_state", "資料不足")}</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="top-btn">', unsafe_allow_html=True)
    if st.button("🚀 依總資金重新推薦本週標的", use_container_width=True):
        run_auto_market_scan_v10_2(capital)
    st.markdown("</div>", unsafe_allow_html=True)

if st.session_state["top3_df"].empty:
    run_auto_market_scan_v10_2(capital)

scan_df = as_object_df(st.session_state["scan_df"])
top3_df = as_object_df(st.session_state["top3_df"])
order_df = as_object_df(st.session_state["order_df"])
sector_df = as_object_df(st.session_state["sector_df"])
weekly_summary = st.session_state["weekly_summary"]

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 本週推薦三檔",
    "📋 下單表",
    "💼 持股追蹤",
    "📲 推播"
])

with tab1:
    st.subheader("本週推薦三檔")

    if not sector_df.empty:
        st.markdown("**族群輪動排行**")
        st.dataframe(sector_df, use_container_width=True, hide_index=True)

    if top3_df.empty:
        st.info("尚無推薦結果。")
    else:
        cols = st.columns(min(3, len(top3_df)))
        for i, (_, row) in enumerate(top3_df.iterrows()):
            color = get_confidence_color(row.get("評分"))
            with cols[i]:
                st.markdown(
                    f"""
                    <div class="signal-card">
                        <div class="title-xl">{clean_text(row.get("代碼"))}｜{clean_text(row.get("股名"))}</div>
                        <div class="muted">{clean_text(row.get("族群"))}｜{clean_text(row.get("等級"))}</div>
                        <div style="margin-top:10px;">
                            <span class="badge" style="background:{color};color:white;">信心 {clean_text(row.get("信心"))}</span>
                            <span class="badge" style="background:#1e293b;color:#93c5fd;">{clean_text(row.get("訊號"))}</span>
                            <span class="badge" style="background:#111827;color:#cbd5e1;">評分 {clean_text(row.get("評分"))}</span>
                        </div>
                        <div class="kpi">進場：{clean_text(row.get("建議進場價")) or "-"}</div>
                        <div>停損：{clean_text(row.get("停損價")) or "-"}</div>
                        <div>停利：{clean_text(row.get("第一停利價")) or "-"}</div>
                        <div>風報比：{clean_text(row.get("風險報酬比")) or "-"}</div>
                        <div style="margin-top:8px;">理由：{clean_text(row.get("理由"))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("### 完整市場掃描排行")
        st.dataframe(scan_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("依總資金自動換算下單表")
    if order_df.empty:
        st.info("尚無下單表。")
    else:
        st.dataframe(order_df, use_container_width=True, hide_index=True)

        s1, s2, s3 = st.columns(3)
        s1.metric("總建議投入", f"{weekly_summary.get('總建議投入', 0):,.0f}")
        s2.metric("預估週總收益", f"{weekly_summary.get('預估週總收益', 0):,.0f}")
        s3.metric("預估週收益率%", f"{weekly_summary.get('預估週收益率%', 0)}%")

        st.download_button(
            "⬇️ 下載下單表 CSV",
            order_df.to_csv(index=False).encode("utf-8-sig"),
            "god_view_v10_2_orders.csv",
            "text/csv"
        )

with tab3:
    st.subheader("持股追蹤")
    pos_df = positions_df()
    edited_pos = st.data_editor(
        pos_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="positions_editor"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("⚡ 自動補齊持股資訊", use_container_width=True):
            safe_df = ensure_position_columns(pd.DataFrame(edited_pos))
            safe_df = enrich_positions_auto(safe_df)
            st.session_state["positions"] = safe_df.fillna("").to_dict("records")
            st.success("持股資訊已補齊")
            st.rerun()

    with c2:
        if st.button("📡 掃描目前持股", use_container_width=True):
            safe_df = ensure_position_columns(pd.DataFrame(edited_pos))
            safe_df = enrich_positions_auto(safe_df)
            st.session_state["positions"] = safe_df.fillna("").to_dict("records")
            st.session_state["position_scan_df"] = build_position_scan_df(safe_df)
            st.success("持股掃描完成")
            st.rerun()

    latest_positions = positions_df()
    if not latest_positions.empty:
        st.dataframe(latest_positions, use_container_width=True, hide_index=True)

    position_scan_df = st.session_state.get("position_scan_df", pd.DataFrame())
    if not position_scan_df.empty:
        st.markdown("### 持股即時掃描")
        st.dataframe(position_scan_df, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("LINE 推播")
    line_text = build_priority_alerts(top3_df, weekly_summary)
    st.code(line_text)

    if st.button("📲 發送本週推薦到 LINE", use_container_width=True):
        ok, msg = send_line(line_text)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

st.markdown("---")
st.caption("上帝視角 V10.2 簡化實戰版｜側欄僅保留總資金，系統自動換算開盤進出場與下單張數")
