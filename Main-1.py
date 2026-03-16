import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Kalshi Every Sport Edge Bot",
    layout="wide",
    page_icon="🏆",
    initial_sidebar_state="expanded"
)

st.title("Kalshi Every Sport Edge Bot 🏀⚽🏈🏸")
st.markdown("**All sports • All sub-markets • Real-time profit edge flags**")

# ============================================================================
# Configuration
# ============================================================================
BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
API_TIMEOUT = 10
CACHE_TTL = 35
MAX_RETRIES = 3

# Edge detection thresholds
EDGE_THRESHOLDS = {
    "grind_play_min_pct": 70,
    "grind_play_min_vol": 5000,
    "under_bias_max_pct": 48,
    "under_bias_min_vol": 1000,
    "volume_spike_min_vol": 20000,
    "volume_spike_min_pct": 35,
    "volume_spike_max_pct": 65,
    "upset_value_max_pct": 45,
    "upset_value_min_vol": 3000,
    "longshot_max_pct": 40,
    "longshot_min_vol": 10000,
}

# ============================================================================
# API Functions
# ============================================================================
@st.cache_data(ttl=CACHE_TTL)
def fetch_all_sports_with_retry() -> List[Dict]:
    """Fetch all open sports events from Kalshi API with retry logic."""
    events = []
    cursor = None
    retry_count = 0
    
    while True:
        try:
            params = {
                "limit": 200,
                "with_nested_markets": "true",
                "status": "open"
            }
            if cursor:
                params["cursor"] = cursor
            
            r = requests.get(
                f"{BASE_URL}/events",
                params=params,
                timeout=API_TIMEOUT
            )
            r.raise_for_status()
            
            data = r.json()
            events.extend(data.get("events", []))
            cursor = data.get("cursor")
            
            if not cursor:
                break
                
            retry_count = 0  # Reset on success
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API Error: {e}")
            retry_count += 1
            
            if retry_count >= MAX_RETRIES:
                st.error(f"Failed to fetch data after {MAX_RETRIES} retries. Please try again.")
                return events if events else []
            
            time.sleep(2 ** retry_count)  # Exponential backoff
    
    logger.info(f"Successfully fetched {len(events)} events")
    return events

# ============================================================================
# Data Processing Functions
# ============================================================================
def calculate_implied_percentage(yes_price: Optional[int]) -> Optional[float]:
    """Convert yes_price (in cents) to implied probability percentage."""
    if yes_price is None or yes_price <= 0:
        return None
    return round((yes_price / 100) * 100, 1)

def build_dataframe(events: List[Dict]) -> pd.DataFrame:
    """Transform raw API events into a clean dataframe."""
    data = []
    
    for event in events:
        event_title = event.get("title", "Unknown")
        markets = event.get("markets", [])
        
        for market in markets:
            yes_price = market.get("yes_price")
            implied_pct = calculate_implied_percentage(yes_price)
            
            data.append({
                "Event": event_title,
                "Market": market.get("title", "Unknown"),
                "Yes ¢": yes_price if yes_price else "N/A",
                "Implied %": implied_pct,
                "Volume 24h": market.get("volume_24h", 0),
                "Ticker": market.get("ticker", "N/A"),
                "Category": market.get("category", "Other"),
            })
    
    df = pd.DataFrame(data)
    
    # Data validation
    if df.empty:
        st.warning("No market data available. Please try again later.")
        return df
    
    return df

# ============================================================================
# Edge Detection Functions
# ============================================================================
def detect_edges(df: pd.DataFrame) -> Dict[str, List[Dict]]:
    """Detect various betting edges in the dataframe."""
    edges = {
        "grind_plays": [],
        "under_bias": [],
        "volume_spikes": [],
        "upset_value": [],
        "longshot_watch": [],
    }
    
    for idx, row in df.iterrows():
        pct = row["Implied %"]
        vol = row["Volume 24h"]
        market_lower = str(row["Market"]).lower()
        
        # Skip invalid data
        if not isinstance(pct, float) or pct < 0 or pct > 100:
            continue
        
        # Grind Play: High confidence, good volume
        if pct >= EDGE_THRESHOLDS["grind_play_min_pct"] and vol > EDGE_THRESHOLDS["grind_play_min_vol"]:
            edges["grind_plays"].append({
                "market": row["Market"],
                "pct": pct,
                "vol": vol,
                "ticker": row["Ticker"]
            })
        
        # Under Bias: Historical edge on under bets
        if ("over" in market_lower or "total" in market_lower) and pct < EDGE_THRESHOLDS["under_bias_max_pct"]:
            edges["under_bias"].append({
                "market": row["Market"],
                "pct": pct,
                "vol": vol,
                "ticker": row["Ticker"]
            })
        
        # Volume Spike: Unusual activity in mid-range odds
        if (vol > EDGE_THRESHOLDS["volume_spike_min_vol"] and
            EDGE_THRESHOLDS["volume_spike_min_pct"] < pct < EDGE_THRESHOLDS["volume_spike_max_pct"]):
            edges["volume_spikes"].append({
                "market": row["Market"],
                "pct": pct,
                "vol": vol,
                "ticker": row["Ticker"]
            })
        
        # Upset Value: Underdog plays with decent volume
        if ("upset" in market_lower or "seed" in market_lower) and pct < EDGE_THRESHOLDS["upset_value_max_pct"] and vol > EDGE_THRESHOLDS["upset_value_min_vol"]:
            edges["upset_value"].append({
                "market": row["Market"],
                "pct": pct,
                "vol": vol,
                "ticker": row["Ticker"]
            })
        
        # Longshot Watch: Cheap prices with significant volume
        if pct < EDGE_THRESHOLDS["longshot_max_pct"] and vol > EDGE_THRESHOLDS["longshot_min_vol"]:
            edges["longshot_watch"].append({
                "market": row["Market"],
                "pct": pct,
                "vol": vol,
                "ticker": row["Ticker"]
            })
    
    return edges

# ============================================================================
# Main Application
# ============================================================================
try:
    # Fetch data
    events = fetch_all_sports_with_retry()
    
    if not events:
        st.error("No data available. Please refresh the page.")
        st.stop()
    
    # Build dataframe
    df = build_dataframe(events)
    
    if df.empty:
        st.stop()
    
    # Sidebar filters
    st.sidebar.header("⚙️ Filters & Settings")
    
    sports = sorted(df["Event"].unique().tolist())
    sport_filter = st.sidebar.selectbox(
        "Sport",
        ["All Sports"] + sports,
        index=0
    )
    
    search = st.sidebar.text_input(
        "Search markets",
        placeholder="e.g., over, upset, Sinner"
    )
    
    volume_threshold = st.sidebar.slider(
        "Minimum Volume (24h)",
        min_value=0,
        max_value=int(df["Volume 24h"].max()),
        value=0,
        step=1000
    )
    
    # Apply filters
    filtered_df = df.copy()
    
    if sport_filter != "All Sports":
        filtered_df = filtered_df[filtered_df["Event"] == sport_filter]
    
    if search:
        mask = filtered_df.apply(
            lambda row: search.lower() in str(row).lower(),
            axis=1
        )
        filtered_df = filtered_df[mask]
    
    filtered_df = filtered_df[filtered_df["Volume 24h"] >= volume_threshold]
    
    # Display stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Markets", len(filtered_df))
    with col2:
        st.metric("Total Volume (24h)", f"${filtered_df['Volume 24h'].sum():,.0f}")
    with col3:
        st.metric("Avg Implied %", f"{filtered_df['Implied %'].mean():.1f}%")
    with col4:
        st.metric("Last Updated", datetime.now().strftime("%H:%M:%S"))
    
    st.divider()
    
    # Main table
    st.subheader("📊 All Markets")
    st.dataframe(
        filtered_df.sort_values("Volume 24h", ascending=False),
        use_container_width=True,
        height=500,
        column_config={
            "Volume 24h": st.column_config.NumberColumn(format="$%d"),
            "Implied %": st.column_config.ProgressColumn(min_value=0, max_value=100),
        }
    )
    
    st.divider()
    
    # Edge detection
    st.subheader("🔥 Profit Edge Flags")
    edges = detect_edges(filtered_df)
    
    # Display edges in columns
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🟢 Grind Plays (High Confidence)")
        if edges["grind_plays"]:
            for edge in sorted(edges["grind_plays"], key=lambda x: x["vol"], reverse=True)[:5]:
                st.success(
                    f"**{edge['market']}**\n"
                    f"Implied: {edge['pct']}% | Volume: ${edge['vol']:,}\n"
                    f"`{edge['ticker']}`"
                )
        else:
            st.info("No grind plays detected right now.")
        
        st.markdown("### 🔴 Under Bias")
        if edges["under_bias"]:
            for edge in sorted(edges["under_bias"], key=lambda x: x["vol"], reverse=True)[:5]:
                st.warning(
                    f"**{edge['market']}**\n"
                    f"Implied: {edge['pct']}% | Volume: ${edge['vol']:,}\n"
                    f"`{edge['ticker']}`"
                )
        else:
            st.info("No under bias detected right now.")
    
    with col2:
        st.markdown("### 🔥 Volume Spikes")
        if edges["volume_spikes"]:
            for edge in sorted(edges["volume_spikes"], key=lambda x: x["vol"], reverse=True)[:5]:
                st.info(
                    f"**{edge['market']}**\n"
                    f"Implied: {edge['pct']}% | Volume: ${edge['vol']:,}\n"
                    f"`{edge['ticker']}`"
                )
        else:
            st.info("No volume spikes detected right now.")
        
        st.markdown("### 🔵 Upset Value")
        if edges["upset_value"]:
            for edge in sorted(edges["upset_value"], key=lambda x: x["vol"], reverse=True)[:5]:
                st.info(
                    f"**{edge['market']}**\n"
                    f"Implied: {edge['pct']}% | Volume: ${edge['vol']:,}\n"
                    f"`{edge['ticker']}`"
                )
        else:
            st.info("No upset value detected right now.")
    
    st.markdown("### ⚠️ Longshot Watch")
    if edges["longshot_watch"]:
        cols = st.columns(min(3, len(edges["longshot_watch"])))
        for idx, edge in enumerate(sorted(edges["longshot_watch"], key=lambda x: x["vol"], reverse=True)[:6]):
            with cols[idx % 3]:
                st.warning(
                    f"**{edge['market']}**\n"
                    f"Implied: {edge['pct']}% | Volume: ${edge['vol']:,}\n"
                    f"`{edge['ticker']}`"
                )
    else:
        st.info("No longshot plays detected right now.")
    
    st.divider()
    st.caption("💡 Refresh page or click button below for latest prices. Deployed free on Streamlit Cloud.")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🔄 Refresh Data Now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with col2:
        st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

except Exception as e:
    logger.exception("Unexpected error in main application")
    st.error(f"An unexpected error occurred: {str(e)}")
    st.info("Please refresh the page and try again.")