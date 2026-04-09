from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import io
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

st.set_page_config(page_title="上帝視角 V10", page_icon="📈", layout="wide")

DEFAULT_CAPITAL = 200000
DEFAULT_MAX_POSITIONS = 2
DEFAULT_SINGLE_POSITION_PCT = 0.30
DEFAULT_STOP_LOSS_PCT = 0.05
DEFAULT_TAKE_PROFIT_PCT = 0.10
DEFAULT_DAILY_LOSS_STOP_PCT = 0.05
DEFAULT_REFRESH_SECONDS = 60

TWSE_STOCK_DAY_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_BWIBBU_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"

POSITION_COLUMNS = [
    "市場", "代碼", "股名", "持有數量", "成本價", "目前價", "報酬率%",
    "停損價", "第一停利價", "狀態", "本益比", "殖利率%", "股價淨值比"
]

TRADE_LOG_COLUMNS = ["日期", "市場", "代碼", "動作", "價格", "數量", "備註"]

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


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_symbol(symbol: str) -> str:
    if symbol is None:
        return ""
    return str(symbol).strip().upper()


def parse_symbols(raw: str) -> List[str]:
    if not raw:
        return []
    items = []
    for x in raw.replace("\n", ",").split(","):
        s = normalize_symbol(x)
        if s:
            items.append(s)

    seen = set()
    out = []
    for s in items:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def is_tw_stock(symbol: str) -> bool:
    symbol = normalize_symbol(symbol)
    return symbol.isdigit() or symbol.endswith(".TW")


def infer_market(symbol: str, market: str = "") -> str:
    market = str(market).strip()
    if market in ["台股", "美股"]:
        return market
    return "台股" if is_tw_stock(symbol) else "美股"


def to_tw_code(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    if symbol.endswith(".TW"):
        return symbol[:-3]
    return symbol


def to_yf_symbol(symbol: str, market: str = "") -> str:
    symbol = normalize_symbol(symbol)
    market = infer_market(symbol, market)
    if not symbol:
        return ""
    if market == "台股":
        return symbol if symbol.endswith(".TW") else f"{to_tw_code(symbol)}.TW"
    return symbol


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


def as_object_df(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    for col in out.columns:
        out[col] = out[col].astype("object")
    return out


def ymd_str(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


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
# 深色專業交易介面 CSS
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
        min-height: 270px;
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
        font-size: 1.2rem;
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

    .stSelectbox [data-baseweb="select"] > div {
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
# 資料源
# =========================================================
@st.cache_data(ttl=120)
def fetch_twse_stock_day_all() -> pd.DataFrame:
    try:
        r = requests.get(TWSE_STOCK_DAY_ALL_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data)
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

        if "代碼" in df.columns:
            df["代碼"] = df["代碼"].astype(str).str.strip()

        for col in ["成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"]:
            if col in df.columns:
                df[col] = df[col].apply(safe_float)

        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def fetch_twse_bwibbu_all() -> pd.DataFrame:
    try:
        r = requests.get(TWSE_BWIBBU_ALL_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame()

        rename_map = {
            "Code": "代碼",
            "Name": "股名",
            "PEratio": "本益比",
            "DividendYield": "殖利率%",
            "PBratio": "股價淨值比",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        if "代碼" in df.columns:
            df["代碼"] = df["代碼"].astype(str).str.strip()

        for col in ["本益比", "殖利率%", "股價淨值比"]:
            if col in df.columns:
                df[col] = df[col].apply(safe_float)

        return df
    except Exception:
        return pd.DataFrame()


def get_twse_day_row(code: str) -> Optional[dict]:
    df = fetch_twse_stock_day_all()
    if df.empty or "代碼" not in df.columns:
        return None
    match = df[df["代碼"] == code]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def get_twse_bw_row(code: str) -> Optional[dict]:
    df = fetch_twse_bwibbu_all()
    if df.empty or "代碼" not in df.columns:
        return None
    match = df[df["代碼"] == code]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


@st.cache_data(ttl=180)
def get_yf_info(symbol: str, market: str = "") -> Dict[str, object]:
    yf_symbol = to_yf_symbol(symbol, market)
    result = {
        "股名": normalize_symbol(symbol),
        "目前價": None,
        "開盤價": None,
        "最高價": None,
        "最低價": None,
        "成交股數": None,
        "本益比": None,
        "殖利率%": None,
        "股價淨值比": None,
    }

    try:
        t = yf.Ticker(yf_symbol)
        hist = t.history(period="5d")
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            result["目前價"] = safe_float(last.get("Close"))
            result["開盤價"] = safe_float(last.get("Open"))
            result["最高價"] = safe_float(last.get("High"))
            result["最低價"] = safe_float(last.get("Low"))
            result["成交股數"] = safe_float(last.get("Volume"))

        info = t.info if hasattr(t, "info") else {}
        result["股名"] = info.get("shortName") or info.get("longName") or result["股名"]
        result["本益比"] = safe_float(info.get("trailingPE"))
        result["殖利率%"] = round(float(info.get("dividendYield", 0)) * 100, 2) if info.get("dividendYield") is not None else None
        result["股價淨值比"] = safe_float(info.get("priceToBook"))
    except Exception:
        pass

    return result


def _find_recent_trade_dates(days_back: int = 10) -> List[datetime]:
    today = datetime.now()
    return [today - timedelta(days=i) for i in range(days_back)]


@st.cache_data(ttl=1800)
def fetch_twse_t86_recent() -> pd.DataFrame:
    for dt in _find_recent_trade_dates(10):
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={ymd_str(dt)}&selectType=ALLBUT0999&response=html"
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            tables = pd.read_html(io.StringIO(resp.text))
            if not tables:
                continue

            chosen = None
            for tb in tables:
                cols = [str(c) for c in tb.columns]
                cols_text = "|".join(cols)
                if ("代號" in cols_text or "證券代號" in cols_text) and ("外資" in cols_text or "投信" in cols_text or "自營商" in cols_text):
                    chosen = tb
                    break

            if chosen is None or chosen.empty:
                continue

            df = chosen.copy()
            df.columns = [str(c).replace("\n", "").strip() for c in df.columns]

            rename_map = {}
            for c in df.columns:
                if "代號" in c:
                    rename_map[c] = "代碼"
                elif "名稱" in c:
                    rename_map[c] = "股名"
                elif "外資" in c and "買賣超" in c:
                    rename_map[c] = "外資買賣超"
                elif "投信" in c and "買賣超" in c:
                    rename_map[c] = "投信買賣超"
                elif "自營商" in c and "買賣超" in c:
                    rename_map[c] = "自營商買賣超"
                elif "三大法人買賣超股數" in c or "三大法人買賣超" in c:
                    rename_map[c] = "三大法人合計"

            df = df.rename(columns=rename_map)

            if "代碼" not in df.columns:
                continue

            for need in ["股名", "外資買賣超", "投信買賣超", "自營商買賣超", "三大法人合計"]:
                if need not in df.columns:
                    df[need] = None

            df["代碼"] = df["代碼"].astype(str).str.strip()
            for col in ["外資買賣超", "投信買賣超", "自營商買賣超", "三大法人合計"]:
                df[col] = df[col].apply(safe_float)

            df["資料日期"] = dt.strftime("%Y-%m-%d")
            return df[["資料日期", "代碼", "股名", "外資買賣超", "投信買賣超", "自營商買賣超", "三大法人合計"]]
        except Exception:
            continue

    return pd.DataFrame(columns=["資料日期", "代碼", "股名", "外資買賣超", "投信買賣超", "自營商買賣超", "三大法人合計"])


def get_chip_row(symbol: str) -> Dict[str, object]:
    code = to_tw_code(symbol)
    t86 = fetch_twse_t86_recent()
    result = {
        "資料日期": "",
        "外資買賣超": None,
        "投信買賣超": None,
        "自營商買賣超": None,
        "三大法人合計": None,
    }
    if t86.empty:
        return result

    match = t86[t86["代碼"] == code]
    if match.empty:
        return result

    row = match.iloc[0]
    result["資料日期"] = clean_text(row.get("資料日期", ""))
    result["外資買賣超"] = safe_float(row.get("外資買賣超"))
    result["投信買賣超"] = safe_float(row.get("投信買賣超"))
    result["自營商買賣超"] = safe_float(row.get("自營商買賣超"))
    result["三大法人合計"] = safe_float(row.get("三大法人合計"))
    return result


@st.cache_data(ttl=120)
def get_stock_info(symbol: str, market: str = "") -> Dict[str, object]:
    symbol = normalize_symbol(symbol)
    market = infer_market(symbol, market)

    if market == "台股":
        code = to_tw_code(symbol)
        twse_day = get_twse_day_row(code)
        twse_bw = get_twse_bw_row(code)
        yf_info = get_yf_info(code, "台股")
        chip = get_chip_row(code)

        result = {
            "代碼": code,
            "股名": code,
            "目前價": None,
            "開盤價": None,
            "最高價": None,
            "最低價": None,
            "成交股數": None,
            "本益比": None,
            "殖利率%": None,
            "股價淨值比": None,
            "外資買賣超": chip.get("外資買賣超"),
            "投信買賣超": chip.get("投信買賣超"),
            "自營商買賣超": chip.get("自營商買賣超"),
            "三大法人合計": chip.get("三大法人合計"),
        }

        if twse_day:
            result["股名"] = twse_day.get("股名", code) or code
            result["目前價"] = twse_day.get("收盤價", None)
            result["開盤價"] = twse_day.get("開盤價", None)
            result["最高價"] = twse_day.get("最高價", None)
            result["最低價"] = twse_day.get("最低價", None)
            result["成交股數"] = twse_day.get("成交股數", None)

        if twse_bw:
            result["股名"] = twse_bw.get("股名", result["股名"]) or result["股名"]
            result["本益比"] = twse_bw.get("本益比", None)
            result["殖利率%"] = twse_bw.get("殖利率%", None)
            result["股價淨值比"] = twse_bw.get("股價淨值比", None)

        for k in ["股名", "目前價", "開盤價", "最高價", "最低價", "成交股數", "本益比", "殖利率%", "股價淨值比"]:
            if result.get(k) in [None, "", code]:
                result[k] = yf_info.get(k)

        return result

    us_info = get_yf_info(symbol, "美股")
    return {
        "代碼": symbol,
        "股名": us_info.get("股名", symbol),
        "目前價": us_info.get("目前價"),
        "開盤價": us_info.get("開盤價"),
        "最高價": us_info.get("最高價"),
        "最低價": us_info.get("最低價"),
        "成交股數": us_info.get("成交股數"),
        "本益比": us_info.get("本益比"),
        "殖利率%": us_info.get("殖利率%"),
        "股價淨值比": us_info.get("股價淨值比"),
        "外資買賣超": None,
        "投信買賣超": None,
        "自營商買賣超": None,
        "三大法人合計": None,
    }


@st.cache_data(ttl=180)
def fetch_price_history(symbol: str, period: str = "6mo", market: str = "") -> pd.DataFrame:
    market = infer_market(symbol, market)
    yf_symbol = to_yf_symbol(symbol, market)
    if not yf_symbol:
        return pd.DataFrame()

    try:
        df = yf.download(yf_symbol, period=period, interval="1d", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        keep = [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in df.columns]
        df = df[keep].copy()
        if "Close" not in df.columns:
            return pd.DataFrame()

        df["MA5"] = df["Close"].rolling(5).mean()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA60"] = df["Close"].rolling(60).mean()
        df["VOL20"] = df["Volume"].rolling(20).mean() if "Volume" in df.columns else 0
        df["RSI14"] = rsi(df["Close"], 14)
        df["Prev20High"] = df["High"].rolling(20).max().shift(1)
        df["Prev20Low"] = df["Low"].rolling(20).min().shift(1)
        df["Ret1D%"] = df["Close"].pct_change() * 100
        df["Ret5D%"] = df["Close"].pct_change(5) * 100
        df["VolumeRatio"] = df["Volume"] / df["VOL20"].replace(0, pd.NA)
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()


def calc_chip_health(symbol: str, market: str, stop_loss_pct: float, take_profit_pct: float) -> Dict[str, object]:
    market = infer_market(symbol, market)
    info = get_stock_info(symbol, market)
    df = fetch_price_history(symbol, period="6mo", market=market)

    if df.empty or len(df) < 65:
        return {
            "市場": market,
            "代碼": to_tw_code(symbol) if market == "台股" else normalize_symbol(symbol),
            "股名": clean_text(info.get("股名", symbol)),
            "綜合評分": -999,
            "等級": "資料不足",
            "建議": "資料不足",
            "目前價": display_str(info.get("目前價")),
            "停損價": "",
            "第一停利價": "",
            "異常事件": "資料不足",
            "流動性加分": 0,
            "事件加分": 0,
            "均線分數": 0,
            "RSI": "",
        }

    last = df.iloc[-1]
    close = safe_float(last.get("Close"))
    ma5 = safe_float(last.get("MA5"))
    ma20 = safe_float(last.get("MA20"))
    ma60 = safe_float(last.get("MA60"))
    rsi14 = safe_float(last.get("RSI14"))
    vol_ratio = safe_float(last.get("VolumeRatio"))
    ret1d = safe_float(last.get("Ret1D%"))
    ret5d = safe_float(last.get("Ret5D%"))
    prev20h = safe_float(last.get("Prev20High"))
    prev20l = safe_float(last.get("Prev20Low"))

    foreign = safe_float(info.get("外資買賣超"))
    trust = safe_float(info.get("投信買賣超"))
    dealer = safe_float(info.get("自營商買賣超"))

    foreign_score = 15 if foreign and foreign > 0 else (-10 if foreign and foreign < 0 else 0)
    trust_score = 15 if trust and trust > 0 else (-10 if trust and trust < 0 else 0)
    dealer_score = 10 if dealer and dealer > 0 else (-5 if dealer and dealer < 0 else 0)

    chip_total = 0
    for v in [foreign, trust, dealer]:
        if v:
            chip_total += v
    major_proxy_score = 20 if chip_total > 0 else (-15 if chip_total < 0 else 0)

    ma_score = 0
    if close and ma5 and ma20 and ma60:
        if close > ma5 > ma20 > ma60:
            ma_score = 30
        elif close > ma5 > ma60:
            ma_score = 20
        elif close < ma60:
            ma_score = -20

    rsi_score = 0
    if rsi14 is not None:
        if 55 <= rsi14 <= 75:
            rsi_score = 15
        elif rsi14 < 40:
            rsi_score = -10
        elif rsi14 > 80:
            rsi_score = -5

    volume_price_score = 0
    anomaly_tags = []
    event_bonus = 0

    if vol_ratio and vol_ratio >= 1.8:
        volume_price_score += 15
        event_bonus += 8
        anomaly_tags.append("放量")
    if close and prev20h and close > prev20h:
        volume_price_score += 15
        event_bonus += 10
        anomaly_tags.append("突破")
    if close and prev20l and close < prev20l:
        volume_price_score -= 15
        anomaly_tags.append("跌破")
    if ret1d and ret1d >= 4:
        event_bonus += 5
        anomaly_tags.append("急拉")
    if ret1d and ret1d <= -4:
        anomaly_tags.append("急殺")

    liquidity_bonus = 0
    if vol_ratio and vol_ratio >= 1.2:
        liquidity_bonus += 5
    if ret5d and ret5d > 0:
        liquidity_bonus += 5

    score = foreign_score + trust_score + dealer_score + major_proxy_score + ma_score + rsi_score + volume_price_score + liquidity_bonus + event_bonus

    if score >= 60:
        grade = "強勢"
        advice = "偏多續抱 / 可列入首選"
    elif score >= 30:
        grade = "觀察"
        advice = "續追蹤 / 等待更佳進場"
    else:
        grade = "危險"
        advice = "保守 / 嚴設停損"

    stop_price = round(close * (1 - stop_loss_pct), 2) if close else None
    tp1 = round(close * (1 + take_profit_pct), 2) if close else None

    return {
        "市場": market,
        "代碼": to_tw_code(symbol) if market == "台股" else normalize_symbol(symbol),
        "股名": clean_text(info.get("股名", symbol)),
        "綜合評分": int(score),
        "等級": grade,
        "建議": advice,
        "目前價": display_str(close or info.get("目前價")),
        "停損價": display_str(stop_price),
        "第一停利價": display_str(tp1),
        "異常事件": " / ".join(anomaly_tags) if anomaly_tags else "",
        "流動性加分": liquidity_bonus,
        "事件加分": event_bonus,
        "均線分數": ma_score,
        "RSI": display_str(rsi14),
    }


def build_search_df(symbols: List[str], market_hint: str, stop_loss_pct: float, take_profit_pct: float) -> pd.DataFrame:
    rows = []
    for s in symbols:
        rows.append(calc_chip_health(s, market_hint, stop_loss_pct, take_profit_pct))
    if not rows:
        return pd.DataFrame()
    return as_object_df(pd.DataFrame(rows).sort_values(["綜合評分"], ascending=False).reset_index(drop=True))


def build_sector_rotation_df(scan_df: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(scan_df).copy()
    if df.empty:
        return pd.DataFrame(columns=["族群", "平均評分", "強勢檔數", "樣本數"])

    df["族群"] = df["代碼"].apply(get_sector_for_symbol)
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

        if "成交金額" in work.columns:
            pool.extend(work.sort_values("成交金額", ascending=False).head(top_n_value)["代碼"].tolist())

        if "成交股數" in work.columns:
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


def build_scan_row(symbol: str, market: str, stop_loss_pct: float, take_profit_pct: float) -> Dict[str, object]:
    health = calc_chip_health(symbol, market, stop_loss_pct, take_profit_pct)

    signal = "觀察"
    if health["等級"] == "強勢":
        signal = "候選進攻"
    elif health["等級"] == "危險":
        signal = "保守"

    current_price = safe_float(health["目前價"])
    stop_price = safe_float(health["停損價"])
    tp1 = safe_float(health["第一停利價"])

    rr = ""
    if current_price and stop_price and tp1 and current_price > stop_price:
        risk = current_price - stop_price
        reward = tp1 - current_price
        if risk > 0:
            rr = round(reward / risk, 2)

    return {
        "市場": health["市場"],
        "代碼": health["代碼"],
        "股名": health["股名"],
        "族群": get_sector_for_symbol(health["代碼"]),
        "收盤": health["目前價"],
        "訊號": signal,
        "建議進場價": health["目前價"] if signal != "保守" else "",
        "停損價": health["停損價"],
        "第一停利價": health["第一停利價"],
        "風險報酬比": rr,
        "評分": health["綜合評分"],
        "信心": get_confidence_label(health["綜合評分"]),
        "等級": health["等級"],
        "理由": health["建議"],
        "異常事件": health["異常事件"],
        "流動性加分": health["流動性加分"],
        "事件加分": health["事件加分"],
    }


def recommend_qty(capital: float, alloc_pct: float, entry: Optional[float], market: str) -> Tuple[float, int]:
    budget = capital * alloc_pct
    entry = safe_float(entry)
    market = infer_market("", market)

    if entry is None or entry <= 0:
        return budget, 0

    if market == "台股":
        qty = int(budget // (entry * 1000))
        return budget, max(qty, 0)

    qty = int(budget // entry)
    return budget, max(qty, 0)


def make_order_df(top_df: pd.DataFrame, capital: float, alloc_pct: float, market_state: str = "震盪盤") -> pd.DataFrame:
    rows = []
    for idx, (_, row) in enumerate(pd.DataFrame(top_df).iterrows(), start=1):
        market = infer_market(row.get("代碼", ""), row.get("市場", ""))
        entry_price = safe_float(row.get("建議進場價"))

        pos_pct = alloc_pct
        mode = "標準"

        if market_state == "強勢盤":
            if idx == 1:
                pos_pct = min(alloc_pct, 0.35)
                mode = "積極"
            elif idx == 2:
                pos_pct = min(alloc_pct, 0.30)
                mode = "標準"
            else:
                pos_pct = min(alloc_pct, 0.25)
                mode = "保守"
        elif market_state == "震盪盤":
            if idx == 1:
                pos_pct = min(alloc_pct, 0.25)
            elif idx == 2:
                pos_pct = min(alloc_pct, 0.20)
                mode = "保守"
            else:
                pos_pct = min(alloc_pct, 0.15)
                mode = "保守"
        else:
            pos_pct = min(alloc_pct, 0.12)
            mode = "保守"

        budget, qty = recommend_qty(capital, pos_pct, entry_price, market)

        rows.append({
            "市場": market,
            "代碼": clean_text(row.get("代碼", "")),
            "股名": clean_text(row.get("股名", row.get("代碼", ""))),
            "族群": clean_text(row.get("族群", "")),
            "信心": clean_text(row.get("信心", "")),
            "等級": clean_text(row.get("等級", "")),
            "訊號": clean_text(row.get("訊號", "")),
            "委託類型": "現股/限價" if market == "台股" else "複委託/限價",
            "建議進場價": clean_text(row.get("建議進場價", "")),
            "停損價": clean_text(row.get("停損價", "")),
            "第一停利價": clean_text(row.get("第一停利價", "")),
            "風險報酬比": clean_text(row.get("風險報酬比", "")),
            "建議倉位%": f"{round(pos_pct * 100, 1)}%",
            "建議模式": mode,
            "配置金額": str(round(budget, 2)),
            "建議數量": f"{qty} 張" if market == "台股" else f"{qty} 股",
            "異常事件": clean_text(row.get("異常事件", "")),
        })
    return as_object_df(pd.DataFrame(rows))


def run_auto_market_scan_v9(stop_loss_pct: float, take_profit_pct: float, capital: float, alloc_pct: float):
    candidate_pool = build_dynamic_tw_scan_pool()
    raw_results = []
    df_map = {}

    for symbol in candidate_pool:
        health = calc_chip_health(symbol, "台股", stop_loss_pct, take_profit_pct)

        rsi_val = safe_float(health["RSI"])
        ma_score = safe_float(health["均線分數"])
        score = safe_float(health["綜合評分"])
        current_price = safe_float(health["目前價"])

        if current_price is None:
            continue
        if rsi_val is None or rsi_val < 50:
            continue
        if ma_score is not None and ma_score < 0:
            continue
        if score is not None and score < 25:
            continue

        row = build_scan_row(symbol, "台股", stop_loss_pct, take_profit_pct)
        raw_results.append(row)
        df_map[to_tw_code(symbol)] = fetch_price_history(symbol, period="6mo", market="台股")

    scan_df = pd.DataFrame(raw_results)
    if scan_df.empty:
        st.session_state["scan_df"] = pd.DataFrame()
        st.session_state["top3_df"] = pd.DataFrame()
        st.session_state["order_df"] = pd.DataFrame()
        st.session_state["df_map"] = {}
        st.session_state["market_state"] = "資料不足"
        st.session_state["sector_df"] = pd.DataFrame()
        return

    sector_df = build_sector_rotation_df(scan_df)
    strength_map = get_sector_strength_map(scan_df)
    scan_df["族群強度加分"] = scan_df["族群"].apply(lambda x: round((strength_map.get(x, 0) - 30) / 5, 2) if strength_map.get(x, 0) else 0)

    scan_df["評分_num"] = pd.to_numeric(scan_df["評分"], errors="coerce").fillna(-999)
    scan_df["事件加分_num"] = pd.to_numeric(scan_df["事件加分"], errors="coerce").fillna(0)
    scan_df["流動性加分_num"] = pd.to_numeric(scan_df["流動性加分"], errors="coerce").fillna(0)
    scan_df["風險報酬比_num"] = pd.to_numeric(scan_df["風險報酬比"], errors="coerce").fillna(0)
    scan_df["族群強度加分_num"] = pd.to_numeric(scan_df["族群強度加分"], errors="coerce").fillna(0)

    scan_df["最終排序"] = (
        scan_df["評分_num"]
        + scan_df["事件加分_num"]
        + scan_df["流動性加分_num"]
        + scan_df["族群強度加分_num"]
        + (scan_df["風險報酬比_num"] * 3)
    )

    scan_df = scan_df.sort_values(["最終排序", "評分_num"], ascending=False).drop(
        columns=["評分_num", "事件加分_num", "流動性加分_num", "風險報酬比_num", "族群強度加分_num"]
    ).reset_index(drop=True)

    market_state = build_market_state(scan_df)

    if market_state == "強勢盤":
        top3_df = scan_df.head(3).copy()
    elif market_state == "震盪盤":
        top3_df = scan_df[pd.to_numeric(scan_df["評分"], errors="coerce") >= 45].head(3).copy()
    else:
        top3_df = scan_df[pd.to_numeric(scan_df["評分"], errors="coerce") >= 60].head(2).copy()

    order_df = make_order_df(top3_df, capital, alloc_pct, market_state) if not top3_df.empty else pd.DataFrame()

    st.session_state["scan_df"] = as_object_df(scan_df)
    st.session_state["top3_df"] = as_object_df(top3_df)
    st.session_state["order_df"] = as_object_df(order_df)
    st.session_state["df_map"] = df_map
    st.session_state["market_state"] = market_state
    st.session_state["sector_df"] = as_object_df(sector_df)


def ensure_position_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    for col in POSITION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[POSITION_COLUMNS]
    return as_object_df(out)


def enrich_positions_auto(df: pd.DataFrame) -> pd.DataFrame:
    out = ensure_position_columns(df)
    if out.empty:
        return out

    for idx, row in out.iterrows():
        symbol = normalize_symbol(row.get("代碼", ""))
        market = infer_market(symbol, row.get("市場", ""))
        if not symbol:
            continue

        info = get_stock_info(symbol, market)

        out.at[idx, "市場"] = market
        out.at[idx, "代碼"] = to_tw_code(symbol) if market == "台股" else symbol
        out.at[idx, "股名"] = clean_text(info.get("股名", symbol))
        out.at[idx, "目前價"] = display_str(info.get("目前價"))
        out.at[idx, "本益比"] = display_str(info.get("本益比"))
        out.at[idx, "殖利率%"] = display_str(info.get("殖利率%"))
        out.at[idx, "股價淨值比"] = display_str(info.get("股價淨值比"))

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


def build_position_scan_df(pos_df: pd.DataFrame, stop_loss_pct: float, take_profit_pct: float) -> pd.DataFrame:
    pos_df = ensure_position_columns(pos_df)
    if pos_df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in pos_df.iterrows():
        symbol = normalize_symbol(row.get("代碼", ""))
        market = infer_market(symbol, row.get("市場", ""))
        if not symbol:
            continue

        health = calc_chip_health(symbol, market, stop_loss_pct, take_profit_pct)

        rows.append({
            "市場": health["市場"],
            "代碼": health["代碼"],
            "股名": health["股名"],
            "收盤": health["目前價"],
            "訊號": health["等級"],
            "建議進場價": health["目前價"] if health["等級"] == "強勢" else "",
            "停損價": health["停損價"],
            "第一停利價": health["第一停利價"],
            "評分": health["綜合評分"],
            "理由": health["建議"],
            "異常事件": health["異常事件"],
        })

    if not rows:
        return pd.DataFrame()
    return as_object_df(pd.DataFrame(rows).sort_values(["評分"], ascending=False).reset_index(drop=True))


def build_daily_report_df(positions_df: pd.DataFrame, search_symbols: List[str], stop_loss_pct: float, take_profit_pct: float) -> pd.DataFrame:
    rows = []

    if not positions_df.empty:
        for _, row in positions_df.iterrows():
            symbol = normalize_symbol(row.get("代碼", ""))
            market = infer_market(symbol, row.get("市場", ""))
            if not symbol:
                continue
            health = calc_chip_health(symbol, market, stop_loss_pct, take_profit_pct)
            rows.append({
                "類別": "持股",
                "市場": market,
                "代碼": health["代碼"],
                "股名": health["股名"],
                "目前價": health["目前價"],
                "等級": health["等級"],
                "綜合評分": health["綜合評分"],
                "異常事件": health["異常事件"],
                "建議": health["建議"],
            })

    for s in search_symbols:
        market = infer_market(s, "")
        health = calc_chip_health(s, market, stop_loss_pct, take_profit_pct)
        rows.append({
            "類別": "搜尋觀察",
            "市場": market,
            "代碼": health["代碼"],
            "股名": health["股名"],
            "目前價": health["目前價"],
            "等級": health["等級"],
            "綜合評分": health["綜合評分"],
            "異常事件": health["異常事件"],
            "建議": health["建議"],
        })

    if not rows:
        return pd.DataFrame()
    return as_object_df(pd.DataFrame(rows).sort_values(["綜合評分"], ascending=False).reset_index(drop=True))


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
        return False, f"推播失敗：HTTP {r.status_code} / {r.text[:180]}"
    except Exception as e:
        return False, f"推播失敗：{e}"


def build_priority_alerts(scan_df: pd.DataFrame, position_scan_df: pd.DataFrame) -> str:
    lines = [f"上帝視角 V10 高優先級提醒 {now_str()}"]
    added = 0

    if not pd.DataFrame(scan_df).empty:
        for _, row in pd.DataFrame(scan_df).iterrows():
            score = safe_float(row.get("評分"))
            event = clean_text(row.get("異常事件", ""))
            grade = clean_text(row.get("等級", ""))
            if (score is not None and score >= 60) or ("突破" in event) or ("放量" in event and grade == "強勢"):
                lines.append(f"候選｜{clean_text(row.get('代碼'))} {clean_text(row.get('股名'))}｜{grade}｜{event or '無'}｜評分 {clean_text(row.get('評分'))}")
                added += 1

    if not pd.DataFrame(position_scan_df).empty:
        for _, row in pd.DataFrame(position_scan_df).iterrows():
            signal = clean_text(row.get("訊號"))
            event = clean_text(row.get("異常事件", ""))
            if signal in ["危險"] or "跌破" in event or "急殺" in event:
                lines.append(f"持股警示｜{clean_text(row.get('代碼'))} {clean_text(row.get('股名'))}｜{signal}｜{event or '無'}｜評分 {clean_text(row.get('評分'))}")
                added += 1

    if added == 0:
        lines.append("目前沒有高優先級事件。")
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


def init_state():
    st.session_state.setdefault("scan_df", pd.DataFrame())
    st.session_state.setdefault("top3_df", pd.DataFrame())
    st.session_state.setdefault("order_df", pd.DataFrame())
    st.session_state.setdefault("df_map", {})
    st.session_state.setdefault("positions", [])
    st.session_state.setdefault("position_scan_df", pd.DataFrame())
    st.session_state.setdefault("search_tw_df", pd.DataFrame())
    st.session_state.setdefault("search_us_df", pd.DataFrame())
    st.session_state.setdefault("daily_report_df", pd.DataFrame())
    st.session_state.setdefault("market_state", "資料不足")
    st.session_state.setdefault("sector_df", pd.DataFrame())
    st.session_state.setdefault("auto_refresh", False)
    st.session_state.setdefault("refresh_seconds", DEFAULT_REFRESH_SECONDS)


init_state()

st.sidebar.title("📊 上帝視角 V10 設定")
capital = st.sidebar.number_input("總資金", min_value=10000, value=DEFAULT_CAPITAL, step=10000)
max_positions = st.sidebar.slider("同時持倉上限", 1, 5, DEFAULT_MAX_POSITIONS)
single_position_pct = st.sidebar.slider("單檔上限 %", 10, 50, int(DEFAULT_SINGLE_POSITION_PCT * 100), step=5) / 100
stop_loss_pct = st.sidebar.slider("固定停損 %", 2, 10, int(DEFAULT_STOP_LOSS_PCT * 100)) / 100
take_profit_pct = st.sidebar.slider("第一停利 %", 5, 20, int(DEFAULT_TAKE_PROFIT_PCT * 100)) / 100
daily_loss_stop_pct = st.sidebar.slider("當日停手機制 %", 2, 10, int(DEFAULT_DAILY_LOSS_STOP_PCT * 100)) / 100

tw_search_symbols = parse_symbols(st.sidebar.text_area("台股搜尋", "", height=90, placeholder="例如：2330,2317,2454"))
us_search_symbols = parse_symbols(st.sidebar.text_area("美股搜尋", "", height=90, placeholder="例如：NVDA,TSM,QQQM"))

st.sidebar.markdown("---")
auto_refresh = st.sidebar.toggle("啟用盤中自動刷新", value=st.session_state["auto_refresh"])
refresh_seconds = st.sidebar.slider("刷新秒數", 10, 300, st.session_state["refresh_seconds"], step=10)
st.session_state["auto_refresh"] = auto_refresh
st.session_state["refresh_seconds"] = refresh_seconds

st.markdown(
    """
    <div class="hero-card">
        <div class="title-xl">🌙 上帝視角 V10 深色專業交易介面版</div>
        <div class="muted">深色專業盤面 / 推薦引擎 / 實戰下單 / 族群輪動 / LINE 高優先級推播</div>
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("總資金", f"{capital:,.0f}")
m2.metric("持倉上限", f"{max_positions} 檔")
m3.metric("單檔上限", f"{single_position_pct:.0%}")
m4.metric("當日停手", f"{daily_loss_stop_pct:.0%}")

i1, i2, i3 = st.columns(3)
with i1:
    st.markdown(f'<div class="soft-box"><b>最後刷新時間</b><br>{now_str()}</div>', unsafe_allow_html=True)
with i2:
    st.markdown(f'<div class="soft-box"><b>自動刷新</b><br>{"開啟" if auto_refresh else "關閉"} / {refresh_seconds} 秒</div>', unsafe_allow_html=True)
with i3:
    st.markdown(f'<div class="soft-box"><b>盤面狀態</b><br>{st.session_state.get("market_state", "資料不足")}</div>', unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="top-btn">', unsafe_allow_html=True)
    if st.button("🚀 啟動 V10 市場掃描", use_container_width=True):
        run_auto_market_scan_v9(stop_loss_pct, take_profit_pct, capital, single_position_pct)
    st.markdown("</div>", unsafe_allow_html=True)

if st.session_state["scan_df"].empty:
    run_auto_market_scan_v9(stop_loss_pct, take_profit_pct, capital, single_position_pct)

if auto_refresh:
    auto_refresh_script(refresh_seconds)

if tw_search_symbols:
    st.session_state["search_tw_df"] = build_search_df(tw_search_symbols, "台股", stop_loss_pct, take_profit_pct)
if us_search_symbols:
    st.session_state["search_us_df"] = build_search_df(us_search_symbols, "美股", stop_loss_pct, take_profit_pct)

scan_df = as_object_df(st.session_state["scan_df"])
top3_df = as_object_df(st.session_state["top3_df"])
order_df = as_object_df(st.session_state["order_df"])
sector_df = as_object_df(st.session_state["sector_df"])

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🎯 主動推薦三檔",
    "🔎 搜尋健檢",
    "📋 下單表",
    "💼 持倉追蹤",
    "📰 盤後日報",
    "📲 推播中心"
])

with tab1:
    st.subheader("明日 / 盤中最強三檔")

    if not sector_df.empty:
        st.markdown("**族群輪動排行**")
        st.dataframe(sector_df, use_container_width=True, hide_index=True)

    if top3_df.empty:
        st.info("尚無推薦結果。")
    else:
        card_cols = st.columns(min(3, len(top3_df)))
        for i, (_, row) in enumerate(top3_df.iterrows()):
            color = get_confidence_color(row.get("評分"))
            with card_cols[i]:
                st.markdown(
                    f"""
                    <div class="signal-card">
                        <div class="title-xl">{clean_text(row.get("代碼", ""))}｜{clean_text(row.get("股名", ""))}</div>
                        <div class="muted">{clean_text(row.get("族群", ""))}｜{clean_text(row.get("等級", ""))}</div>
                        <div style="margin-top:10px;">
                            <span class="badge" style="background:{color};color:white;">信心 {clean_text(row.get("信心",""))}</span>
                            <span class="badge" style="background:#1e293b;color:#93c5fd;">{clean_text(row.get("訊號",""))}</span>
                            <span class="badge" style="background:#111827;color:#cbd5e1;">評分 {clean_text(row.get("評分",""))}</span>
                        </div>
                        <div class="kpi">進場：{clean_text(row.get("建議進場價","")) or "-"}</div>
                        <div>停損：{clean_text(row.get("停損價","")) or "-"}</div>
                        <div>停利：{clean_text(row.get("第一停利價","")) or "-"}</div>
                        <div>風報比：{clean_text(row.get("風險報酬比","")) or "-"}</div>
                        <div style="margin-top:8px;">異常：{clean_text(row.get("異常事件","")) or "-"}</div>
                        <div class="muted" style="margin-top:8px;">{clean_text(row.get("理由",""))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("### 市場掃描完整排行")
        st.dataframe(scan_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("台股 / 美股搜尋健檢")
    c1, c2 = st.columns(2)
    with c1:
        tw_df = st.session_state.get("search_tw_df", pd.DataFrame())
        if not pd.DataFrame(tw_df).empty:
            st.dataframe(tw_df, use_container_width=True, hide_index=True)
        else:
            st.info("左側輸入台股代碼後顯示。")
    with c2:
        us_df = st.session_state.get("search_us_df", pd.DataFrame())
        if not pd.DataFrame(us_df).empty:
            st.dataframe(us_df, use_container_width=True, hide_index=True)
        else:
            st.info("左側輸入美股代碼後顯示。")

with tab3:
    st.subheader("國泰手動下單表")
    if order_df.empty:
        st.info("尚無下單表。")
    else:
        st.dataframe(order_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ 下載下單表 CSV",
            order_df.to_csv(index=False).encode("utf-8-sig"),
            "god_view_orders_v10.csv",
            "text/csv"
        )

with tab4:
    st.subheader("持倉追蹤")
    pos_df = positions_df()
    edited_pos = st.data_editor(
        pos_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="positions_editor"
    )

    p1, p2 = st.columns(2)
    with p1:
        if st.button("⚡ 自動補齊持倉資訊", use_container_width=True):
            safe_df = ensure_position_columns(pd.DataFrame(edited_pos))
            safe_df = enrich_positions_auto(safe_df)
            st.session_state["positions"] = safe_df.fillna("").to_dict("records")
            st.success("持倉資訊已補齊")
            st.rerun()

    with p2:
        if st.button("📡 即時掃描持倉", use_container_width=True):
            safe_df = ensure_position_columns(pd.DataFrame(edited_pos))
            safe_df = enrich_positions_auto(safe_df)
            st.session_state["positions"] = safe_df.fillna("").to_dict("records")
            st.session_state["position_scan_df"] = build_position_scan_df(safe_df, stop_loss_pct, take_profit_pct)
            st.success("持倉掃描完成")
            st.rerun()

    latest_positions = positions_df()
    if not latest_positions.empty:
        st.dataframe(latest_positions, use_container_width=True, hide_index=True)

        avg_ret = pd.to_numeric(latest_positions["報酬率%"], errors="coerce").mean()
        avg_ret = 0 if pd.isna(avg_ret) else avg_ret

        pp1, pp2 = st.columns(2)
        pp1.metric("持倉檔數", len(latest_positions))
        pp2.metric("平均報酬率%", f"{avg_ret:.2f}")

    position_scan_df = st.session_state.get("position_scan_df", pd.DataFrame())
    if not position_scan_df.empty:
        st.markdown("### 持倉即時掃描結果")
        st.dataframe(position_scan_df, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("盤後籌碼日報")
    search_symbols_for_report = [to_tw_code(s) for s in tw_search_symbols] + [normalize_symbol(s) for s in us_search_symbols]
    report_df = build_daily_report_df(positions_df(), search_symbols_for_report, stop_loss_pct, take_profit_pct)

    if report_df.empty:
        st.info("尚無日報資料。")
    else:
        st.dataframe(report_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ 匯出日報 CSV",
            report_df.to_csv(index=False).encode("utf-8-sig"),
            f"chip_report_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )

with tab6:
    st.subheader("LINE 推播中心")
    priority_text = build_priority_alerts(
        st.session_state.get("scan_df", pd.DataFrame()),
        st.session_state.get("position_scan_df", pd.DataFrame())
    )
    st.code(priority_text)

    l1, l2 = st.columns(2)
    with l1:
        if st.button("📲 發送高優先級 LINE", use_container_width=True):
            ok, msg = send_line(priority_text)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    with l2:
        st.info("已設定 LINE secrets" if line_enabled() else "尚未設定 LINE secrets")

st.markdown("---")
st.caption("上帝視角 V10 深色專業交易介面版")
