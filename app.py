import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📊 Dividend Kings PRO Dashboard")

# =========================
# LISTA
# =========================
DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF.B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LEG","LOW","MCD","MMM",
    "MO","NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT",
    "TROW","WBA","WMT","XOM"
]

# =========================
# DATA FUNCTION (FIXED)
# =========================
@st.cache_data
def get_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="10y")
        info = stock.info

        if hist.empty:
            return None

        price = hist["Close"].iloc[-1]
        low_52 = hist["Close"].rolling(252).min().iloc[-1]
        high_all = hist["Close"].max()

        # 🔥 FIX YIELD
        dividend_yield = info.get("dividendYield", None)
        if dividend_yield and 0 < dividend_yield < 0.15:
            yield_value = dividend_yield * 100
        else:
            yield_value = None

        pe = info.get("trailingPE", None)
        payout = info.get("payoutRatio", None)

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        # =========================
        # DIVIDENDOS HISTÓRICOS
        # =========================
        dividends = stock.dividends

        if dividends is None or dividends.empty:
            yield_hist = None
        else:
            dividends.index = pd.to_datetime(dividends.index, errors="coerce")
            dividends = dividends.dropna()

            if len(dividends) > 5:
                yearly = dividends.resample("YE").sum()
                yield_hist = (yearly.mean() / price) * 100
            else:
                yield_hist = None

        return {
            "hist": hist,
            "price": price,
            "yield": yield_value,
            "yield_hist": yield_hist,
            "pe": pe,
            "payout": payout,
            "distance_low": distance_low,
            "drawdown": drawdown
        }

    except:
        return None


# =========================
# SCORING PRO REAL
# =========================
def score_stock(d):
    score = 0

    # Yield vs histórico
    if d["yield"] and d["yield_hist"]:
        if d["yield"] > d["yield_hist"]:
            score += 3

    # Cerca de mínimos
    if d["distance_low"] < 15:
        score += 2

    # Caída relevante
    if d["drawdown"] < -20:
        score += 2

    # 🔴 Yield trap
    if d["payout"] and d["payout"] > 1:
        score -= 4
    elif d["payout"] and d["payout"] > 0.85:
        score -= 2

    # Valuación
    if d["pe"] and d["pe"] < 20:
        score += 1
    elif d["pe"] and d["pe"] > 30:
        score -= 1

    return score


# =========================
# LOAD DATA
# =========================
data = {}

with st.spinner("Cargando datos..."):
    for ticker in DIVIDEND_KINGS:
        result = get_data(ticker)
        if result:
            data[ticker] = result

# =========================
# DATAFRAME
# =========================
rows = []

for ticker, d in data.items():
    score = score_stock(d)

    # 🚫 eliminar basura
    if d["yield"] is None:
        continue

    rows.append({
        "Ticker": ticker,
        "Price": d["price"],
        "Yield (%)": d["yield"],
        "Hist Yield (%)": d["yield_hist"],
        "P/E": d["pe"],
        "Payout": d["payout"],
        "Dist 52W Low (%)": d["distance_low"],
        "Drawdown (%)": d["drawdown"],
        "Score": score
    })

df = pd.DataFrame(rows)

if df.empty:
    st.error("No se pudieron cargar datos.")
    st.stop()

# =========================
# RANKING
# =========================
df = df.sort_values(by="Score", ascending=False)

st.subheader("🏆 Top Oportunidades")
st.dataframe(df.head(10), use_container_width=True)

# =========================
# FILTROS
# =========================
st.sidebar.header("🔎 Filtros")

min_yield = st.sidebar.slider("Min Yield", 0.0, 10.0, 2.0)
max_distance = st.sidebar.slider("Max distancia a mínimo", 0.0, 100.0, 50.0)

filtered = df[
    (df["Yield (%)"] >= min_yield) &
    (df["Dist 52W Low (%)"] <= max_distance)
]

st.subheader("📋 Tabla filtrada")
st.dataframe(filtered, use_container_width=True)

# =========================
# SCATTER
# =========================
st.subheader("📊 Yield vs Drawdown")

fig = px.scatter(
    filtered,
    x="Drawdown (%)",
    y="Yield (%)",
    size="Score",
    color="Score",
    hover_name="Ticker",
    title="Oportunidades: alto yield + caída"
)

st.plotly_chart(fig, use_container_width=True)

# =========================
# DETALLE
# =========================
if not filtered.empty:
    ticker = st.selectbox("Selecciona acción", filtered["Ticker"])

    if ticker:
        d = data[ticker]
        hist = d["hist"]

        fig = px.line(hist, x=hist.index, y="Close", title=f"{ticker} Precio")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Yield", f"{d['yield']:.2f}%" if d["yield"] else "N/A")
        col2.metric("Hist Yield", f"{d['yield_hist']:.2f}%" if d["yield_hist"] else "N/A")
        col3.metric("Drawdown", f"{d['drawdown']:.2f}%")
        col4.metric("Score", score_stock(d))
