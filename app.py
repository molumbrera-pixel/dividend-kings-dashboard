import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import time
import math

st.set_page_config(layout="wide", page_title="Dividend Kings PRO HYBRID")

# =========================
# LISTA
# =========================
DIVIDEND_KINGS = list(set([
    "AWR","DOV","NWN","GPC","PG","PH","EMR","CINF","KO","JNJ","CL","NDSN",
    "ABM","SCL","CBSH","HTO","FUL","MO","BKH","NFG","UVV","MSA","SYY","LOW",
    "TGT","GWW","ABT","ADP","LIN","SHW","MKC","PNR","ROL","AOS","APD","ATO",
    "BDX","BF-B","CAH","CAT","CLX","CMS","CVX","ED","FRT","HRL","ITW","KMB",
    "MCD","MMM","PEP","PPG","RPM","SJW","SWK","TROW","WBA","WMT","XOM","NUE"
]))

def fetch_fast_data(ticker):
    try:
        time.sleep(0.2)

        hist = yf.download(ticker, period="10y", progress=False)

        if hist.empty or len(hist) < 200:
            print(f"{ticker} sin datos")
            return None

        price = hist["Close"].iloc[-1]
        low_52 = hist["Close"].tail(252).min()
        high_all = hist["Close"].max()

        return {
            "Ticker": ticker,
            "Price": price,
            "Yield": 0,
            "PE": None,
            "Payout": None,
            "Sector": "Unknown",
            "Drawdown": (price - high_all) / high_all * 100,
            "Dist_Low": (price - low_52) / low_52 * 100,
            "hist_df": hist
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None


# =========================
# EXTRA FETCH (LENTO)
# =========================
def fetch_extra_data(ticker):
    try:
        stock = yf.Ticker(ticker)

        try:
            info = stock.info
        except:
            return {}

        return {
            "PE": info.get("trailingPE"),
            "Payout": info.get("payoutRatio"),
            "Sector": info.get("sector", "Unknown")
        }

    except:
        return {}


# =========================
# LOADERS
# =========================
@st.cache_data(ttl=600)
def load_fast(tickers):
    with ThreadPoolExecutor(max_workers=2):
        results = list(map(fetch_fast_data, tickers))
    return [r for r in results if r]


@st.cache_data(ttl=1800)
def load_extra(tickers):
    extra = {}
    for t in tickers:
        extra[t] = fetch_extra_data(t)
        time.sleep(0.2)
    return extra


def merge_data(base, extra):
    for row in base:
        t = row["Ticker"]
        if t in extra:
            for k, v in extra[t].items():
                if v is not None:
                    row[k] = v
    return base


# =========================
# PIPELINE
# =========================
def normalize_data(df):
    cols = ["Yield","PE","Payout","Drawdown","Dist_Low"]
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Sector"] = df["Sector"].fillna("Unknown")
    df["PE"] = df["PE"].fillna(100)
    df["Payout"] = df["Payout"].fillna(0)
    df["Yield"] = df["Yield"].fillna(0)

    return df


def clean_data(df):
    return df[(df["Price"] > 0) & (df["Yield"] < 20) & (df["PE"] < 150)]


# =========================
# SCORE + SIGNAL
# =========================
def calculate_score(row):
    score = 0

    if row["Yield"] > 3:
        score += 2

    if row["Drawdown"] < -30:
        score += 2

    if row["Dist_Low"] < 10:
        score += 1

    if row["PE"] < 15:
        score += 2
    elif row["PE"] > 35:
        score -= 2

    if row["Payout"] > 0.9:
        score -= 3

    return score


def entry_signal(row):
    if row["Score"] >= 5:
        return "🟢 Strong Buy"
    elif row["Score"] >= 3:
        return "🟡 Watch / DCA"
    else:
        return "🔴 Avoid"


# =========================
# APP
# =========================
st.title("📊 Dividend Kings PRO HYBRID")

# ⚡ FASE 1
raw_data = load_fast(DIVIDEND_KINGS)

if not raw_data:
    st.error("No se pudieron cargar datos base")
    st.stop()

st.success("⚡ Datos base cargados")

# 🧠 FASE 2
with st.spinner("Enriqueciendo datos..."):
    extra_data = load_extra([x["Ticker"] for x in raw_data])

raw_data = merge_data(raw_data, extra_data)

# =========================
# DATAFRAME
# =========================
df = pd.DataFrame(raw_data)
df = normalize_data(df)
df = clean_data(df)

df["Score"] = df.apply(calculate_score, axis=1)
df["Signal"] = df.apply(entry_signal, axis=1)

df = df.sort_values("Score", ascending=False)

# =========================
# FILTROS
# =========================
col1, col2 = st.columns(2)

min_score = col1.slider("Score mínimo", 0, 10, 0)
signal_filter = col2.multiselect(
    "Señal",
    df["Signal"].unique(),
    default=df["Signal"].unique()
)

df_f = df[
    (df["Score"] >= min_score) &
    (df["Signal"].isin(signal_filter))
]

st.dataframe(df_f, use_container_width=True)

# =========================
# DETALLE + GRAFICO
# =========================
st.divider()

ticker_sel = st.selectbox("Seleccionar acción", df_f["Ticker"])

data_sel = next((x for x in raw_data if x["Ticker"] == ticker_sel), None)

if data_sel:
    col1, col2 = st.columns([1,2])

    with col1:
        st.metric("Precio", f"${data_sel['Price']:.2f}")
        st.metric("Yield", f"{data_sel['Yield']:.2f}%")
        st.write(f"Sector: {data_sel.get('Sector','N/A')}")

    with col2:
        hist = data_sel["hist_df"]

        df_plot = hist.copy()
        df_plot["MA200"] = df_plot["Close"].rolling(200).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["Close"], name="Precio"))
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["MA200"], name="MA200"))

        st.plotly_chart(fig, use_container_width=True)
