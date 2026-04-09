from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

st.set_page_config(page_title="上帝視角", page_icon="📱", layout="wide")

# =========================
# 基本設定
# =========================
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


# =========================
# 共用工具
# =========================
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


# =========================
# TWSE 官方資料
# =========================
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


def get_tw_stock_info_from_yf(code: str) -> Dict[str, object]:
    symbol = f"{to_tw_code(code)}.TW"
    result = {
        "代碼": to_tw_code(code),
        "股名": to_tw_code(code),
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
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            result["目前價"] = safe_float(last.get("Close"))
            result["開盤價"] = safe_float(last.get("Open"))
            result["最高價"] = safe_float(last.get("High"))
            result["最低價"] = safe_float(last.get("Low"))
            result["成交股數"] = safe_float(last.get("Volume"))

        info = t.info if hasattr(t, "info") else {}
        result["股名"] = info.get("shortName") or info.get("longName") or result["代碼"]
        result["本益比"] = safe_float(info.get("trailingPE"))
        result["殖利率%"] = round(float(info.get("dividendYield", 0)) * 100, 2) if info.get("dividendYield") is not None else None
        result["股價淨值比"] = safe_float(info.get("priceToBook"))
    except Exception:
        pass

    return result


@st.cache_data(ttl=120)
def get_tw_stock_info(code: str) -> Dict[str, object]:
    code = to_tw_code(code)
    day_df = fetch_twse_stock_day_all()
    bw_df = fetch_twse_bwibbu_all()

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
    }

    if not day_df.empty and "代碼" in day_df.columns:
        match = day_df[day_df["代碼"] == code]
        if not match.empty:
            row = match.iloc[0]
            result["股名"] = row.get("股名", code)
            result["目前價"] = row.get("收盤價", None)
            result["開盤價"] = row.get("開盤價", None)
            result["最高價"] = row.get("最高價", None)
            result["最低價"] = row.get("最低價", None)
            result["成交股數"] = row.get("成交股數", None)

    if not bw_df.empty and "代碼" in bw_df.columns:
        match2 = bw_df[bw_df["代碼"] == code]
        if not match2.empty:
            row2 = match2.iloc[0]
            if result["股名"] == code:
                result["股名"] = row2.get("股名", code)
            result["本益比"] = row2.get("本益比", None)
            result["殖利率%"] = row2.get("殖利率%", None)
            result["股價淨值比"] = row2.get("股價淨值比", None)

    if result["目前價"] is None or result["股名"] == code:
        yf_result = get_tw_stock_info_from_yf(code)
        for k, v in yf_result.items():
            if result.get(k) in [None, "", code]:
                result[k] = v

    return result


# =========================
# 美股資料
# =========================
@st.cache_data(ttl=180)
def get_us_stock_info(symbol: str) -> Dict[str, object]:
    symbol = normalize_symbol(symbol)
    result = {
        "代碼": symbol,
        "股名": symbol,
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
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if hist is not None and not hist.empty:
            last = hist.iloc[-1]
            result["目前價"] = safe_float(last.get("Close"))
            result["開盤價"] = safe_float(last.get("Open"))
            result["最高價"] = safe_float(last.get("High"))
            result["最低價"] = safe_float(last.get("Low"))
            result["成交股數"] = safe_float(last.get("Volume"))

        info = t.info if hasattr(t, "info") else {}
        result["股名"] = info.get("shortName") or info.get("longName") or symbol
        result["本益比"] = safe_float(info.get("trailingPE"))
        result["殖利率%"] = round(float(info.get("dividendYield", 0)) * 100, 2) if info.get("dividendYield") is not None else None
        result["股價淨值比"] = safe_float(info.get("priceToBook"))
    except Exception:
        pass

    return result


def get_stock_info(symbol: str, market: str) -> Dict[str, object]:
    symbol = normalize_symbol(symbol)
    market = infer_market(symbol, market)
    if market == "台股":
        return get_tw_stock_info(symbol)
    return get_us_stock_info(symbol)


# =========================
# 技術分析
# =========================
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(0)


@st.cache_data(ttl=180)
def fetch_price_history(symbol: str, period: str = "6mo", market: str = "") -> pd.DataFrame:
    market = infer_market(symbol, market)
    symbol = to_yf_symbol(symbol, market)
    if not symbol:
        return pd.DataFrame()

    try:
        df = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False)
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
        df["Signal_Breakout"] = (df["Close"] > df["Prev20High"]) & (df["Volume"] > df["VOL20"])
        df["Signal_Trend"] = (df["Close"] > df["MA5"]) & (df["MA5"] > df["MA60"])
        df["Signal_Pullback"] = (
            (df["Low"] <= df["MA5"]) &
            (df["Close"] > df["MA5"]) &
            (df["MA5"] > df["MA60"])
        )
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()


def calc_signal(df: pd.DataFrame, stop_loss_pct: float, take_profit_pct: float) -> Dict[str, object]:
    if df.empty or len(df) < 65:
        return {
            "signal": "資料不足",
            "entry": None,
            "stop": None,
            "tp1": None,
            "score": -999,
            "reason": "資料不足",
            "close": None,
        }

    last = df.iloc[-1]
    close = float(last["Close"])
    ma5 = float(last["MA5"]) if pd.notna(last["MA5"]) else None
    ma60 = float(last["MA60"]) if pd.notna(last["MA60"]) else None
    vol = float(last["Volume"]) if pd.notna(last["Volume"]) else 0
    vol20 = float(last["VOL20"]) if pd.notna(last["VOL20"]) else 0
    prev20h = float(last["Prev20High"]) if pd.notna(last["Prev20High"]) else None
    r = float(last["RSI14"]) if pd.notna(last["RSI14"]) else 0

    trend_ok = ma5 is not None and ma60 is not None and close > ma5 > ma60
    breakout = bool(last["Signal_Breakout"])
    pullback = bool(last["Signal_Pullback"])

    score = 0
    reasons = []

    if trend_ok:
        score += 40
        reasons.append("5MA>60MA 且收盤站上5MA")
    if breakout:
        score += 35
        reasons.append("突破20日高點且量增")
    if pullback:
        score += 15
        reasons.append("回踩5MA承接")
    if vol20 > 0 and vol > vol20:
        score += 5
    if 50 <= r <= 78:
        score += 10
        reasons.append(f"RSI14={r:.1f}")
    elif r > 80:
        score -= 5
        reasons.append(f"RSI14={r:.1f} 偏熱")

    signal = "觀察"
    entry = None

    if breakout and trend_ok:
        signal = "突破買進"
        entry = round(max(close, prev20h or close), 2)
    elif pullback and trend_ok:
        signal = "5MA承接"
        entry = round(ma5, 2) if ma5 else round(close, 2)
    elif trend_ok:
        signal = "趨勢續抱"
        entry = round(close, 2)
    else:
        score -= 15
        reasons.append("未形成多頭趨勢")

    return {
        "signal": signal,
        "entry": entry,
        "stop": round(close * (1 - stop_loss_pct), 2),
        "tp1": round(close * (1 + take_profit_pct), 2),
        "score": score,
        "reason": "；".join(reasons),
        "close": round(close, 2),
    }


# =========================
# 持倉資料
# =========================
def ensure_position_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    for col in POSITION_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[POSITION_COLUMNS]
    return as_object_df(out)


def ensure_trade_log_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    for col in TRADE_LOG_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[TRADE_LOG_COLUMNS]
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


def build_position_scan_df(pos_df: pd.DataFrame, period: str, stop_loss_pct: float, take_profit_pct: float) -> pd.DataFrame:
    pos_df = ensure_position_columns(pos_df)
    if pos_df.empty:
        return pd.DataFrame()

    rows = []
    for _, row in pos_df.iterrows():
        symbol = normalize_symbol(row.get("代碼", ""))
        market = infer_market(symbol, row.get("市場", ""))
        if not symbol:
            continue

        df = fetch_price_history(symbol, period=period, market=market)
        sig = calc_signal(df, stop_loss_pct, take_profit_pct)
        close_val = sig["close"]
        if close_val is None:
            info = get_stock_info(symbol, market)
            close_val = info.get("目前價")

        rows.append({
            "市場": market,
            "代碼": to_tw_code(symbol) if market == "台股" else symbol,
            "股名": clean_text(row.get("股名", symbol)),
            "收盤": display_str(close_val),
            "訊號": clean_text(sig["signal"]),
            "建議進場價": display_str(sig["entry"]),
            "停損價": display_str(sig["stop"]),
            "第一停利價": display_str(sig["tp1"]),
            "評分": sig["score"],
            "理由": clean_text(sig["reason"]),
        })

    if not rows:
        return pd.DataFrame()
    return as_object_df(pd.DataFrame(rows).sort_values(["評分", "市場"], ascending=[False, True]).reset_index(drop=True))


# =========================
# 掃描與下單
# =========================
def recommend_qty(capital: float, alloc_pct: float, entry: Optional[float], market: str) -> Tuple[float, int]:
    budget = capital * alloc_pct

    entry = safe_float(entry)
    if entry is None or entry <= 0:
        return budget, 0

    market = infer_market("", market)

    if market == "台股":
        qty = int(budget // (entry * 1000))
        return budget, max(qty, 0)

    qty = int(budget // entry)
    return budget, max(qty, 0)


def make_order_df(top_df: pd.DataFrame, capital: float, alloc_pct: float) -> pd.DataFrame:
    rows = []
    for _, row in pd.DataFrame(top_df).iterrows():
        market = infer_market(row.get("代碼", ""), row.get("市場", ""))
        entry_price = safe_float(row.get("建議進場價"))
        budget, qty = recommend_qty(capital, alloc_pct, entry_price, market)

        rows.append({
            "市場": market,
            "代碼": clean_text(row.get("代碼", "")),
            "股名": clean_text(row.get("股名", row.get("代碼", ""))),
            "訊號": clean_text(row.get("訊號", "")),
            "委託類型": "現股/限價" if market == "台股" else "複委託/限價",
            "建議進場價": clean_text(row.get("建議進場價", "")),
            "停損價": clean_text(row.get("停損價", "")),
            "第一停利價": clean_text(row.get("第一停利價", "")),
            "配置金額": str(round(budget, 2)),
            "建議數量": f"{qty} 張" if market == "台股" else f"{qty} 股",
        })
    return as_object_df(pd.DataFrame(rows))


def build_scan_row(symbol: str, market: str, period: str, stop_loss_pct: float, take_profit_pct: float) -> Optional[Dict[str, object]]:
    market = infer_market(symbol, market)
    info = get_stock_info(symbol, market)
    df = fetch_price_history(symbol, period=period, market=market)
    sig = calc_signal(df, stop_loss_pct, take_profit_pct)

    close_val = sig["close"] if sig["close"] is not None else info.get("目前價")
    entry_val = sig["entry"]
    stop_val = sig["stop"]
    tp1_val = sig["tp1"]

    if close_val is not None:
        if entry_val is None and sig["signal"] != "資料不足":
            entry_val = round(float(close_val), 2)
        if stop_val is None and sig["signal"] != "資料不足":
            stop_val = round(float(close_val) * (1 - stop_loss_pct), 2)
        if tp1_val is None and sig["signal"] != "資料不足":
            tp1_val = round(float(close_val) * (1 + take_profit_pct), 2)

    return {
        "市場": market,
        "代碼": to_tw_code(symbol) if market == "台股" else normalize_symbol(symbol),
        "股名": clean_text(info.get("股名", symbol)),
        "收盤": display_str(close_val),
        "訊號": clean_text(sig["signal"]),
        "建議進場價": display_str(entry_val),
        "停損價": display_str(stop_val),
        "第一停利價": display_str(tp1_val),
        "評分": sig["score"],
        "理由": clean_text(sig["reason"]),
        "本益比": display_str(info.get("本益比")),
        "殖利率%": display_str(info.get("殖利率%")),
        "股價淨值比": display_str(info.get("股價淨值比")),
    }


def run_scan(symbols_tw: List[str], symbols_us: List[str], period: str, stop_loss_pct: float, take_profit_pct: float, capital: float, alloc_pct: float):
    results = []
    df_map = {}

    for symbol in symbols_tw:
        code = to_tw_code(symbol)
        row = build_scan_row(code, "台股", period, stop_loss_pct, take_profit_pct)
        if row:
            results.append(row)
            df_map[code] = fetch_price_history(code, period=period, market="台股")

    for symbol in symbols_us:
        s = normalize_symbol(symbol)
        row = build_scan_row(s, "美股", period, stop_loss_pct, take_profit_pct)
        if row:
            results.append(row)
            df_map[s] = fetch_price_history(s, period=period, market="美股")

    scan_df = pd.DataFrame(results)
    if not scan_df.empty:
        scan_df = scan_df.sort_values(["評分", "市場"], ascending=[False, True]).reset_index(drop=True)

    top3_df = scan_df.head(3).copy() if not scan_df.empty else pd.DataFrame()
    order_df = make_order_df(top3_df, capital, alloc_pct) if not top3_df.empty else pd.DataFrame()

    st.session_state["scan_df"] = as_object_df(scan_df)
    st.session_state["top3_df"] = as_object_df(top3_df)
    st.session_state["order_df"] = as_object_df(order_df)
    st.session_state["df_map"] = df_map


# =========================
# LINE
# =========================
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


def build_alert_text(top_df: pd.DataFrame) -> str:
    lines = [f"上帝視角 TWSE Pro 訊號 {now_str()}"]
    if top_df.empty:
        lines.append("目前沒有可用訊號。")
        return "\n".join(lines)

    for _, row in pd.DataFrame(top_df).iterrows():
        stock_name = clean_text(row.get("股名", row.get("代碼", "")))
        lines.append(
            f"{clean_text(row.get('代碼', ''))} {stock_name}｜{clean_text(row.get('訊號', ''))}｜進場 {clean_text(row.get('建議進場價', ''))}｜停損 {clean_text(row.get('停損價', ''))}｜停利 {clean_text(row.get('第一停利價', ''))}"
        )
    return "\n".join(lines)


# =========================
# 畫圖與刷新
# =========================
def draw_chart_no_plotly(df: pd.DataFrame, symbol: str):
    if df.empty:
        st.warning(f"{symbol} 無資料")
        return

    st.markdown(f"**{symbol} 走勢圖**")
    chart_df = pd.DataFrame(index=df.index)
    chart_df["Close"] = df["Close"]
    chart_df["MA5"] = df["MA5"]
    chart_df["MA20"] = df["MA20"]
    chart_df["MA60"] = df["MA60"]
    st.line_chart(chart_df, use_container_width=True)

    latest = df.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("收盤", display_str(latest.get("Close")))
    c2.metric("MA5", display_str(latest.get("MA5")))
    c3.metric("MA60", display_str(latest.get("MA60")))
    c4.metric("RSI14", display_str(latest.get("RSI14")))


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


# =========================
# Session state
# =========================
def init_state():
    st.session_state.setdefault("scan_df", pd.DataFrame())
    st.session_state.setdefault("top3_df", pd.DataFrame())
    st.session_state.setdefault("order_df", pd.DataFrame())
    st.session_state.setdefault("df_map", {})
    st.session_state.setdefault("positions", [])
    st.session_state.setdefault("trade_log", [])
    st.session_state.setdefault("last_alert_text", "")
    st.session_state.setdefault("auto_refresh", False)
    st.session_state.setdefault("refresh_seconds", DEFAULT_REFRESH_SECONDS)
    st.session_state.setdefault("position_scan_df", pd.DataFrame())


def positions_df() -> pd.DataFrame:
    rows = st.session_state.get("positions", [])
    if rows:
        return ensure_position_columns(pd.DataFrame(rows))
    return ensure_position_columns(pd.DataFrame())


def trade_log_df() -> pd.DataFrame:
    rows = st.session_state.get("trade_log", [])
    if rows:
        return ensure_trade_log_columns(pd.DataFrame(rows))
    return ensure_trade_log_columns(pd.DataFrame())


def save_positions(rows: List[Dict]):
    st.session_state["positions"] = rows


def save_trade_log(rows: List[Dict]):
    st.session_state["trade_log"] = rows


# =========================
# 初始化
# =========================
init_state()

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 4rem;
        max-width: 1200px;
    }
    div[data-testid="stMetric"] {
        background: rgba(240,242,246,0.55);
        border-radius: 14px;
        padding: 8px 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# Sidebar
# =========================
st.sidebar.title("📱 上帝視角 設定")
capital = st.sidebar.number_input("總資金", min_value=10000, value=DEFAULT_CAPITAL, step=10000)
max_positions = st.sidebar.slider("同時持倉上限", 1, 5, DEFAULT_MAX_POSITIONS)
single_position_pct = st.sidebar.slider("單檔上限 %", 10, 50, int(DEFAULT_SINGLE_POSITION_PCT * 100), step=5) / 100
stop_loss_pct = st.sidebar.slider("固定停損 %", 2, 10, int(DEFAULT_STOP_LOSS_PCT * 100)) / 100
take_profit_pct = st.sidebar.slider("第一停利 %", 5, 20, int(DEFAULT_TAKE_PROFIT_PCT * 100)) / 100
daily_loss_stop_pct = st.sidebar.slider("當日停手機制 %", 2, 10, int(DEFAULT_DAILY_LOSS_STOP_PCT * 100)) / 100
period = st.sidebar.selectbox("抓取區間", ["3mo", "6mo", "1y"], index=1)

tw_symbols = parse_symbols(st.sidebar.text_area("台股清單", "", height=100, placeholder="例如：2330,2317,2454"))
us_symbols = parse_symbols(st.sidebar.text_area("美股清單", "", height=100, placeholder="例如：NVDA,TSM,QQQM"))

st.sidebar.markdown("---")
auto_refresh = st.sidebar.toggle("啟用盤中自動刷新", value=st.session_state["auto_refresh"])
refresh_seconds = st.sidebar.slider("刷新秒數", 10, 300, st.session_state["refresh_seconds"], step=10)
st.session_state["auto_refresh"] = auto_refresh
st.session_state["refresh_seconds"] = refresh_seconds

# =========================
# Header
# =========================
st.title("📈 上帝視角 TWSE Pro 穩定修復版")
st.caption("可實戰三檔 / 國泰下單表 / 持倉追蹤 / 即時掃描 / LINE 推播")

m1, m2, m3, m4 = st.columns(4)
m1.metric("總資金", f"{capital:,.0f}")
m2.metric("持倉上限", f"{max_positions} 檔")
m3.metric("單檔上限", f"{single_position_pct:.0%}")
m4.metric("當日停手", f"{daily_loss_stop_pct:.0%}")

i1, i2 = st.columns(2)
with i1:
    st.info(f"最後刷新時間：{now_str()}")
with i2:
    st.info(f"自動刷新：{'開啟' if auto_refresh else '關閉'} / {refresh_seconds} 秒")

if st.button("🔍 立即重新掃描", type="primary", use_container_width=True):
    run_scan(tw_symbols, us_symbols, period, stop_loss_pct, take_profit_pct, capital, single_position_pct)

if st.session_state["scan_df"].empty and (tw_symbols or us_symbols):
    run_scan(tw_symbols, us_symbols, period, stop_loss_pct, take_profit_pct, capital, single_position_pct)

if auto_refresh:
    auto_refresh_script(refresh_seconds)

scan_df = as_object_df(st.session_state["scan_df"])
top3_df = as_object_df(st.session_state["top3_df"])
order_df = as_object_df(st.session_state["order_df"])
df_map = st.session_state["df_map"]

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 狙擊清單",
    "📋 下單表",
    "💼 持倉追蹤",
    "🧾 交易紀錄",
    "⚙️ 推播 / 設定"
])

with tab1:
    st.subheader("明日 / 盤中實戰 3 檔")
    if top3_df.empty:
        st.info("請先在左側輸入台股清單或美股清單，再按『立即重新掃描』。")
    else:
        st.dataframe(top3_df, use_container_width=True, hide_index=True)

        cards = st.columns(min(3, len(top3_df)))
        for i, (_, row) in enumerate(top3_df.iterrows()):
            with cards[i]:
                st.markdown(f"**{clean_text(row.get('代碼', ''))}**")
                st.caption(f"{clean_text(row.get('股名', ''))}｜{clean_text(row.get('市場', ''))}｜{clean_text(row.get('訊號', ''))}")
                st.write(f"進場：{clean_text(row.get('建議進場價', '')) or '-'}")
                st.write(f"停損：{clean_text(row.get('停損價', '')) or '-'}")
                st.write(f"停利：{clean_text(row.get('第一停利價', '')) or '-'}")

        st.subheader("完整排行")
        st.dataframe(scan_df, use_container_width=True, hide_index=True)

        chart_symbol = st.selectbox("查看圖表", options=top3_df["代碼"].tolist())
        chart_market = top3_df[top3_df["代碼"] == chart_symbol]["市場"].iloc[0]
        draw_chart_no_plotly(df_map.get(chart_symbol, fetch_price_history(chart_symbol, period=period, market=chart_market)), chart_symbol)

with tab2:
    st.subheader("國泰手動下單表")
    if order_df.empty:
        st.info("尚無下單表，請先完成掃描。")
    else:
        st.dataframe(order_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ 下載 CSV",
            order_df.to_csv(index=False).encode("utf-8-sig"),
            "god_view_orders.csv",
            "text/csv"
        )

with tab3:
    st.subheader("持倉追蹤面板")
    pos_df = positions_df()

    edited_pos = st.data_editor(
        as_object_df(pos_df),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="positions_editor"
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("⚡ 自動補齊資訊", use_container_width=True):
            safe_df = ensure_position_columns(pd.DataFrame(edited_pos))
            safe_df = enrich_positions_auto(safe_df)
            save_positions(safe_df.fillna("").to_dict("records"))
            st.success("已自動補上股名、目前價、報酬率、狀態、估值欄位")
            st.rerun()

    with c2:
        if st.button("📡 即時掃描持倉", use_container_width=True):
            safe_df = ensure_position_columns(pd.DataFrame(edited_pos))
            safe_df = enrich_positions_auto(safe_df)
            save_positions(safe_df.fillna("").to_dict("records"))
            scan_result = build_position_scan_df(safe_df, period, stop_loss_pct, take_profit_pct)
            st.session_state["position_scan_df"] = scan_result
            st.success("持倉掃描完成")
            st.rerun()

    latest_positions = positions_df()
    if not latest_positions.empty:
        st.dataframe(as_object_df(latest_positions), use_container_width=True, hide_index=True)

        avg_ret = pd.to_numeric(latest_positions["報酬率%"], errors="coerce").mean()
        avg_ret = 0 if pd.isna(avg_ret) else avg_ret

        p1, p2 = st.columns(2)
        p1.metric("持倉檔數", len(latest_positions))
        p2.metric("平均報酬率%", f"{avg_ret:.2f}")

    position_scan_df = st.session_state.get("position_scan_df", pd.DataFrame())
    if not position_scan_df.empty:
        st.subheader("持倉即時掃描結果")
        st.dataframe(as_object_df(position_scan_df), use_container_width=True, hide_index=True)

with tab4:
    st.subheader("交易紀錄")
    log_df = trade_log_df()

    edited_log = st.data_editor(
        as_object_df(log_df),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="trade_log_editor"
    )

    l1, l2 = st.columns(2)
    with l1:
        if st.button("💾 儲存交易紀錄", use_container_width=True):
            safe_log = ensure_trade_log_columns(pd.DataFrame(edited_log))
            save_trade_log(safe_log.fillna("").to_dict("records"))
            st.success("交易紀錄已儲存")

    with l2:
        if not pd.DataFrame(edited_log).empty:
            st.download_button(
                "⬇️ 匯出交易紀錄 CSV",
                pd.DataFrame(edited_log).to_csv(index=False).encode("utf-8-sig"),
                "god_view_trade_log.csv",
                "text/csv",
                use_container_width=True
            )

with tab5:
    st.subheader("LINE 推播 / 風控摘要")
    alert_text = build_alert_text(top3_df)
    st.code(alert_text)

    a1, a2 = st.columns(2)
    with a1:
        if st.button("發送 LINE 訊號", use_container_width=True):
            ok, msg = send_line(alert_text)
            if ok:
                st.success(msg)
                st.session_state["last_alert_text"] = alert_text
            else:
                st.error(msg)

    with a2:
        st.info("已設定 LINE secrets" if line_enabled() else "尚未設定 LINE secrets")

    st.markdown("**穩定修復版修正內容**")
    st.markdown(
        "- 修正持倉追蹤 pandas/pyarrow 型別衝突\n"
        "- 所有顯示欄位統一用字串回填\n"
        "- 台股先 TWSE，抓不到自動用 yfinance 補\n"
        "- 自動判斷市場\n"
        "- 保留可實戰三檔、下單表、持倉、LINE"
    )

st.markdown("---")
st.caption("上帝視角 TWSE Pro 穩定修復版：研究與決策輔助用途，不保證獲利。")
