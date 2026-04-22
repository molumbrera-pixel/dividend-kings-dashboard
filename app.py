import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(layout="wide", page_title="Dividend Kings PRO")

DIVIDEND_KINGS = [
    "AWR","ABM","ABBV","ALB","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CL","CINF","CLX","CMS","CVX","DOV","ED","EMR","FRT",
    "GPC","HRL","ITW","JNJ","KMB","KO","LEG","LOW","MCD","MMM",
    "MO","NUE","PEP","PG","PPG","RPM","SJW","SWK","SYY","TGT",
    "TROW","WBA","WMT","XOM","ADP","LIN","SHW","MKC","PNR","ROL"
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
        low_52 = hist["Low"].rolling(252).min().iloc[-1]
        high_all = hist["High"].max()

        pe = info.get("trailingPE")
        payout = info.get("payoutRatio")
        sector = info.get("sector", "N/A")

        distance_low = (price - low_52) / low_52 * 100 if low_52 else 0
        drawdown = (price - high_all) / high_all * 100 if high_all else 0

        dividends = stock.dividends
        yield_value = 0
        yield_hist = None

        if dividends is not None and not dividends.empty:
            dividends.index = pd.to_datetime(dividends.index, errors="coerce")
            dividends = dividends.dropna()

            last_year = dividends[dividends.index > (dividends.index[-1] - pd.DateOffset(years=1))]
            total_div = last_year.sum()

            if price > 0:
                yield_value = (total_div / price) * 100

            yearly = dividends.resample("YE").sum()
            if len(yearly) > 1:
                avg_price = hist["Close"].mean()
                yield_hist = (yearly.mean() / avg_price) * 100

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Price": round(price, 2),
            "Yield": round(yield_value, 2),
            "Yield_Hist": round(yield_hist, 2) if yield_hist else None,
            "PE": pe,
            "Payout": payout,
            "Dist_Low": round(distance_low, 1),
            "Drawdown": round(drawdown, 1),
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
# SCORING
# =========================
def calculate_score(row):
    score = 0

    if row['Yield'] and row['Yield_Hist']:
        if row['Yield'] > row['Yield_Hist'] * 1.1:
            score += 4
        elif row['Yield'] > row['Yield_Hist']:
            score += 2

    if row['Dist_Low'] < 10:
        score += 3

    if row['Drawdown'] < -20:
        score += 2

    payout = row['Payout'] if row['Payout'] else 0
    if payout and payout > 0.9:
        score -= 5
    elif payout and payout > 0.75:
        score -= 2

    pe = row['PE'] if row['PE'] else 100
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
df["Score"] = df["Score"].fillna(0)
df = df.sort_values("Score", ascending=False)

score_min = int(df["Score"].min())
score_max = int(df["Score"].max())

# =========================
# TOP
# =========================
st.subheader("🏆 Top Oportunidades")

st.dataframe(
    df.head(10),
    use_container_width=True,
    column_config={
        "Score": st.column_config.ProgressColumn(
            "Score",
            min_value=score_min,
            max_value=score_max,
        )
    }
)

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
    int(score_min),
    int(score_max),
    5
)

filtered = df[
    (df["Sector"].isin(sector_sel)) &
    (df["Score"] >= min_score)
]

st.subheader(f"Resultados ({len(filtered)})")
st.dataframe(filtered, use_container_width=True)

# =========================
# SCATTER FIXED
# =========================
plot_df = filtered.copy()

for col in ["PE", "Yield", "Score"]:
    plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")

plot_df = plot_df.dropna(subset=["PE", "Yield", "Score"])
plot_df = plot_df[(plot_df["PE"] > 0) & (plot_df["PE"] < 100)]

fig_scatter = px.scatter(
    plot_df,
    x="PE",
    y="Yield",
    size="Score",
    color="Sector",
    hover_name="Ticker",
    title="Atractivo: Valuación vs Rendimiento"
)

st.plotly_chart(fig_scatter, use_container_width=True)

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

            st.write(f"Payout: {data['Payout']:.1%}" if data["Payout"] else "Payout: N/A")
            st.write(f"Sector: {data['Sector']}")

        with col2:
            fig_hist = px.line(data["hist_df"], y="Close", title=ticker)
            st.plotly_chart(fig_hist, use_container_width=True)

# =========================
# BACKTEST SIMPLE
# =========================
st.divider()
st.header("📊 Backtest")

def run_backtest(tickers, start="2018-01-01"):
    prices = yf.download(tickers, start=start)["Close"]
    returns = prices.pct_change().dropna()
    portfolio = returns.mean(axis=1)
    return (1 + portfolio).cumprod()

if st.button("Ejecutar Backtest"):
    bt = run_backtest(DIVIDEND_KINGS)

    if bt is not None:
        fig_bt = px.line(bt, title="Backtest Estrategia (Equal Weight)")
        st.plotly_chart(fig_bt, use_container_width=True)
