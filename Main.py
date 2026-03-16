import streamlit as st
import requests
import pandas as pd
import time

st.set_page_config(page_title="Kalshi Every Sport Edge Bot", layout="wide", page_icon="🏆")
st.title("Kalshi Every Sport Edge Bot 🏀⚽🏈🏸")
st.markdown("**All sports • All sub-markets • Real-time profit edge flags**")

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"

@st.cache_data(ttl=35)
def fetch_all_sports():
    events = []
    cursor = None
    while True:
        params = {"limit": 200, "with_nested_markets": "true", "status": "open"}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{BASE_URL}/events", params=params)
        data = r.json()
        events.extend(data.get("events", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return events

events = fetch_all_sports()

# Build dataframe
data = []
for e in events:
    for m in e.get("markets", []):
        data.append({
            "Event": e["title"],
            "Market": m["title"],
            "Yes ¢": m.get("yes_price", "N/A"),
            "Implied %": round(m.get("yes_price", 0) / 100 * 100, 1) if m.get("yes_price") else "N/A",
            "Volume 24h": m.get("volume_24h", 0),
            "Ticker": m["ticker"]
        })

df = pd.DataFrame(data)

# Sidebar filters
st.sidebar.header("Filters")
sport_filter = st.sidebar.selectbox(
    "Sport", 
    ["All Sports", "Basketball", "Football", "Soccer", "Tennis", "E-sports", "Golf", "MMA", "Other"]
)
search = st.sidebar.text_input("Search markets (e.g. over, mentions, Sinner, upset)")

if sport_filter != "All Sports":
    df = df[df["Event"].str.contains(sport_filter, case=False)]
if search:
    df = df[df.apply(lambda row: search.lower() in str(row).lower(), axis=1)]

# Main table
st.dataframe(
    df.sort_values("Volume 24h", ascending=False),
    use_container_width=True,
    height=650
)

# Edge Flags
st.subheader("🔥 Profit Edge Flags (Rule-Based)")
col1, col2 = st.columns(2)

with col1:
    for _, row in df.iterrows():
        pct = row["Implied %"]
        vol = row["Volume 24h"]
        title_lower = row["Market"].lower()
        
        if isinstance(pct, float):
            if pct >= 70 and vol > 5000:
                st.success(f"🟢 **Grind Play** → {row['Market']} ({pct}%) — buy & hold")
            elif ("over" in title_lower or "total" in title_lower) and pct < 48:
                st.warning(f"🔴 **Under Bias** → {row['Market']} — historical edge")
            elif vol > 20000 and 35 < pct < 65:
                st.info(f"🔥 **Volume Spike** → {row['Market']} — money moving fast")

with col2:
    for _, row in df.iterrows():
        pct = row["Implied %"]
        vol = row["Volume 24h"]
        title_lower = row["Market"].lower()
        
        if isinstance(pct, float):
            if ("upset" in title_lower or "seed" in title_lower) and pct < 45 and vol > 3000:
                st.info(f"🔵 **Upset Value** → {row['Market']} — mid-range edge")
            elif pct < 40 and vol > 10000:
                st.warning(f"⚠️ **Longshot Watch** → {row['Market']} — high volume cheapie")

st.caption("Refresh page or click button below for latest prices. Deployed free on Streamlit Cloud — no limits.")

if st.button("🔄 Refresh Data Now"):
    st.rerun()
