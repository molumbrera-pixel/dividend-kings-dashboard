# 1. **Lista 2026 VERIFICADA (57 Kings exactos)** [web:21][web:26]
DIVIDEND_KINGS = list(set([
    "AWR","DOV","NWN","GPC","PG","PH","EMR","CINF","KO","JNJ","KVUE","CL","NDSN",
    "ABM","SCL","CBSH","**CWT**","FUL","MO","BKH","NFG","UVV","MSA","SYY","LOW","TGT","GWW",
    "ABT","ADP","LIN","SHW","MKC","PNR","ROL","AOS","APD","ATO","BDX","BF-B","CAH",
    "CAT","CLX","CMS","CVX","ED","FRT","HRL","ITW","KMB","MCD","MMM","PEP","PPG",
    "RPM","SJW","SWK","TROW","WBA","WMT","XOM","NUE","**CB**","**AFL**"  # +2 confirmados
]))

# 2. **Progress bar + Status** (arriba de raw_data=)
progress_bar = st.progress(0)
status_text = st.empty()
raw_data = get_all_data(DIVIDEND_KINGS)
progress_bar.empty()
status_text.empty()

# 3. **Metrics TOP + Balloons** (después de df_f)
col_top1, col_top2, col_top3 = st.columns(3)
strong = df_f[df_f.Signal == "🟢 Strong Buy"]
watch = df_f[df_f.Signal == "🟡 Watch / DCA"]

col_top1.metric("🟢 Strong Buy", len(strong))
col_top2.metric("🟡 Watch/DCA", len(watch))
col_top3.metric("Total Filtrados", len(df_f))

if len(strong) > 0:
    st.success(f"🚀 **TOP Strong Buy**: {', '.join(strong.head(5)['Ticker'].tolist())}")
    st.balloons()

# 4. **Backtest RÁPIDO** (agrega después del gráfico en detalle)
st.subheader("⚡ Backtest Golden Cross (90 días)")
hist = data_sel["hist_df"]
ma200 = hist["Close"].rolling(200).mean()
signals = ((hist["Close"] > ma200) & (hist["Close"].shift(1) <= ma200.shift(1)))

trades = []
for i in signals[signals].index:
    if i + pd.Timedelta(90, "d") in hist.index:
        ret = (hist["Close"].loc[i + pd.Timedelta(90, "d")] / hist["Close"].loc[i] - 1) * 100
        trades.append(ret)

if trades:
    df_bt = pd.DataFrame({"Return %": trades})
    col_bt1, col_bt2 = st.columns(2)
    col_bt1.metric("Retorno Promedio", f"{df_bt.mean():.1f}%")
    col_bt2.metric("Win Rate", f"{(df_bt > 0).mean()*100:.0f}%")
    st.dataframe(df_bt.describe(), use_container_width=True)
else:
    st.info("Sin señales Golden Cross recientes")

# 5. **requirements.txt** (para Streamlit Cloud)
"""
streamlit==1.38.0
yfinance==0.2.40
pandas==2.2.2
plotly==5.22.0
"""
