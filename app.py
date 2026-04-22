import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import time
import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

st.set_page_config(layout="wide", page_title="Dividend Kings PRO STABLE")

# =========================
# SESIÓN SEGURA
# =========================
@st.cache_resource
def get_session():
    session = requests_cache.CachedSession('yahoo_cache', expire_after=3600)
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[429,500,502,503,504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

session = get_session()

# =========================
# LISTA
# =========================
DIVIDEND_KINGS = sorted(list(set([
    "AWR","DOV","NWN","GPC","PG","PH","EMR","CINF","KO","JNJ","CL","NDSN",
    "ABM","SCL","CBSH","FUL","MO","BKH","NFG","UVV","MSA","SYY","LOW",
    "TGT","GWW","ABT","ADP","LIN","SHW","MKC","PNR","ROL","AOS","APD","ATO",
    "BDX","BF-B","CAH","CAT","CLX","CMS","CVX","ED","FRT","HRL","ITW","KMB",
    "MCD","MMM","PEP","PPG","RPM","SJW","SWK","TROW","WBA","WMT","XOM","NUE"
])))

# =========================
# FETCH
# =========================
def fetch_data(ticker):
    try:
        stock = yf.Ticker(ticker, session=session)
        hist = stock.history(period="10y", progress=False)

        if hist.empty or len(hist) < 200:
            return None

        price = hist["Close"].iloc[-1]
        low_52 = hist["Close"].tail(252).min()
        high_all = hist["Close"].max()

        dividends = stock.dividends
        yield_val = 0
        yield_hist = None

        if dividends is not None and not dividends.empty:
            dividends.index = pd.to_datetime(dividends.index).tz_localize(None)

            last_year = dividends[
                dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))
            ]
            yield_val = (last_year.sum() / price) * 100 if price > 0 else 0

            yearly = dividends.resample("YE").sum()

            yearly_yields = []
            for y in yearly.index:
                hist_year = hist[hist.index.year == y.year]
                if not hist_year.empty:
                    avg_price = hist_year["Close"].mean()
                    yearly_yields.append((yearly[y] / avg_price) * 100)

            if yearly_yields:
                yield_hist = pd.Series(yearly_yields).mean()

        # info opcional
        try:
            info = stock.info
        except:
            info = {}

        pe = info.get("trailingPE", None)
        payout = info.get("payoutRatio", None)
        sector = info.get("sector", "Unknown")

        return {
            "Ticker": ticker,
            "Price": price,
            "Yield": yield_val,
            "Yield_Hist": yield_hist,
            "PE": pe,
            "Payout": payout,
            "Sector": sector,
            "Drawdown": (price - high_all) / high_all * 100,
            "Dist_Low": (price - low_52) / low_52 * 100,
            "hist_df": hist
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None


@st.cache_data(ttl=1800)
def load_data(tickers):
    with ThreadPoolExecutor(max_workers=3):
        res = list(map(fetch_data, tickers))
    return [r for r in res if r]

# =========================
# SCORE
# =========================
def calculate_score(row):
    score = 0

    if pd.notna(row["Yield"]) and pd.notna(row["Yield_Hist"]):
        if row["Yield"] > row["Yield_Hist"] * 1.15:
            score += 4
        elif row["Yield"] > row["Yield_Hist"]:
            score += 2

    if pd.notna(row["Drawdown"]) and row["Drawdown"] < -25:
        score += 2

    if pd.notna(row["Dist_Low"]) and row["Dist_Low"] < 8:
        score += 2

    pe = row["PE"] if pd.notna(row["PE"]) else 100
    if pe < 16:
        score += 3
    elif pe > 32:
        score -= 2

    payout = row["Payout"] if pd.notna(row["Payout"]) else 0
    if payout > 0.85:
        score -= 5
    elif payout > 0.70:
        score -= 2

    return score

# =========================
# APP
# =========================
st.title("📊 Dividend Kings PRO STABLE")

with st.spinner("Cargando datos (modo seguro)..."):
    data = load_data(DIVIDEND_KINGS)

if not data:
    st.error("No se pudieron cargar datos (posible bloqueo Yahoo)")
    st.stop()

df = pd.DataFrame(data)

# =========================
# LIMPIEZA SEGURA
# =========================
numeric_cols = ["Yield","Yield_Hist","PE","Payout","Drawdown","Dist_Low"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["Sector"] = df["Sector"].fillna("Unknown")

df = df[(df["Price"] > 0)]

# =========================
# SCORE
# =========================
df["Score"] = df.apply(calculate_score, axis=1)
df = df.sort_values("Score", ascending=False)

# =========================
# FILTROS
# =========================
st.sidebar.header("Filtros")

min_score = st.sidebar.slider("Score mínimo", -5, 12, 4)
sector_filter = st.sidebar.multiselect(
    "Sector",
    df["Sector"].dropna().unique(),
    default=df["Sector"].dropna().unique()
)

df_f = df[
    (df["Score"] >= min_score) &
    (df["Sector"].isin(sector_filter))
]

# =========================
# TABLA SEGURA
# =========================
st.dataframe(
    df_f.drop(columns=["hist_df"]),
    use_container_width=True,
    hide_index=True
)

# =========================
# DETALLE
# =========================
st.divider()

if not df_f.empty:
    ticker = st.selectbox("Seleccionar acción", df_f["Ticker"])
    d = df[df["Ticker"] == ticker].iloc[0]

    col1, col2 = st.columns([1,2])

    with col1:
        st.metric("Yield", f"{d['Yield']:.2f}%")
        st.metric("Score", int(d["Score"]))

    with col2:
        hist = d["hist_df"]
        hist["MA200"] = hist["Close"].rolling(200).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], name="Precio"))
        fig.add_trace(go.Scatter(x=hist.index, y=hist["MA200"], name="MA200"))

        st.plotly_chart(fig, use_container_width=True)
