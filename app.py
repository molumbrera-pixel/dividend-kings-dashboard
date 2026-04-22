import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.title("📊 Dividend Kings PRO Dashboard")

@st.cache_data
def get_data(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="10y")
    info = stock.info

    if hist.empty:
        return None

    price = hist["Close"].iloc[-1]
    low_52 = hist["Close"].rolling(252).min().iloc[-1]
    high_all = hist["Close"].max()

    dividend_yield = info.get("dividendYield", 0)
    pe = info.get("trailingPE", None)
    payout = info.get("payoutRatio", None)

    # Métricas calculadas
    distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
    drawdown = (price - high_all) / high_all * 100 if high_all else 0

    # Yield histórico aproximado
    dividends = stock.dividends
    if len(dividends) > 5:
        yearly = dividends.resample("Y").sum()
        yield_hist = yearly.mean() / price
    else:
        yield_hist = None

    return {
        "hist": hist,
        "price": price,
        "yield": dividend_yield * 100 if dividend_yield else 0,
        "yield_hist": yield_hist * 100 if yield_hist else None,
        "pe": pe,
        "payout": payout,
        "distance_low": distance_low,
        "drawdown": drawdown
    }

# Scoring inteligente
def score_stock(d):
    score = 0

    if d["yield"] and d["yield_hist"]:
        if d["yield"] > d["yield_hist"]:
            score += 2

    if d["distance_low"] < 20:
        score += 2

    if d["drawdown"] < -20:
        score += 1

    if d["payout"] and d["payout"] > 0.8:
        score -= 2

    if d["pe"] and d["pe"] > 25:
        score -= 1

    if score >= 3:
        return "💰 Value"
    elif score >= 1:
        return "⚖️ Neutral"
    else:
        return "❌ Risk"

# Cargar datos
DIVIDEND_KINGS = [
    "KO", "JNJ", "PG", "PEP", "MCD",
    "LOW", "CL", "MMM", "ABBV", "TGT"
]
data = {}
for ticker in DIVIDEND_KINGS:
    data[ticker] = get_data(ticker)

rows = []
for ticker, d in data.items():
    if d:
        rows.append({
            "Ticker": ticker,
            "Price": d["price"],
            "Yield (%)": d["yield"],
            "Hist Yield (%)": d["yield_hist"],
            "P/E": d["pe"],
            "Payout": d["payout"],
            "Dist 52W Low (%)": d["distance_low"],
            "Drawdown (%)": d["drawdown"],
            "Score": score_stock(d)
        })

df = pd.DataFrame(rows)

# Sidebar filtros
st.sidebar.header("🔎 Filtros")

min_yield = st.sidebar.slider("Min Yield", 0.0, 10.0, 2.0)
max_distance = st.sidebar.slider("Max distancia a mínimo", 0.0, 100.0, 50.0)
score_filter = st.sidebar.multiselect("Score", df["Score"].unique(), default=df["Score"].unique())

filtered = df[
    (df["Yield (%)"] >= min_yield) &
    (df["Dist 52W Low (%)"] <= max_distance) &
    (df["Score"].isin(score_filter))
]

st.dataframe(filtered, use_container_width=True)

# Selección
ticker = st.selectbox("Selecciona acción", filtered["Ticker"])

if ticker:
    d = data[ticker]
    hist = d["hist"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], name="Precio"))

    fig.update_layout(title=f"{ticker} Precio histórico", template="plotly_white")

    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Yield", f"{d['yield']:.2f}%")
    col2.metric("Hist Yield", f"{d['yield_hist']:.2f}%" if d["yield_hist"] else "N/A")
    col3.metric("Drawdown", f"{d['drawdown']:.2f}%")
    col4.metric("Score", score_stock(d))
DIVIDEND_KINGS = [
    "KO", "JNJ", "PG", "PEP", "MCD",
    "LOW", "CL", "MMM", "ABBV", "TGT"
]
