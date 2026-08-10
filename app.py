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
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timezone
import anthropic
import feedparser
import swisseph as swe

# ----------------------------
# TECHNICAL INDICATOR FUNCTIONS (pure pandas, no external TA library needed)
# ----------------------------
def calc_rsi(close, length=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def calc_sma(close, length):
    return close.rolling(window=length, min_periods=length).mean()

def calc_bbands(close, length=20, std_mult=2):
    mid = close.rolling(window=length, min_periods=length).mean()
    std = close.rolling(window=length, min_periods=length).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return upper, mid, lower

# ----------------------------
# NEWS SENTIMENT (free RSS feeds + keyword-based scoring, no paid API)
# ----------------------------
NEWS_FEEDS = {
    "India (NSE)": "https://www.moneycontrol.com/rss/marketreports.xml",
    "USA": "https://finance.yahoo.com/news/rssindex",
    "Japan": "https://finance.yahoo.com/news/rssindex",
    "China": "https://finance.yahoo.com/news/rssindex",
}

POSITIVE_WORDS = [
    "rally", "gain", "gains", "surge", "surges", "bullish", "profit", "profits",
    "growth", "high", "highs", "strong", "upbeat", "soar", "soars", "rise", "rises",
    "rebound", "record", "boost", "positive", "outperform", "upgrade", "buy",
]
NEGATIVE_WORDS = [
    "fall", "falls", "drop", "drops", "crash", "bearish", "loss", "losses",
    "decline", "declines", "weak", "plunge", "plunges", "sell-off", "selloff",
    "recession", "slump", "slumps", "downgrade", "sell", "negative", "fear", "fears",
    "concern", "concerns", "cut", "cuts", "warning",
]

@st.cache_data(ttl=900)
def fetch_news(country):
    url = NEWS_FEEDS.get(country)
    if not url:
        return []
    try:
        feed = feedparser.parse(url)
        headlines = [entry.title for entry in feed.entries[:12]]
        return headlines
    except Exception:
        return []

def score_headline(headline):
    text = headline.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    return pos - neg

def analyze_news(headlines):
    if not headlines:
        return 0, "🟡 Neutral (no news mila)", []
    scored = [(h, score_headline(h)) for h in headlines]
    total = sum(s for _, s in scored)
    if total > 1:
        verdict = "🟢 Positive"
    elif total < -1:
        verdict = "🔴 Negative"
    else:
        verdict = "🟡 Neutral/Mixed"
    return total, verdict, scored

# ----------------------------
# ASTROLOGY MODULE (Graha positions + Graha Bala / dignity)
# ----------------------------
SIGNS = ["Mesh (Aries)", "Vrishabh (Taurus)", "Mithun (Gemini)", "Kark (Cancer)",
         "Simha (Leo)", "Kanya (Virgo)", "Tula (Libra)", "Vrishchik (Scorpio)",
         "Dhanu (Sagittarius)", "Makar (Capricorn)", "Kumbh (Aquarius)", "Meen (Pisces)"]

NAKSHATRAS = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
              "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
              "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
              "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
              "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]

PLANET_IDS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY, "Venus": swe.VENUS,
    "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE,
}

# Uccha (exaltation) sign index for each planet
EXALTATION = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3, "Venus": 11, "Saturn": 6}
# Neech (debilitation) = opposite sign
DEBILITATION = {p: (s + 6) % 12 for p, s in EXALTATION.items()}
# Swakshetra (own sign)
OWN_SIGNS = {
    "Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5],
    "Jupiter": [8, 11], "Venus": [1, 6], "Saturn": [9, 10],
}
BENEFICS = ["Jupiter", "Venus", "Mercury", "Moon"]
MALEFICS = ["Sun", "Mars", "Saturn", "Rahu"]

@st.cache_data(ttl=1800)
def get_planet_positions():
    now = datetime.now(timezone.utc)
    jd = swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60)
    positions = {}
    for name, pid in PLANET_IDS.items():
        lon = swe.calc_ut(jd, pid, swe.FLG_MOSEPH)[0][0]
        sign = int(lon // 30)
        deg_in_sign = lon % 30
        nak_index = int(lon // (360 / 27)) % 27
        positions[name] = {"lon": lon, "sign": sign, "deg": deg_in_sign, "nakshatra": nak_index}
    rahu_lon = positions["Rahu"]["lon"]
    ketu_lon = (rahu_lon + 180) % 360
    positions["Ketu"] = {
        "lon": ketu_lon, "sign": int(ketu_lon // 30), "deg": ketu_lon % 30,
        "nakshatra": int(ketu_lon // (360 / 27)) % 27,
    }
    return positions

def dignity_score(planet, sign):
    if EXALTATION.get(planet) == sign:
        return 2, "Uchcha (exalted)"
    if DEBILITATION.get(planet) == sign:
        return -2, "Neech (debilitated)"
    if sign in OWN_SIGNS.get(planet, []):
        return 1, "Swakshetra (own sign)"
    return 0, None

def compute_astro_signal():
    positions = get_planet_positions()
    notes = []
    score = 0
    for planet in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]:
        sign = positions[planet]["sign"]
        d, label = dignity_score(planet, sign)
        if label:
            notes.append(f"{planet} {SIGNS[sign]} rashi me {label} hai")
        if planet in BENEFICS:
            score += d
        elif planet in MALEFICS:
            score -= d
    return score, notes, positions

# ----------------------------
# ASHTAVARGA MODULE (Sarvashtakvarga - classical Parashari bindu system)
# ----------------------------
EXCHANGE_LOCATIONS = {
    "India (NSE)": (18.9298, 72.8354),   # Mumbai (BSE/NSE)
    "USA": (40.7128, -74.0060),          # New York (NYSE)
    "Japan": (35.6762, 139.6503),        # Tokyo
    "China": (31.2304, 121.4737),        # Shanghai
}

# Classical Ashtakvarga bindu tables: for each planet's own Ashtakvarga,
# houses (counted from each contributor's own position, 1=own sign) that receive a bindu.
ASHTAKVARGA_TABLES = {
    "Sun": {
        "Sun": [1, 2, 4, 7, 8, 9, 10, 11], "Moon": [3, 6, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11], "Mercury": [3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [5, 6, 9, 11], "Venus": [6, 7, 12],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11], "Lagna": [3, 4, 6, 10, 11, 12],
    },
    "Moon": {
        "Sun": [3, 6, 7, 8, 10, 11], "Moon": [1, 3, 6, 7, 10, 11],
        "Mars": [2, 3, 5, 6, 9, 10, 11], "Mercury": [1, 3, 4, 5, 7, 8, 10, 11],
        "Jupiter": [1, 4, 7, 8, 10, 11, 12], "Venus": [3, 4, 5, 7, 9, 10, 11],
        "Saturn": [3, 5, 6, 11], "Lagna": [3, 6, 10, 11],
    },
    "Mars": {
        "Sun": [3, 5, 6, 10, 11], "Moon": [3, 6, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11], "Mercury": [3, 5, 6, 11],
        "Jupiter": [6, 10, 11, 12], "Venus": [6, 8, 11, 12],
        "Saturn": [1, 4, 7, 8, 9, 10, 11], "Lagna": [1, 3, 6, 10, 11],
    },
    "Mercury": {
        "Sun": [5, 6, 9, 11, 12], "Moon": [2, 4, 6, 8, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11], "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [6, 8, 11, 12], "Venus": [1, 2, 3, 4, 5, 8, 9, 11],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11], "Lagna": [1, 2, 4, 6, 8, 10, 11],
    },
    "Jupiter": {
        "Sun": [1, 2, 3, 4, 7, 8, 9, 10, 11], "Moon": [2, 5, 7, 9, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11], "Mercury": [1, 2, 4, 5, 6, 9, 10, 11],
        "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11], "Venus": [2, 5, 6, 9, 10, 11],
        "Saturn": [3, 5, 6, 12], "Lagna": [1, 2, 4, 5, 6, 7, 9, 10, 11],
    },
    "Venus": {
        "Sun": [8, 11, 12], "Moon": [1, 2, 3, 4, 5, 8, 9, 11, 12],
        "Mars": [3, 4, 6, 9, 11, 12], "Mercury": [3, 5, 6, 9, 11],
        "Jupiter": [5, 8, 9, 10, 11], "Venus": [1, 2, 3, 4, 5, 8, 9, 10, 11],
        "Saturn": [3, 4, 5, 8, 9, 10, 11], "Lagna": [1, 2, 3, 4, 5, 8, 9, 11],
    },
    "Saturn": {
        "Sun": [1, 2, 4, 7, 8, 10, 11], "Moon": [3, 6, 11],
        "Mars": [3, 5, 6, 10, 11, 12], "Mercury": [6, 8, 9, 10, 11, 12],
        "Jupiter": [5, 6, 11, 12], "Venus": [6, 11, 12],
        "Saturn": [3, 5, 6, 11], "Lagna": [1, 3, 4, 6, 10, 11],
    },
}

@st.cache_data(ttl=1800)
def get_ascendant_sign(country):
    lat, lon = EXCHANGE_LOCATIONS.get(country, EXCHANGE_LOCATIONS["India (NSE)"])
    now = datetime.now(timezone.utc)
    jd = swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60)
    cusps, ascmc = swe.houses(jd, lat, lon, b'P')
    asc_lon = ascmc[0]
    return int(asc_lon // 30)

def compute_sarvashtakvarga(positions, lagna_sign):
    contributor_signs = {p: positions[p]["sign"] for p in
                          ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]}
    contributor_signs["Lagna"] = lagna_sign

    individual_ashtakvarga = {}
    for planet, table in ASHTAKVARGA_TABLES.items():
        bindus = [0] * 12
        for contributor, house_list in table.items():
            c_sign = contributor_signs[contributor]
            for house in house_list:
                target_sign = (c_sign + house - 1) % 12
                bindus[target_sign] += 1
        individual_ashtakvarga[planet] = bindus

    sarva = [0] * 12
    for planet, bindus in individual_ashtakvarga.items():
        for i in range(12):
            sarva[i] += bindus[i]

    return sarva, individual_ashtakvarga

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
data["RSI"] = calc_rsi(data["Close"], length=14)
data["MACD_line"], data["MACD_signal"], data["MACD_hist"] = calc_macd(data["Close"])
data["SMA20"] = calc_sma(data["Close"], 20)
data["SMA50"] = calc_sma(data["Close"], 50)
data["BB_upper"], data["BB_mid"], data["BB_lower"] = calc_bbands(data["Close"], 20)

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
    if pd.notna(row.get("MACD_line")) and pd.notna(row.get("MACD_signal")):
        if row["MACD_line"] > row["MACD_signal"]:
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
        "prediction nahi, guarantee bilkul nahi.")

# ----------------------------
# NEWS SENTIMENT SECTION
# ----------------------------
st.markdown("---")
st.subheader("📰 News Sentiment")

with st.spinner("News fetch ho raha hai..."):
    headlines = fetch_news(country)

news_score, news_verdict, scored_headlines = analyze_news(headlines)

if headlines:
    st.write(f"**News Sentiment: {news_verdict}** (score: {news_score})")
    with st.expander("Recent headlines dekho"):
        for h, s in scored_headlines:
            tag = "🟢" if s > 0 else ("🔴" if s < 0 else "⚪")
            st.write(f"{tag} {h}")
else:
    st.write("Abhi news fetch nahi ho payi — kuch der baad try karo ya market badal ke dekho.")

st.info("Ye ek simple keyword-based sentiment hai (positive/negative shabdon ki counting) — "
        "AI-level news understanding nahi hai, sirf ek quick signal hai.")

# ----------------------------
# ASTROLOGY SECTION
# ----------------------------
st.markdown("---")
st.subheader("🪐 Graha Sthiti (Planetary Positions)")

with st.spinner("Graha positions calculate ho rahe hain..."):
    astro_score, astro_notes, positions = compute_astro_signal()

astro_verdict = "🟢 Graha Bala Positive" if astro_score > 0 else (
    "🔴 Graha Bala Negative" if astro_score < 0 else "🟡 Graha Bala Neutral")

cols = st.columns(4)
planet_order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"]
for i, p in enumerate(planet_order):
    pos = positions[p]
    with cols[i % 4]:
        st.write(f"**{p}**")
        st.caption(f"{SIGNS[pos['sign']]}\n{pos['deg']:.1f}°\n{NAKSHATRAS[pos['nakshatra']]} nakshatra")

st.write(f"**Graha Bala Signal: {astro_verdict}** (score: {astro_score})")
if astro_notes:
    for n in astro_notes:
        st.write(f"- {n}")
else:
    st.write("- Abhi koi graha uchcha/neech/swakshetra me nahi hai (neutral zone)")

st.info("Ye 'Graha Bala' hai — grahon ki uchcha/neech/swakshetra sthiti par based ek simplified "
        "signal. Ye astrology signal scientifically market movement se prove nahi hai, sirf ek "
        "additional perspective ki tarah treat karo.")

# ----------------------------
# SARVASHTAKVARGA SECTION (Full Ashtavarga)
# ----------------------------
st.markdown("---")
st.subheader("🔯 Sarvashtakvarga (Full Ashtavarga)")

with st.spinner("Ashtakvarga bindu calculate ho rahe hain..."):
    lagna_sign = get_ascendant_sign(country)
    sarva, individual_av = compute_sarvashtakvarga(positions, lagna_sign)

st.caption(f"Lagna (Ascendant) is exchange ki location par abhi: **{SIGNS[lagna_sign]}**")

av_df = pd.DataFrame({"Rashi": SIGNS, "Bindu": sarva})
st.bar_chart(av_df.set_index("Rashi"))

avg_bindu = sum(sarva) / 12
moon_sign = positions["Moon"]["sign"]
sun_sign = positions["Sun"]["sign"]
moon_bindu = sarva[moon_sign]
sun_bindu = sarva[sun_sign]

av_notes = []
if moon_bindu >= avg_bindu + 3:
    av_notes.append(f"Moon jis rashi ({SIGNS[moon_sign]}) me hai, wahan bindu strong hai ({moon_bindu}) — market ka mood supportive ho sakta hai")
    av_signal = 1
elif moon_bindu <= avg_bindu - 3:
    av_notes.append(f"Moon jis rashi ({SIGNS[moon_sign]}) me hai, wahan bindu weak hai ({moon_bindu}) — market ka mood volatile/weak ho sakta hai")
    av_signal = -1
else:
    av_notes.append(f"Moon ki rashi ({SIGNS[moon_sign]}) me bindu average range me hai ({moon_bindu})")
    av_signal = 0

with st.expander("Sarvashtakvarga details dekho (har rashi ka bindu count)"):
    st.dataframe(av_df, use_container_width=True, hide_index=True)
    st.caption(f"Average bindu per rashi: {avg_bindu:.1f} | Total: {sum(sarva)} (classical total ~337 hota hai)")

for n in av_notes:
    st.write(f"- {n}")

st.info("Sarvashtakvarga transiting grahon ki rashi-strength batata hai — classical Vedic astrology "
        "me isse 'kaunsi rashi/samay strong hai' judge karte hain. Ye standard Parashari tables se "
        "banaya gaya hai; agar precision bahut zaroori ho to kisi trusted Jyotish software se "
        "cross-check kar lena. Ye financial prediction nahi hai.")

# ----------------------------
# COMBINED SIGNAL (Technical + News + Astrology + Ashtavarga)
# ----------------------------
astro_contribution = 1 if astro_score > 0 else (-1 if astro_score < 0 else 0)
news_contribution = 1 if news_score > 1 else (-1 if news_score < -1 else 0)
combined_score = score + news_contribution + astro_contribution + av_signal
combined_verdict = "🟢 Overall Bullish" if combined_score > 0 else (
    "🔴 Overall Bearish" if combined_score < 0 else "🟡 Overall Neutral")
st.markdown("---")
st.subheader("🎯 Combined Signal (Technical + News + Astrology + Ashtavarga)")
st.write(f"**{combined_verdict}** (combined score: {combined_score})")
st.caption("Technical + News sentiment + Graha Bala + Sarvashtakvarga — sab mila kar ye score bana hai. "
           "Ye kisi bhi tarah guaranteed prediction nahi hai.")

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
                f"Technical Signal Score: {score} ({verdict})\n"
                f"Technical Notes: {', '.join(notes)}\n"
                f"News Sentiment: {news_verdict} (score: {news_score})\n"
                f"Graha Bala (Astrology) Signal: {astro_verdict} (score: {astro_score})\n"
                f"Astrology Notes: {', '.join(astro_notes) if astro_notes else 'Neutral zone'}\n"
                f"Sarvashtakvarga Moon-sign Bindu: {moon_bindu} (avg: {avg_bindu:.1f})\n"
                f"Combined Signal: {combined_verdict} (score: {combined_score})\n"
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
