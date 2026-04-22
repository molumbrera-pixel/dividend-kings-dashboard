import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor

# Configuración inicial
st.set_page_config(layout="wide", page_title="Dividend Kings PRO")

# =========================
# LISTA DE TICKERS
# =========================
DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LOW","MCD","MMM","MO",
    "NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT","TROW",
    "WBA","WMT","XOM"
]

# =========================
# FUNCIÓN DE EXTRACCIÓN (REVISADA)
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

        # Datos fundamentales con fallback
        pe = info.get("trailingPE")
        sector = info.get("sector", "N/A")
        
        # Robustez en Payout Ratio
        payout = info.get("payoutRatio")
        if payout is None:
            eps = info.get("trailingEps")
            div_rate = info.get("dividendRate")
            if eps and div_rate and eps > 0:
                payout = div_rate / eps

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        # Yield Actual (Últimos 12 meses)
        dividends = stock.dividends
        yield_value = 0
        yield_hist = None

        if not dividends.empty:
            last_year_divs = dividends[dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))].sum()
            yield_value = (last_year_divs / price) * 100

            # Yield Histórico Real (Promedio de yields anuales)
            yearly = dividends.resample("YE").sum()
            if len(yearly) > 1:
                # Calculamos el yield histórico promedio aproximado
                avg_price = hist["Close"].mean()
                yield_hist = (yearly.mean() / avg_price) * 100

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Price": price,
            "Yield": yield_value,
            "Yield_Hist": yield_hist,
            "PE": pe,
            "Payout": payout * 100 if payout else None, # Guardamos como porcentaje 0-100
            "Dist_Low": distance_low,
            "Drawdown": drawdown,
            "hist_df": hist # No se mostrará en la tabla, pero se usará para gráficos
        }
    except Exception:
        return None

@st.cache_data(ttl=3600)
def get_all_data(tickers):
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_ticker_data, tickers))
    return [r for r in results if r is not None]

# =========================
# LÓGICA DE SCORING
# =========================
def calculate_score(row):
    score = 0
    # Oportunidad por Yield
    if row['Yield'] and row['Yield_Hist']:
        if row['Yield'] > row['Yield_Hist'] * 1.1: score += 4
        elif row['Yield'] > row['Yield_Hist']: score += 2

    # Cercanía a mínimos y Drawdown
    if row['Dist_Low'] < 10: score += 3
    if row['Drawdown'] < -20: score += 2

    # Penalización por Payout (Riesgo de recorte)
    payout = row['Payout'] if row['Payout'] else 0
    if payout > 90: score -= 6
    elif payout > 75: score -= 3
    
    # Valuación PE
    pe = row['PE'] if row['PE'] else 100
    if pe < 15: score += 3
    elif pe > 30: score -= 2

    return score

# =========================
# INTERFAZ (UI)
# =========================
st.title("📊 Dividend Kings PRO Dashboard")
st.markdown("---")

with st.spinner("Analizando mercado en tiempo real..."):
    raw_data = get_all_data(DIVIDEND_KINGS)

df = pd.DataFrame(raw_data)
if df.empty:
    st.error("No se pudieron obtener datos.")
    st.stop()

df['Score'] = df.apply(calculate_score, axis=1)
df = df.sort_values("Score", ascending=False)

# --- TABLA DE OPORTUNIDADES ---
st.subheader("🏆 Ranking de Oportunidades")

# Columnas que queremos mostrar (excluimos hist_df para evitar el error visual)
display_cols = ["Ticker", "Sector", "Price", "Yield", "Yield_Hist", "PE", "Payout", "Score"]

st.dataframe(
    df[display_cols],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn(
            "Puntaje", min_value=int(df["Score"].min()), max_value=int(df["Score"].max()), format="%d pts"
        ),
        "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
        "Yield": st.column_config.NumberColumn("Yield %", format="%.2f%%"),
        "Yield_Hist": st.column_config.NumberColumn("Yield Hist %", format="%.2f%%"),
        "Payout": st.column_config.NumberColumn("Payout %", format="%.1f%%"),
        "PE": st.column_config.NumberColumn("P/E Ratio", format="%.1f"),
    }
)

# --- FILTROS ---
st.sidebar.header("🔎 Filtros de Cartera")
selected_sectors = st.sidebar.multiselect("Sectores", df["Sector"].unique(), default=df["Sector"].unique())
min_yield = st.sidebar.slider("Yield Mínimo (%)", 0.0, 10.0, 2.0)

filtered = df[(df["Sector"].isin(selected_sectors)) & (df["Yield"] >= min_yield)]

# --- GRÁFICOS ---
col_g1, col_g2 = st.columns(2)
with col_g1:
    fig_scatter = px.scatter(
        filtered, x="PE", y="Yield", size="Score", color="Sector",
        hover_name="Ticker", title="Atractivo: Valuación vs Rendimiento"
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

with col_g2:
    fig_hist = px.histogram(filtered, x="Score", color="Sector", title="Distribución de Calidad (Scores)")
    st.plotly_chart(fig_hist, use_container_width=True)

# --- DETALLE INDIVIDUAL ---
st.divider()
st.subheader("🔍 Análisis Profundo")
if not filtered.empty:
    selected_ticker = st.selectbox("Selecciona un Ticker para ver su historial:", filtered["Ticker"])
    ticker_data = next(x for x in raw_data if x["Ticker"] == selected_ticker)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Yield Actual", f"{ticker_data['Yield']:.2f}%", 
              delta=f"{ticker_data['Yield'] - ticker_data['Yield_Hist']:.2f}% vs Promedio")
    c2.metric("Distancia del Mínimo (52W)", f"{ticker_data['Dist_Low']:.1f}%")
    c3.metric("Payout Ratio", f"{ticker_data['Payout']:.1f}%" if ticker_data['Payout'] else "N/A")

    fig_line = px.line(ticker_data["hist_df"], y="Close", title=f"Precio 10 años - {selected_ticker}")
    st.plotly_chart(fig_line, use_container_width=True)
