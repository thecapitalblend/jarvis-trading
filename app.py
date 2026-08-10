"""
JARVIS TRADING ASSISTANT
=========================
Ek AI-based trading analysis dashboard jo Hindi me baat karta hai.

CHALANE KA TAREEKA (Setup Instructions):
1. Python install karo (python.org se, version 3.10+)
2. Terminal/Command Prompt me is folder me jao:
   cd jarvis-trading
3. Packages install karo:
   pip install -r requirements.txt
4. Anthropic API key lo (console.anthropic.com se, free credits milte hain)
5. App chalao:
   streamlit run app.py
6. Browser me khud khul jayega -> http://localhost:8501

DISCLAIMER: Ye tool sirf educational/research purpose ke liye hai.
Ye financial advice NAHI hai. Trading me risk hota hai, apni research
khud bhi karo aur zaroorat ho to SEBI-registered advisor se consult karo.
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from datetime import datetime
import anthropic

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(page_title="Jarvis Trading Assistant", layout="wide", page_icon="📈")

# ----------------------------
# MARKET / TICKER OPTIONS
# ----------------------------
MARKETS = {
    "India (NSE)": {
        "Nifty 50": "^NSEI",
        "Sensex": "^BSESN",
        "Reliance": "RELIANCE.NS",
        "TCS": "TCS.NS",
        "HDFC Bank": "HDFCBANK.NS",
        "Infosys": "INFY.NS",
    },
    "USA": {
        "Dow Jones": "^DJI",
        "Nasdaq": "^IXIC",
        "S&P 500": "^GSPC",
        "Apple": "AAPL",
        "Tesla": "TSLA",
        "Microsoft": "MSFT",
    },
    "Japan": {
        "Nikkei 225": "^N225",
        "Toyota": "7203.T",
        "Sony": "6758.T",
    },
    "China": {
        "Shanghai Composite": "000001.SS",
        "Shenzhen Component": "399001.SZ",
        "Alibaba": "BABA",
    },
}

# ----------------------------
# SIDEBAR - SELECTIONS
# ----------------------------
st.sidebar.title("⚙️ Settings")
country = st.sidebar.selectbox("Market chuno / Select Market", list(MARKETS.keys()))
instrument = st.sidebar.selectbox("Stock/Index chuno", list(MARKETS[country].keys()))
ticker_symbol = MARKETS[country][instrument]

period = st.sidebar.selectbox(
    "Time period", ["5d", "1mo", "3mo", "6mo", "1y"], index=2
)
interval = st.sidebar.selectbox(
    "Interval", ["15m", "1h", "1d"], index=2,
    help="Note: 15m/1h data sirf recent dinon ke liye available hoti hai (yfinance limit)"
)

api_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
if not api_key:
    api_key = st.sidebar.text_input("Anthropic API Key (Jarvis chat ke liye)", type="password")
    st.sidebar.caption("API key console.anthropic.com se milegi. Kisi ke saath share mat karo.")
else:
    st.sidebar.success("API Key connected ✅ (Streamlit Secrets se)")

st.sidebar.markdown("---")
st.sidebar.caption("⚠️ Ye data 15-20 min delayed ho sakta hai (free source). "
                    "Ye tool financial advice nahi deta, sirf analysis dikhata hai.")

# ----------------------------
# MAIN TITLE
# ----------------------------
st.title("🤖 Jarvis Trading Assistant")
st.caption(f"Live view: **{instrument}** ({ticker_symbol}) — {country}")

# ----------------------------
# FETCH DATA
# ----------------------------
@st.cache_data(ttl=300)
def fetch_data(symbol, period, interval):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(inplace=True)
    return df

with st.spinner("Data fetch ho raha hai..."):
    try:
        data = fetch_data(ticker_symbol, period, interval)
    except Exception as e:
        st.error(f"Data fetch nahi ho paya: {e}")
        st.stop()

if data.empty:
    st.warning("Is combination ke liye data nahi mila. Time period ya interval badal ke dekho.")
    st.stop()

# ----------------------------
# TECHNICAL INDICATORS
# ----------------------------
data["RSI"] = ta.rsi(data["Close"], length=14)
macd = ta.macd(data["Close"])
data = pd.concat([data, macd], axis=1)
data["SMA20"] = ta.sma(data["Close"], length=20)
data["SMA50"] = ta.sma(data["Close"], length=50)
bbands = ta.bbands(data["Close"], length=20)
data = pd.concat([data, bbands], axis=1)

latest = data.iloc[-1]

# ----------------------------
# TOP METRICS
# ----------------------------
col1, col2, col3, col4 = st.columns(4)
change = latest["Close"] - data.iloc[-2]["Close"]
pct_change = (change / data.iloc[-2]["Close"]) * 100
col1.metric("Current Price", f"{latest['Close']:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
col2.metric("RSI (14)", f"{latest['RSI']:.1f}" if pd.notna(latest['RSI']) else "N/A")
col3.metric("SMA 20", f"{latest['SMA20']:.2f}" if pd.notna(latest['SMA20']) else "N/A")
col4.metric("SMA 50", f"{latest['SMA50']:.2f}" if pd.notna(latest['SMA50']) else "N/A")

# ----------------------------
# CANDLESTICK CHART
# ----------------------------
fig = go.Figure(data=[go.Candlestick(
    x=data.index, open=data["Open"], high=data["High"],
    low=data["Low"], close=data["Close"], name="Price"
)])
fig.add_trace(go.Scatter(x=data.index, y=data["SMA20"], name="SMA 20", line=dict(width=1)))
fig.add_trace(go.Scatter(x=data.index, y=data["SMA50"], name="SMA 50", line=dict(width=1)))
fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)

# ----------------------------
# SIMPLE RULE-BASED SIGNAL SCORE
# ----------------------------
def compute_signal(row):
    score = 0
    notes = []
    if pd.notna(row.get("RSI")):
        if row["RSI"] < 30:
            score += 1; notes.append("RSI oversold hai (bullish sign)")
        elif row["RSI"] > 70:
            score -= 1; notes.append("RSI overbought hai (bearish sign)")
    if pd.notna(row.get("SMA20")) and pd.notna(row.get("SMA50")):
        if row["SMA20"] > row["SMA50"]:
            score += 1; notes.append("Short-term trend upar hai (SMA20 > SMA50)")
        else:
            score -= 1; notes.append("Short-term trend niche hai (SMA20 < SMA50)")
    macd_col = [c for c in row.index if c.startswith("MACD_")]
    signal_col = [c for c in row.index if c.startswith("MACDs_")]
    if macd_col and signal_col and pd.notna(row[macd_col[0]]) and pd.notna(row[signal_col[0]]):
        if row[macd_col[0]] > row[signal_col[0]]:
            score += 1; notes.append("MACD bullish crossover ke paas hai")
        else:
            score -= 1; notes.append("MACD bearish zone me hai")
    return score, notes

score, notes = compute_signal(latest)
verdict = "🟢 Halka Bullish" if score > 0 else ("🔴 Halka Bearish" if score < 0 else "🟡 Neutral")

st.subheader("📊 Technical Summary")
st.write(f"**Overall Signal: {verdict}** (score: {score})")
for n in notes:
    st.write(f"- {n}")

st.info("Ye sirf technical indicators ka rule-based summary hai — "
        "prediction nahi, guarantee bilkul nahi. News aur astrology module abhi jodna baaki hai.")

# ----------------------------
# JARVIS CHAT (Hindi)
# ----------------------------
st.markdown("---")
st.subheader("🗣️ Jarvis se baat karo")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

user_msg = st.text_input("Apna sawaal Hindi me likho...", key="user_input")

if st.button("Bhejo") and user_msg:
    if not api_key:
        st.warning("Pehle sidebar me apni Anthropic API key daalo.")
    else:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            context = (
                f"Stock/Index: {instrument} ({ticker_symbol})\n"
                f"Current Price: {latest['Close']:.2f}\n"
                f"RSI: {latest['RSI']:.1f}\n"
                f"SMA20: {latest['SMA20']:.2f}, SMA50: {latest['SMA50']:.2f}\n"
                f"Signal Score: {score} ({verdict})\n"
                f"Notes: {', '.join(notes)}\n"
            )
            system_prompt = (
                "Aap 'Jarvis' hain, ek trading analysis assistant. Hamesha Hindi (Devanagari script) "
                "me jawab do, dosti aur clarity ke saath. Aapko diye gaye technical data ke aadhar par "
                "sawalon ka jawab do. Kabhi bhi guaranteed prediction mat do ya 'paisa lagao' jaisi "
                "financial advice mat do — sirf data explain karo aur risks yaad dilao. Aap financial "
                "advisor nahi hain."
            )
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Data:\n{context}\n\nMera sawaal: {user_msg}"
                }]
            )
            reply = response.content[0].text
            st.session_state.chat_history.append(("user", user_msg))
            st.session_state.chat_history.append(("jarvis", reply))
        except Exception as e:
            st.error(f"Jarvis se connect nahi ho paya: {e}")

for role, msg in reversed(st.session_state.chat_history):
    if role == "user":
        st.markdown(f"**Aap:** {msg}")
    else:
        st.markdown(f"**Jarvis:** {msg}")
