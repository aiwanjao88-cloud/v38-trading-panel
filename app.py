import requests
import pandas as pd
import streamlit as st
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="上帝視角", layout="wide")

# =========================
# TWSE 即時資料
# =========================
@st.cache_data(ttl=30)
def get_twse_realtime(symbol):
    code = symbol.replace(".TW", "")
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{code}.tw"

    try:
        r = requests.get(url, timeout=5)
        data = r.json()

        if data["msgArray"]:
            d = data["msgArray"][0]
            price = float(d["z"]) if d["z"] != "-" else None
            name = d["n"]

            return {
                "price": price,
                "name": name
            }
    except:
        pass

    return {"price": None, "name": symbol}


# =========================
# 美股
# =========================
@st.cache_data(ttl=60)
def get_us_price(symbol):
    try:
        df = yf.download(symbol, period="5d", progress=False)
        price = float(df["Close"].iloc[-1])
        name = yf.Ticker(symbol).info.get("shortName", symbol)
        return {"price": price, "name": name}
    except:
        return {"price": None, "name": symbol}


# =========================
# 自動補資料
# =========================
def enrich_position(row):
    symbol = row["代碼"]

    if symbol.isdigit():
        symbol_full = symbol + ".TW"
        data = get_twse_realtime(symbol_full)
    else:
        symbol_full = symbol
        data = get_us_price(symbol)

    price = data["price"]
    name = data["name"]

    row["股名"] = name
    row["目前價"] = price

    try:
        cost = float(row["成本價"])
        if price:
            row["報酬率%"] = round((price - cost) / cost * 100, 2)
    except:
        pass

    # 狀態判斷
    try:
        stop = float(row["停損價"])
        tp = float(row["第一停利價"])

        if price <= stop:
            row["狀態"] = "🔴 停損"
        elif price >= tp:
            row["狀態"] = "🟢 停利"
        else:
            row["狀態"] = "持有中"
    except:
        row["狀態"] = "持有中"

    return row


# =========================
# UI
# =========================
st.title("📈 上帝視角 TWSE版")

# 側邊
capital = st.sidebar.number_input("總資金", value=200000)
tw_list = st.sidebar.text_area("台股清單（輸入代碼即可）", "")
us_list = st.sidebar.text_area("美股清單", "")

# =========================
# 持倉面板
# =========================
st.subheader("💼 持倉追蹤")

if "positions" not in st.session_state:
    st.session_state["positions"] = pd.DataFrame(columns=[
        "市場", "代碼", "股名", "持有數量", "成本價",
        "目前價", "報酬率%", "停損價", "第一停利價", "狀態"
    ])

df = st.data_editor(
    st.session_state["positions"],
    num_rows="dynamic",
    use_container_width=True
)

# 自動補
if st.button("⚡ 自動補齊資訊"):
    new_rows = []
    for _, row in df.iterrows():
        row = enrich_position(row)
        new_rows.append(row)

    st.session_state["positions"] = pd.DataFrame(new_rows)
    st.success("已更新")
    st.rerun()

# =========================
# 顯示
# =========================
st.dataframe(st.session_state["positions"], use_container_width=True)

# =========================
# LINE 推播
# =========================
if st.button("📲 發送LINE"):
    st.warning("請先設定 secrets")
