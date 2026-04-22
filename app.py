import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📊 Dividend Kings PRO Dashboard")

# =========================
# LISTA ACTUALIZADA 2026
# =========================
DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LOW","MCD","MMM","MO",
    "NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT","TROW",
    "WBA","WMT","XOM"
]

# =========================
# DATA FUNCTION (ROBUSTA)
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

        # 🔥 YIELD ROBUSTO
        dividend_yield = info.get("dividendYield", None)
        yield_value = dividend_yield * 100 if dividend_yield and 0 < dividend_yield < 0.15 else None

        pe = info.get("trailingPE", None)
        payout = info.get("payoutRatio", None)

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        # DIVIDENDOS HISTÓRICOS
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
    except Exception:
        return None

# =========================
# SCORING PRO MEJORADO
# =========================
def score_stock(d):
    score = 0
    payout = d.get("payout", 0)
    pe = d.get("pe", 50)

    # Yield vs histórico (BONUS CRECIENTE)
    if d["yield"] and d["yield_hist"]:
        yield_growth = (d["yield"] - d["yield_hist"]) / d["yield_hist"] if d["yield_hist"] > 0 else 0
        if yield_growth > 0.1:  # +10% crecimiento
            score += 4
        elif d["yield"] > d["yield_hist"]:
            score += 3

    # Cerca de mínimos
    if d["distance_low"] < 15:
        score += 2

    # Caída relevante (mejor oportunidad)
    if d["drawdown"] < -20:
        score += 3
    elif d["drawdown"] < -10:
        score += 1

    # 🔴 YIELD TRAP PENALIZACIÓN
    if payout > 1:
        score -= 4
    elif payout > 0.85:
        score -= 2

    # Valuación refinada
    if pe < 15:
        score += 2
    elif pe < 20:
        score += 1
    elif pe > 30:
        score -= 1
    elif pe > 40:
        score -= 2

    return score

# =========================
# LOAD DATA
# =========================
data = {}
progress_bar = st.progress(0)
n = len(DIVIDEND_KINGS)

with st.spinner("Cargando datos de Dividend Kings..."):
    for i, ticker in enumerate(DIVIDEND_KINGS):
        result = get_data(ticker)
        if result:
            data[ticker] = result
        progress_bar.progress((i + 1) / n)

# =========================
# DATAFRAME PRINCIPAL
# =========================
rows = []
for ticker, d in data.items():
    if d["yield"] is None:  # 🚫 Skip sin yield
        continue
    
    score = score_stock(d)
    rows.append({
        "Ticker": ticker,
        "Price": round(d["price"], 2),
        "Yield (%)": round(d["yield"], 2),
        "Hist Yield (%)": round(d["yield_hist"], 2) if d["yield_hist"] else None,
        "P/E": round(d["pe"], 1) if d["pe"] else None,
        "Payout": f"{round(d['payout']*100,1)}%" if d["payout"] else None,
        "Dist 52W Low (%)": round(d["distance_low"], 1),
        "Drawdown (%)": round(d["drawdown"], 1),
        "Score": score
    })

df = pd.DataFrame(rows)
if df.empty:
    st.error("❌ No se pudieron cargar datos válidos. Revisa conexión y tickers.")
    st.stop()

df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)

# =========================
# RANKING TOP
# =========================
st.subheader("🏆 Top Oportunidades (Score PRO)")
st.dataframe(df.head(10), use_container_width=True, height=400)

# =========================
# FILTROS SIDE BAR
# =========================
st.sidebar.header("🔎 Filtros Avanzados")
min_yield = st.sidebar.slider("Min Yield (%)", 0.0, 10.0, 2.0)
max_distance = st.sidebar.slider("Max Dist. 52W Low (%)", 0.0, 100.0, 50.0)
min_score = st.sidebar.slider("Min Score", df["Score"].min(), df["Score"].max(), 0)

filtered = df[
    (df["Yield (%)"] >= min_yield) &
    (df["Dist 52W Low (%)"] <= max_distance) &
    (df["Score"] >= min_score)
]

st.subheader(f"📋 Tabla Filtrada ({len(filtered)} resultados)")
st.dataframe(filtered, use_container_width=True)

# =========================
# VISUALIZACIONES MEJORADAS
# =========================
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Yield vs Drawdown")
    opps = filtered[filtered["Drawdown (%)"] < 0]  # Solo caídas
    fig1 = px.scatter(
        opps if not opps.empty else filtered,
        x="Drawdown (%)",
        y="Yield (%)",
        size="Score",
        color="Score",
        hover_name="Ticker",
        title="🔴 Oportunidades: Alto Yield + Caída",
        color_continuous_scale="RdYlGn_r"
    )
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.subheader("📈 Score Distribution")
    fig2 = px.histogram(filtered, x="Score", title="Distribución Scores")
    st.plotly_chart(fig2, use_container_width=True)

# =========================
# DETALLE INDIVIDUAL
# =========================
if not filtered.empty:
    st.subheader("🔍 Detalle Acción")
    ticker = st.selectbox("Selecciona ticker:", filtered["Ticker"])
    
    if ticker in data:
        d = data[ticker]
        hist = d["hist"]
        
        # Gráfico precio
        fig_price = px.line(hist.tail(2000), x=hist.tail(2000).index, y="Close", 
                           title=f"{ticker} - Precio Histórico (10Y)")
        st.plotly_chart(fig_price, use_container_width=True)
        
        # Métricas mejoradas
        col1, col2, col3, col4, col5 = st.columns(5)
        score = score_stock(d)
        
        col1.metric("💰 Yield", f"{d['yield']:.2f}%" if d['yield'] else "N/A")
        col2.metric("📊 Hist Yield", f"{d['yield_hist']:.2f}%" if d['yield_hist'] else "N/A")
        col3.metric("📉 Drawdown", f"{d['drawdown']:.1f}%")
        col4.metric("🎯 P/E", f"{d['pe']:.1f}" if d['pe'] else "N/A")
        col5.metric("⭐ Score PRO", score, delta=None)

st.markdown("---")
st.caption("🔄 Datos en tiempo real via yfinance | Actualizado: " + pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'))
