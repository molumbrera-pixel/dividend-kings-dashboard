import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

st.set_page_config(layout="wide", page_title="Dividend Kings PRO STABLE")

# =========================
# SESSION CON CACHE + RETRIES
# =========================
@st.cache_resource
def get_session():
    session = requests_cache.CachedSession(
        'yahoo_cache',
        expire_after=3600
    )

    session.headers.update({
        'User-Agent': 'Mozilla/5.0'
    })

    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )

    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

session = get_session()

# =========================
# LISTA
# =========================
DIVIDEND_KINGS = sorted(list(set([
    "KO","PG","JNJ","PEP","MCD","LOW","CL","MMM","ABBV","TGT",
    "WMT","XOM","CVX","ADP","LIN","SHW","MKC","ROL","NUE","GPC"
])))

# =========================
# FETCH BULK (CLAVE)
# =========================
def fetch_bulk_data(tickers):
    try:
        data = yf.download(
            tickers=tickers,
            period="10y",
            group_by="ticker",
            threads=False,
            progress=False,
            session=session
        )

        results = []

        for t in tickers:
            try:
                if len(tickers) == 1:
                    hist = data
                else:
                    hist = data[t]

                if hist.empty:
                    continue

                price = hist["Close"].iloc[-1]
                low_52 = hist["Close"].tail(252).min()
                high_all = hist["Close"].max()

                results.append({
                    "Ticker": t,
                    "Price": price,
                    "Yield": 0,
                    "Yield_Hist": None,
                    "PE": None,
                    "Payout": None,
                    "Sector": "Unknown",
                    "Drawdown": (price - high_all) / high_all * 100,
                    "Dist_Low": (price - low_52) / low_52 * 100,
                    "hist_df": hist
                })

            except Exception as e:
                print(f"Error ticker {t}: {e}")
                continue

        return results

    except Exception as e:
        print("Bulk error:", e)
        return []

# =========================
# SCORE
# =========================
def calculate_score(row):
    score = 0

    if pd.notna(row["Yield"]) and row["Yield"] > 3:
        score += 2

    if pd.notna(row["Drawdown"]) and row["Drawdown"] < -30:
        score += 2

    if pd.notna(row["Dist_Low"]) and row["Dist_Low"] < 10:
        score += 2

    pe = row["PE"] if pd.notna(row["PE"]) else 100
    if pe < 15:
        score += 2
    elif pe > 35:
        score -= 2

    payout = row["Payout"] if pd.notna(row["Payout"]) else 0
    if payout > 0.9:
        score -= 3

    return score

# =========================
# APP
# =========================
st.title("📊 Dividend Kings PRO STABLE")

with st.spinner("Cargando datos de mercado..."):
    data = fetch_bulk_data(DIVIDEND_KINGS)

if not data:
    st.error("⚠️ Yahoo bloqueó la conexión. Reintenta.")
    st.stop()

df = pd.DataFrame(data)

# =========================
# LIMPIEZA SEGURA
# =========================
cols = ["Yield","PE","Payout","Drawdown","Dist_Low"]

for c in cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df["Sector"] = df["Sector"].fillna("Unknown")

# =========================
# SCORE
# =========================
df["Score"] = df.apply(calculate_score, axis=1)
df = df.sort_values("Score", ascending=False)

# =========================
# FILTROS
# =========================
st.sidebar.header("Filtros")

min_score = st.sidebar.slider("Score mínimo", -5, 10, 2)

df_f = df[df["Score"] >= min_score]

# =========================
# TABLA
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
        st.metric("Precio", f"${d['Price']:.2f}")
        st.metric("Score", int(d["Score"]))

    with col2:
        hist = d["hist_df"].copy()
        hist["MA200"] = hist["Close"].rolling(200).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], name="Precio"))
        fig.add_trace(go.Scatter(x=hist.index, y=hist["MA200"], name="MA200"))

        st.plotly_chart(fig, use_container_width=True)
