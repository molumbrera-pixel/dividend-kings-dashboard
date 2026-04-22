import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import time
import requests
import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# =========================
# CONFIGURACIÓN Y SESIÓN ANTIBLOQUEO
# =========================
st.set_page_config(layout="wide", page_title="Dividend Kings PRO HYBRID")

# Creamos una sesión con caché (evita pedir lo mismo 100 veces) y reintentos
@st.cache_resource
def get_safe_session():
    session = requests_cache.CachedSession('yahoo_cache', expire_after=3600) # Caché de 1 hora
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    # Lógica de reintento si Yahoo falla temporalmente
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

session = get_safe_session()

# =========================
# LISTA (Limpia)
# =========================
DIVIDEND_KINGS = sorted(list(set([
    "AWR","DOV","NWN","GPC","PG","PH","EMR","CINF","KO","JNJ","CL","NDSN",
    "ABM","SCL","CBSH","FUL","MO","BKH","NFG","UVV","MSA","SYY","LOW",
    "TGT","GWW","ABT","ADP","LIN","SHW","MKC","PNR","ROL","AOS","APD","ATO",
    "BDX","BF-B","CAH","CAT","CLX","CMS","CVX","ED","FRT","HRL","ITW","KMB",
    "MCD","MMM","PEP","PPG","RPM","SJW","SWK","TROW","WBA","WMT","XOM","NUE"
])))

# =========================
# FETCH DATA (MEJORADO)
# =========================
def fetch_fast_data(ticker):
    try:
        stock = yf.Ticker(ticker, session=session)
        hist = stock.history(period="10y", progress=False)

        if hist.empty or len(hist) < 200:
            return None

        price = hist["Close"].iloc[-1]
        low_52 = hist["Close"].tail(252).min()
        high_all = hist["Close"].max()

        # Yield Actual
        dividends = stock.dividends
        yield_value = 0
        yield_hist = None

        if not dividends.empty:
            dividends.index = pd.to_datetime(dividends.index).tz_localize(None)
            last_year = dividends[dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))]
            yield_value = (last_year.sum() / price) * 100

            # Yield Histórico Real (Promedio de yields anuales para comparar)
            yearly_divs = dividends.resample("YE").sum()
            if len(yearly_divs) > 1:
                avg_price = hist["Close"].mean()
                yield_hist = (yearly_divs.mean() / avg_price) * 100

        return {
            "Ticker": ticker,
            "Price": price,
            "Yield": yield_value,
            "Yield_Hist": yield_hist,
            "PE": None,
            "Payout": None,
            "Sector": "Cargando...",
            "Drawdown": (price - high_all) / high_all * 100,
            "Dist_Low": (price - low_52) / low_52 * 100,
            "hist_df": hist
        }
    except:
        return None

def fetch_extra_data(ticker):
    try:
        stock = yf.Ticker(ticker, session=session)
        info = stock.info
        
        # Payout Robusto (Calculado si el directo falla)
        payout = info.get("payoutRatio")
        if payout is None:
            eps = info.get("trailingEps")
            div_rate = info.get("dividendRate")
            if eps and div_rate and eps > 0:
                payout = div_rate / eps

        return {
            "PE": info.get("trailingPE"),
            "Payout": payout,
            "Sector": info.get("sector", "N/A")
        }
    except:
        return {}

# =========================
# LOADERS (SINCRONIZADOS)
# =========================
@st.cache_data(ttl=3600)
def load_all_data(tickers):
    # Paso 1: Fast data con pocos workers para evitar bloqueos
    with ThreadPoolExecutor(max_workers=3) as executor:
        base_results = list(executor.map(fetch_fast_data, tickers))
    
    base_data = [r for r in base_results if r]
    
    # Paso 2: Extra data con delay preventivo
    for row in base_data:
        extra = fetch_extra_data(row["Ticker"])
        row.update(extra)
        time.sleep(0.1) # Respeto a la API
        
    return base_data

# =========================
# LÓGICA DE SCORE
# =========================
def calculate_score(row):
    score = 0
    # Yield vs su propia historia (Valor)
    if row["Yield"] and row["Yield_Hist"]:
        if row["Yield"] > row["Yield_Hist"] * 1.15: score += 4
        elif row["Yield"] > row["Yield_Hist"]: score += 2

    if row["Drawdown"] < -25: score += 2
    if row["Dist_Low"] < 8: score += 2

    # Fundamentales
    pe = row["PE"] if row["PE"] and not pd.isna(row["PE"]) else 100
    if pe < 16: score += 3
    elif pe > 32: score -= 2

    payout = row["Payout"] if row["Payout"] and not pd.isna(row["Payout"]) else 0
    if payout > 0.85: score -= 5
    elif payout > 0.70: score -= 2

    return score

# =========================
# APP UI
# =========================
st.title("📊 Dividend Kings PRO: Sistema Híbrido")

with st.spinner("Sincronizando con mercado (usando caché seguro)..."):
    data = load_all_data(DIVIDEND_KINGS)

df = pd.DataFrame(data)
df["Score"] = df.apply(calculate_score, axis=1)
df = df.sort_values("Score", ascending=False)

# --- FILTROS SIDEBAR ---
st.sidebar.header("Configuración de Radar")
min_score = st.sidebar.slider("Score de Calidad Mínimo", -5, 12, 4)
show_sectors = st.sidebar.multiselect("Sectores", df["Sector"].unique(), default=df["Sector"].unique())

df_filtered = df[(df["Score"] >= min_score) & (df["Sector"].isin(show_sectors))]

# --- VISUALIZACIÓN DE TABLA ---
st.subheader(f"Oportunidades Detectadas ({len(df_filtered)})")

# IMPORTANTE: Definimos las columnas a mostrar y su formato
st.dataframe(
    df_filtered.drop(columns=["hist_df"]), # Eliminamos los datos pesados de la vista
    use_container_width=True,
    hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn("Score", min_value=-5, max_value=12, format="%d pts"),
        "Price": st.column_config.NumberColumn("Precio", format="$%.2f"),
        "Yield": st.column_config.NumberColumn("Yield %", format="%.2f%%"),
        "Yield_Hist": st.column_config.NumberColumn("Yield Hist %", format="%.2f%%"),
        "Payout": st.column_config.NumberColumn("Payout Ratio", format="%.1%"),
        "PE": st.column_config.NumberColumn("P/E Ratio", format="%.1f"),
        "Drawdown": st.column_config.NumberColumn("Caída Máx", format="%.1f%%"),
        "Dist_Low": st.column_config.NumberColumn("Dist. Mínimo", format="%.1f%%"),
    }
)

# --- DETALLE Y GRÁFICO ---
st.divider()
if not df_filtered.empty:
    t_sel = st.selectbox("Analizar Ticker en Profundidad", df_filtered["Ticker"])
    d_sel = next(x for x in data if x["Ticker"] == t_sel)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Yield Actual", f"{d_sel['Yield']:.2f}%")
        st.metric("P/E Ratio", f"{d_sel['PE']:.1f}" if d_sel['PE'] else "N/A")
        st.write(f"**Estatus:** {'🟢 Compra' if d_sel['Score'] >= 6 else '🟡 Mantener'}")
    
    with c2:
        h = d_sel["hist_df"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h.index, y=h["Close"], name="Precio", line=dict(color="#00ff00")))
        fig.add_trace(go.Scatter(x=h.index, y=h["Close"].rolling(200).mean(), name="MA200", line=dict(dash='dot')))
        fig.update_layout(title=f"Historial 10 años: {t_sel}", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
