import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import math

st.set_page_config(layout="wide", page_title="Dividend Kings PRO")

# =========================
# LISTA
# =========================
DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LOW","MCD","MMM","MO",
    "NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT","TROW",
    "WBA","WMT","XOM","ADP","LIN","SHW","MKC","PNR","ROL"
]

# =========================
# FETCH DATA
# =========================
def fetch_ticker_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="10y")

        if hist.empty:
            return None

        price = hist["Close"].iloc[-1]

        low_52 = hist["Close"].rolling(252).min().iloc[-1]
        high_all = hist["Close"].max()

        pe = info.get("trailingPE")
        payout = info.get("payoutRatio")
        sector = info.get("sector", "N/A")

        # fallback payout
        if payout is None:
            eps = info.get("trailingEps")
            div_rate = info.get("dividendRate")
            if eps and eps > 0 and div_rate:
                payout = div_rate / eps

        if payout and payout > 1:
            payout = payout / 100

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        dividends = stock.dividends
        yield_value = 0
        yield_hist = None
        margin_safety = None

        if dividends is not None and not dividends.empty:
            dividends.index = pd.to_datetime(dividends.index, errors="coerce")
            dividends = dividends.dropna()

            last_year = dividends[dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))]
            yield_value = (last_year.sum() / price) * 100 if price > 0 else 0

            yearly = dividends.resample("YE").sum()

            if len(yearly) > 1:
                avg_price = hist["Close"].mean()
                yield_hist = (yearly.mean() / avg_price) * 100

        if (
            yield_hist is not None and 
            yield_value is not None and 
            yield_hist > 0 and 
            not math.isnan(yield_hist)
        ):
            margin_safety = yield_value / yield_hist

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Price": price,
            "Yield": yield_value,
            "Yield_Hist": yield_hist,
            "Margin_Safety": margin_safety,
            "PE": pe,
            "Payout": payout,
            "Dist_Low": distance_low,
            "Drawdown": drawdown,
            "hist_df": hist
        }

    except:
        return None


@st.cache_data(ttl=3600)
def get_all_data(tickers):
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_ticker_data, tickers)
    return [r for r in results if r is not None]

# =========================
# PIPELINE
# =========================
def normalize_data(df):
    cols = ["Yield","Yield_Hist","Margin_Safety","PE","Payout","Drawdown","Dist_Low"]

    for col in cols:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    df["Payout"] = df["Payout"].fillna(0)
    df["PE"] = df["PE"].fillna(100)
    df["Yield"] = df["Yield"].fillna(0)

    return df

def clean_data(df):
    df = df[df["Price"] > 0]
    df = df[df["PE"] < 150]
    df = df[df["Yield"] < 20]
    return df

# =========================
# SCORE
# =========================
def calculate_score(row):
    score = 0

    mos = row.get("Margin_Safety")
    if mos and not math.isnan(mos):
        if mos > 1.3:
            score += 4
        elif mos > 1.1:
            score += 2

    yield_val = row.get("Yield", 0)
    yield_hist = row.get("Yield_Hist")

    if yield_hist and yield_val:
        if yield_val / yield_hist > 1.2:
            score += 2

    drawdown = row.get("Drawdown", 0)
    if drawdown < -30:
        if yield_val > 2:
            score += 3
        else:
            score -= 2

    if row.get("Dist_Low", 100) < 10:
        score += 2

    pe = row.get("PE", 100)
    if pe < 12:
        score += 3
    elif pe < 18:
        score += 2
    elif pe > 35:
        score -= 3

    payout = row.get("Payout", 0)
    if payout > 0.9:
        score -= 5
    elif payout > 0.75:
        score -= 2

    if yield_val > 6:
        score -= 2

    if yield_hist and yield_val < yield_hist * 0.7:
        score -= 2

    return score

# =========================
# APP
# =========================
st.title("📊 Dividend Kings PRO Dashboard")

raw_data = get_all_data(DIVIDEND_KINGS)
df = pd.DataFrame(raw_data)

df = normalize_data(df)
df = clean_data(df)

df["Score"] = df.apply(calculate_score, axis=1)
df = df.sort_values("Score", ascending=False)

display_cols = [
    "Ticker","Sector","Price","Yield","Yield_Hist",
    "Margin_Safety","PE","Payout","Dist_Low","Drawdown","Score"
]

# =========================
# TABLA
# =========================
st.subheader("📊 Ranking")
st.dataframe(df[display_cols], use_container_width=True)

# =========================
# CSV
# =========================
today = datetime.now().strftime("%Y-%m-%d")
csv = df.to_csv(index=False).encode("utf-8")
st.download_button("📥 Descargar CSV", csv, f"dividend_kings_{today}.csv")

# =========================
# TOP 5
# =========================
top5 = df.head()
st.success(f"🚀 Top 5: {', '.join(top5['Ticker'].tolist())}")

# =========================
# DETALLE + GRAFICO PRO
# =========================
st.divider()

ticker_sel = st.selectbox("Seleccionar acción", df["Ticker"])
data = next((x for x in raw_data if x["Ticker"] == ticker_sel), None)

if data:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.metric("Precio", f"${data.get('Price',0):.2f}")
        st.metric("Yield", f"{data.get('Yield',0):.2f}%")

        payout = data.get("Payout")
        st.write(f"Payout: {payout:.1%}" if payout else "N/A")

        mos = data.get("Margin_Safety")
        mos_str = f"{mos:.2f}" if mos and not math.isnan(mos) else "N/A"
        st.write(f"Margin Safety: {mos_str}")

        st.write(f"Sector: {data.get('Sector','N/A')}")

    with col2:
        hist = data.get("hist_df")

        if hist is not None and not hist.empty:

            df_plot = hist.copy()
            df_plot["MA200"] = df_plot["Close"].rolling(200).mean()
            df_plot["ATH"] = df_plot["Close"].cummax()
            df_plot["Drawdown"] = (df_plot["Close"] - df_plot["ATH"]) / df_plot["ATH"] * 100

            fig = go.Figure()

            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["Close"], name="Precio"))
            fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot["MA200"], name="MA200", line=dict(dash="dash")))

            fig.add_trace(go.Scatter(
                x=df_plot.index,
                y=df_plot["Drawdown"],
                name="Drawdown %",
                fill='tozeroy',
                opacity=0.2,
                yaxis="y2"
            ))

            fig.update_layout(
                template="plotly_dark",
                yaxis2=dict(overlaying='y', side='right', title="Drawdown %")
            )

            st.plotly_chart(fig, use_container_width=True)
