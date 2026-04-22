import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
import math
import time

st.set_page_config(layout="wide", page_title="Dividend Kings PRO ROBUST")

# =========================
# LISTA LIMPIA
# =========================
DIVIDEND_KINGS = list(set([
    "AWR","DOV","NWN","GPC","PG","PH","EMR","CINF","KO","JNJ","CL","NDSN",
    "ABM","SCL","CBSH","HTO","FUL","MO","BKH","NFG","UVV","MSA","SYY","LOW",
    "TGT","GWW","ABT","ADP","LIN","SHW","MKC","PNR","ROL","AOS","APD","ATO",
    "BDX","BF-B","CAH","CAT","CLX","CMS","CVX","ED","FRT","HRL","ITW","KMB",
    "MCD","MMM","PEP","PPG","RPM","SJW","SWK","TROW","WBA","WMT","XOM","NUE"
]))

# =========================
# FETCH ROBUSTO
# =========================
def fetch_ticker_data(ticker, retries=2):
    for attempt in range(retries):
        try:
            time.sleep(0.2)

            stock = yf.Ticker(ticker)

            # 🔥 INFO OPCIONAL
            try:
                info = stock.info
            except:
                info = {}

            hist = stock.history(period="10y", progress=False)

            if hist.empty or len(hist) < 200:
                print(f"{ticker}: datos insuficientes")
                return None

            price = hist["Close"].iloc[-1]

            low_52 = hist["Close"].tail(252).min()
            high_all = hist["Close"].max()

            pe = info.get("trailingPE", None) if isinstance(info, dict) else None
            payout = info.get("payoutRatio", 0) if isinstance(info, dict) else 0
            if payout < 0:
                payout = 0

            sector = info.get("sector", "Unknown") if isinstance(info, dict) else "Unknown"

            # =========================
            # DIVIDENDOS
            # =========================
            dividends = stock.dividends
            yield_value = 0
            yield_hist = None

            if dividends is not None and not dividends.empty:
                dividends.index = pd.to_datetime(dividends.index)

                last_year = dividends[
                    dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))
                ]

                yield_value = (last_year.sum() / price) * 100 if price > 0 else 0

                yearly_div = dividends.resample("YE").sum()
                yearly_yields = []

                for year in yearly_div.index:
                    year_hist = hist[hist.index.year == year.year]
                    if not year_hist.empty:
                        avg_price = year_hist["Close"].mean()
                        yearly_yields.append((yearly_div[year] / avg_price) * 100)

                if yearly_yields:
                    yield_hist = pd.Series(yearly_yields).mean()

            # =========================
            # MOS
            # =========================
            margin_safety = None
            if yield_hist and yield_hist > 0:
                margin_safety = yield_value / yield_hist

            # =========================
            # TECNICO
            # =========================
            ma200 = hist["Close"].rolling(200).mean().iloc[-1]
            trend_ok = price > ma200 if not math.isnan(ma200) else False

            return {
                "Ticker": ticker,
                "Sector": sector,
                "Price": price,
                "Yield": yield_value,
                "Yield_Hist": yield_hist,
                "Margin_Safety": margin_safety,
                "PE": pe,
                "Payout": payout,
                "Drawdown": (price - high_all) / high_all * 100,
                "Dist_Low": (price - low_52) / low_52 * 100 if low_52 else 0,
                "Trend_OK": trend_ok,
                "hist_df": hist
            }

        except Exception as e:
            print(f"Error {ticker} intento {attempt+1}: {e}")
            time.sleep(1)

    return None


# =========================
# LOAD DATA
# =========================
@st.cache_data(ttl=900)
def get_all_data(tickers):
    with ThreadPoolExecutor(max_workers=3):  # 🔥 menos threads = más estable
        results = list(map(fetch_ticker_data, tickers))

    valid = [r for r in results if r]

    print(f"OK: {len(valid)} / {len(tickers)}")

    return valid


# =========================
# PIPELINE
# =========================
def normalize_data(df):
    cols = ["Yield","Yield_Hist","Margin_Safety","PE","Payout","Drawdown","Dist_Low"]

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
# SCORE
# =========================
def calculate_score(row):
    score = 0

    if row.get("Margin_Safety") and row["Margin_Safety"] > 1.2:
        score += 3

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
st.title("📊 Dividend Kings PRO ROBUST")

raw_data = get_all_data(DIVIDEND_KINGS)

if not raw_data:
    st.error("⚠️ No se pudieron cargar datos desde Yahoo Finance")
    st.info("Reintenta en unos segundos (posible rate limit)")
    st.stop()

df = pd.DataFrame(raw_data)
df = normalize_data(df)
df = clean_data(df)

df["Score"] = df.apply(calculate_score, axis=1)
df["Signal"] = df.apply(entry_signal, axis=1)

df = df.sort_values("Score", ascending=False).reset_index(drop=True)

st.dataframe(df, use_container_width=True, hide_index=True)

# =========================
# DETALLE + GRAFICO
# =========================
st.divider()

ticker_sel = st.selectbox("Seleccionar acción", df["Ticker"])

data_sel = next((x for x in raw_data if x["Ticker"] == ticker_sel), None)

if data_sel:
    col1, col2 = st.columns([1,2])

    with col1:
        st.metric("Precio", f"${data_sel['Price']:.2f}")
        st.metric("Yield", f"{data_sel['Yield']:.2f}%")

        mos = data_sel.get("Margin_Safety")
        st.write(f"MOS: {mos:.2f}" if mos else "MOS: N/A")

    with col2:
        hist = data_sel["hist_df"]

        df_plot = hist.copy()
        df_plot["MA200"] = df_plot["Close"].rolling(200).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["Close"], name="Precio"))
        fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["MA200"], name="MA200"))

        st.plotly_chart(fig, use_container_width=True)
