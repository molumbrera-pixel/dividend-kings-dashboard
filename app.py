import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📊 Dividend Kings PRO Dashboard")

# =========================
# LISTA ACTUALIZADA
# =========================
DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LOW","MCD","MMM","MO",
    "NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT","TROW",
    "WBA","WMT","XOM"
]

# =========================
# DATA FUNCTION (PRO)
# =========================
@st.cache_data
def get_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="10y")

        if hist.empty:
            return None

        price = hist["Close"].iloc[-1]
        low_52 = hist["Close"].rolling(252).min().iloc[-1]
        high_all = hist["Close"].max()

        info = stock.info
        pe = info.get("trailingPE", None)
        payout = info.get("payoutRatio", None)

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        # =========================
        # 🔥 YIELD REAL (CLAVE)
        # =========================
        dividends = stock.dividends

        if dividends is not None and not dividends.empty:
            dividends.index = pd.to_datetime(dividends.index, errors="coerce")
            dividends = dividends.dropna()

            last_year_div = dividends.last("365D").sum()

            if last_year_div > 0 and price > 0:
                yield_value = (last_year_div / price) * 100
            else:
                yield_value = None
        else:
            yield_value = None

        # =========================
        # YIELD HISTÓRICO
        # =========================
        if dividends is not None and len(dividends) > 5:
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

    except Exception:
        return None


# =========================
# SCORING PRO AVANZADO
# =========================
def score_stock(d):
    score = 0
    payout = d.get("payout", 0)
    pe = d.get("pe", 50)

    # Yield vs histórico
    if d["yield"] and d["yield_hist"]:
        yield_growth = (d["yield"] - d["yield_hist"]) / d["yield_hist"] if d["yield_hist"] > 0 else 0
        if yield_growth > 0.1:
            score += 4
        elif d["yield"] > d["yield_hist"]:
            score += 3

    # Cerca de mínimos
    if d["distance_low"] < 15:
        score += 2

    # Drawdown (oportunidad)
    if d["drawdown"] < -20:
        score += 3
    elif d["drawdown"] < -10:
        score += 1

    # 🚨 Yield trap
    if payout and payout > 1:
        score -= 4
    elif payout and payout > 0.85:
        score -= 2

    # Valuación
    if pe and pe < 15:
        score += 2
    elif pe and pe < 20:
        score += 1
    elif pe and pe > 40:
        score -= 2
    elif pe and pe > 30:
        score -= 1

    return score


# =========================
# LOAD DATA
# =========================
data = {}
progress = st.progress(0)

with st.spinner("Cargando Dividend Kings..."):
    for i, ticker in enumerate(DIVIDEND_KINGS):
        result = get_data(ticker)
        if result:
            data[ticker] = result
        progress.progress((i + 1) / len(DIVIDEND_KINGS))


# =========================
# DATAFRAME
# =========================
rows = []

for ticker, d in data.items():
    if d["yield"] is None:
        continue

    rows.append({
        "Ticker": ticker,
        "Price": round(d["price"], 2),
        "Yield (%)": round(d["yield"], 2),
        "Hist Yield (%)": round(d["yield_hist"], 2) if d["yield_hist"] else None,
        "P/E": round(d["pe"], 1) if d["pe"] else None,
        "Payout": round(d["payout"] * 100, 1) if d["payout"] else None,
        "Dist 52W Low (%)": round(d["distance_low"], 1),
        "Drawdown (%)": round(d["drawdown"], 1),
        "Score": score_stock(d)
    })

df = pd.DataFrame(rows)

if df.empty:
    st.error("❌ No se pudieron cargar datos válidos.")
    st.stop()

df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)

# =========================
# TOP OPORTUNIDADES
# =========================
st.subheader("🏆 Top Oportunidades")
st.dataframe(df.head(10), use_container_width=True)

# =========================
# FILTROS
# =========================
st.sidebar.header("🔎 Filtros")

min_yield = st.sidebar.slider("Min Yield (%)", 0.0, 10.0, 2.0)
max_distance = st.sidebar.slider("Max Dist 52W Low (%)", 0.0, 100.0, 50.0)
min_score = st.sidebar.slider("Min Score", int(df["Score"].min()), int(df["Score"].max()), 0)

filtered = df[
    (df["Yield (%)"] >= min_yield) &
    (df["Dist 52W Low (%)"] <= max_distance) &
    (df["Score"] >= min_score)
]

st.subheader(f"📋 Tabla Filtrada ({len(filtered)} resultados)")
st.dataframe(filtered, use_container_width=True)

# =========================
# GRÁFICOS
# =========================
col1, col2 = st.columns(2)

with col1:
    fig = px.scatter(
        filtered,
        x="Drawdown (%)",
        y="Yield (%)",
        size="Score",
        color="Score",
        hover_name="Ticker",
        title="Oportunidades (Yield vs Drawdown)",
        color_continuous_scale="RdYlGn_r"
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig2 = px.histogram(filtered, x="Score", title="Distribución Score")
    st.plotly_chart(fig2, use_container_width=True)

# =========================
# DETALLE
# =========================
if not filtered.empty:
    ticker = st.selectbox("Selecciona acción", filtered["Ticker"])

    if ticker in data:
        d = data[ticker]
        hist = d["hist"]

        fig = px.line(hist, x=hist.index, y="Close", title=f"{ticker} Precio")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Yield", f"{d['yield']:.2f}%")
        col2.metric("Hist Yield", f"{d['yield_hist']:.2f}%" if d["yield_hist"] else "N/A")
        col3.metric("Drawdown", f"{d['drawdown']:.2f}%")
        col4.metric("Score", score_stock(d))
