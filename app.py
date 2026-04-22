import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import math

st.set_page_config(layout="wide", page_title="Dividend Kings PRO")

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

        # 🔥 FIX REAL MOS
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

# =========================
# UI
# =========================
display_cols = [
    "Ticker","Sector","Price","Yield","Yield_Hist",
    "Margin_Safety","PE","Payout","Dist_Low","Drawdown","Score"
]

st.dataframe(df[display_cols], use_container_width=True)

# =========================
# TOP 5
# =========================
top5 = df.head()

st.success(f"🚀 Top 5: {', '.join(top5['Ticker'].tolist())}")

for _, row in top5.iterrows():
    mos = row.get("Margin_Safety")
    mos_str = f"{mos:.2f}" if mos and not math.isnan(mos) else "N/A"

    st.write(f"{row['Ticker']} → Score {row['Score']} | Yield {row['Yield']:.2f}% | MOS {mos_str}")
