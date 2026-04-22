import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(layout="wide", page_title="Dividend Kings PRO")

# =========================
# LISTA
# =========================
DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LOW","MCD","MMM","MO",
    "NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT","TROW",
    "WBA","WMT","XOM"
]

# =========================
# FETCH DATA (PARALELO)
# =========================
def fetch_ticker_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="10y")

        if hist.empty:
            return None

        price = hist["Close"].iloc[-1]
        low_52 = hist["Low"].rolling(252).min().iloc[-1]
        high_all = hist["High"].max()

        pe = info.get("trailingPE")
        payout = info.get("payoutRatio")
        sector = info.get("sector", "N/A")

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        # =========================
        # YIELD ROBUSTO
        # =========================
        dividends = stock.dividends
        yield_value = 0
        yield_hist = None

        if dividends is not None and not dividends.empty:
            dividends.index = pd.to_datetime(dividends.index, errors="coerce")
            dividends = dividends.dropna()

            # Últimos 12 meses
            last_year_divs = dividends[dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))].sum()
            if price > 0:
                yield_value = (last_year_divs / price) * 100

            # Histórico corregido
            yearly_divs = dividends.resample("YE").sum()
            if len(yearly_divs) > 1:
                avg_price = hist["Close"].mean()
                yield_hist = (yearly_divs.mean() / avg_price) * 100

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Price": price,
            "Yield": yield_value,
            "Yield_Hist": yield_hist,
            "PE": pe,
            "Payout": payout,
            "Dist_Low": distance_low,
            "Drawdown": drawdown,
            "hist_df": hist
        }

    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_all_data(tickers):
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_ticker_data, tickers)
    return [r for r in results if r is not None]

# =========================
# SCORING
# =========================
def calculate_score(row):
    score = 0

    # Yield vs histórico
    if row['Yield'] and row['Yield_Hist']:
        if row['Yield'] > row['Yield_Hist'] * 1.1:
            score += 4
        elif row['Yield'] > row['Yield_Hist']:
            score += 2

    # Precio
    if row['Dist_Low'] < 10:
        score += 3
    if row['Drawdown'] < -20:
        score += 2

    # Riesgo
    payout = row['Payout'] or 0
    if payout > 0.9:
        score -= 5
    elif payout > 0.75:
        score -= 2

    # Valuación
    pe = row['PE'] or 100
    if pe < 15:
        score += 3
    elif pe > 30:
        score -= 2

    return score

# =========================
# APP
# =========================
st.title("📊 Dividend Kings PRO Dashboard")

with st.spinner("Descargando datos..."):
    raw_data = get_all_data(DIVIDEND_KINGS)

df = pd.DataFrame(raw_data)

if df.empty:
    st.error("No se pudieron cargar datos.")
    st.stop()

df['Score'] = df.apply(calculate_score, axis=1)
df = df.sort_values("Score", ascending=False)

# =========================
# FORMATO
# =========================
def style_df(df_to_style):
    return df_to_style.style.format({
        "Price": "${:.2f}",
        "Yield": "{:.2f}%",
        "Yield_Hist": "{:.2f}%",
        "PE": "{:.1f}",
        "Payout": "{:.1%}",
        "Dist_Low": "{:.1f}%",
        "Drawdown": "{:.1f}%"
    }).background_gradient(subset=["Score"], cmap="RdYlGn")

st.subheader("🏆 Top Oportunidades")
st.dataframe(style_df(df.head(10)), use_container_width=True)

# =========================
# FILTROS
# =========================
st.sidebar.header("Filtros")

sector_sel = st.sidebar.multiselect(
    "Sector",
    df["Sector"].dropna().unique(),
    default=df["Sector"].dropna().unique()
)

min_score = st.sidebar.slider(
    "Score mínimo",
    int(df["Score"].min()),
    int(df["Score"].max()),
    5
)

filtered = df[
    (df["Sector"].isin(sector_sel)) &
    (df["Score"] >= min_score)
]

st.subheader(f"Resultados ({len(filtered)})")
st.dataframe(filtered, use_container_width=True)

# =========================
# GRÁFICO
# =========================
fig = px.scatter(
    filtered,
    x="PE",
    y="Yield",
    size="Score",
    color="Sector",
    hover_name="Ticker",
    title="Yield vs P/E"
)

st.plotly_chart(fig, use_container_width=True)

# =========================
# DETALLE
# =========================
st.divider()

if not filtered.empty:
    ticker = st.selectbox("Seleccionar acción", filtered["Ticker"])

    data = next((x for x in raw_data if x["Ticker"] == ticker), None)

    if data:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.metric("Precio", f"${data['Price']:.2f}")
            st.metric("Yield", f"{data['Yield']:.2f}%")

            if data["Yield_Hist"]:
                delta = data["Yield"] - data["Yield_Hist"]
                st.metric("Yield vs Hist", f"{data['Yield_Hist']:.2f}%", f"{delta:.2f}%")

            payout = data["Payout"]
            st.write(f"Payout: {payout:.1%}" if payout else "Payout: N/A")
            st.write(f"Sector: {data['Sector']}")

        with col2:
            fig_hist = px.line(data["hist_df"], y="Close", title=ticker)
            st.plotly_chart(fig_hist, use_container_width=True)
