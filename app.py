import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

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

        # Mejor señal con Close
        low_52 = hist["Close"].rolling(252).min().iloc[-1]
        high_all = hist["Close"].max()

        pe = info.get("trailingPE")
        payout = info.get("payoutRatio")
        sector = info.get("sector", "N/A")

        # 🔥 FALLBACK PAYOUT
        if payout is None:
            eps = info.get("trailingEps")
            div_rate = info.get("dividendRate")
            if eps and eps > 0 and div_rate:
                payout = div_rate / eps

        # Normalizar payout (0–1)
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

        # 🔥 MARGIN OF SAFETY
        if yield_hist and yield_value:
            margin_safety = yield_value / yield_hist

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Price": round(price, 2),
            "Yield": round(yield_value, 2),
            "Yield_Hist": round(yield_hist, 2) if yield_hist else None,
            "Margin_Safety": round(margin_safety, 2) if margin_safety else None,
            "PE": pe,
            "Payout": payout,
            "Dist_Low": round(distance_low, 1),
            "Drawdown": round(drawdown, 1),
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
# SCORE AVANZADO
# =========================
def calculate_score(row):
    score = 0

    # Margin of Safety (clave)
    if row["Margin_Safety"]:
        if row["Margin_Safety"] > 1.3:
            score += 4
        elif row["Margin_Safety"] > 1.1:
            score += 2

    # Yield relativo
    if row['Yield'] and row['Yield_Hist']:
        ratio = row['Yield'] / row['Yield_Hist']
        if ratio > 1.2:
            score += 2

    # Caída inteligente
    if row['Drawdown'] < -30:
        if row['Yield'] > 2:
            score += 3
        else:
            score -= 2

    # Cercanía a mínimos
    if row['Dist_Low'] < 10:
        score += 2

    # Valuación (fix bug None)
    pe = row['PE'] if row['PE'] is not None else 100
    if pe < 12:
        score += 3
    elif pe < 18:
        score += 2
    elif pe > 35:
        score -= 3

    # Payout
    payout = row['Payout'] if row['Payout'] else 0
    if payout > 0.9:
        score -= 5
    elif payout > 0.75:
        score -= 2

    # Yield extremo
    if row['Yield'] > 6:
        score -= 2

    # Deterioro
    if row['Yield_Hist'] and row['Yield'] < row['Yield_Hist'] * 0.7:
        score -= 2

    return score

# =========================
# APP
# =========================
st.title("📊 Dividend Kings PRO Dashboard")

with st.spinner("Cargando datos..."):
    raw_data = get_all_data(DIVIDEND_KINGS)

df = pd.DataFrame(raw_data)

if df.empty:
    st.error("No se pudieron cargar datos.")
    st.stop()

df['Score'] = df.apply(calculate_score, axis=1)
df["Score"] = df["Score"].fillna(0)
df = df.sort_values("Score", ascending=False)

display_cols = [
    "Ticker","Sector","Price","Yield","Yield_Hist",
    "Margin_Safety","PE","Payout","Dist_Low","Drawdown","Score"
]

# =========================
# FILTROS
# =========================
st.sidebar.header("🔎 Filtros")

min_yield = st.sidebar.slider("Min Yield (%)", 0.0, 10.0, 2.0)
min_score = st.sidebar.slider("Min Score", int(df["Score"].min()), int(df["Score"].max()), 5)

sector_sel = st.sidebar.multiselect(
    "Sector",
    df["Sector"].dropna().unique(),
    default=df["Sector"].dropna().unique()
)

filtered = df[
    (df["Yield"] >= min_yield) &
    (df["Score"] >= min_score) &
    (df["Sector"].isin(sector_sel))
].sort_values("Score", ascending=False)

# =========================
# SECTORES
# =========================
st.sidebar.subheader("📊 Distribución Sector")

if not filtered.empty:
    sector_counts = filtered["Sector"].value_counts()
    sector_weights = (sector_counts / sector_counts.sum()) * 100
    st.sidebar.bar_chart(sector_weights)

# =========================
# TABLA
# =========================
st.subheader(f"📊 Resultados ({len(filtered)})")
st.dataframe(filtered[display_cols], use_container_width=True)

# =========================
# EXPORT CSV
# =========================
today = datetime.now().strftime("%Y-%m-%d")
filename = f"dividend_kings_{today}.csv"

csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button("📥 Descargar CSV", csv, filename, "text/csv")

# =========================
# TOP 5
# =========================
if not filtered.empty:
    top5 = filtered.head()
    st.success(f"🚀 Top 5: {', '.join(top5['Ticker'].tolist())}")

    for _, row in top5.iterrows():
        st.write(f"{row['Ticker']} → Score: {row['Score']} | Yield: {row['Yield']}% | MOS: {row['Margin_Safety']}")

# =========================
# SCATTER
# =========================
plot_df = filtered.copy()

for col in ["PE", "Yield", "Score"]:
    plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")

plot_df = plot_df.dropna(subset=["PE","Yield","Score"])
plot_df = plot_df[(plot_df["PE"] > 0) & (plot_df["PE"] < 100)]

if not plot_df.empty:
    threshold = plot_df["Score"].quantile(0.7)
    opps = plot_df[plot_df["Score"] >= threshold]

    fig = px.scatter(
        opps,
        x="PE",
        y="Yield",
        size="Score",
        color="Sector",
        hover_name="Ticker",
        title="🎯 Top Opportunities (Top 30%)"
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

            st.write(f"Payout: {data['Payout']:.1%}" if data["Payout"] else "N/A")
            st.write(f"Margin Safety: {data['Margin_Safety']}")
            st.write(f"Sector: {data['Sector']}")

        with col2:
            fig_hist = px.line(data["hist_df"], y="Close", title=ticker)
            st.plotly_chart(fig_hist, use_container_width=True)
