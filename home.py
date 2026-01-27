import streamlit as st
from supabase import create_client, Client
import os
import time

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Daylight: Command Center",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SETUP CREDENTIALS ---
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
except:
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

if not supabase_url:
    st.error("🚨 System Offline: Database Credentials Missing.")
    st.stop()

supabase: Client = create_client(supabase_url, supabase_key)

# --- HELPER: FETCH STATS ---
def get_system_status():
    """Fetches live counts from the database."""
    try:
        cases = supabase.table("investigations").select("id, title, status", count="exact").eq("status", "Active").execute()
        case_count = len(cases.data)
        active_list = cases.data

        # Safe Count (Fallback to 0 if table empty)
        try: vault_count = supabase.table("news_archive").select("id", count="exact").limit(1).execute().count
        except: vault_count = 0

        try: ev_count = supabase.table("evidence_locker").select("id", count="exact").limit(1).execute().count
        except: ev_count = 0

        return case_count, vault_count, ev_count, active_list
    except:
        return 0, 0, 0, []

def get_flash_traffic():
    """Gets the 3 most recent headlines."""
    try:
        response = supabase.table("news_archive").select("source, title, created_at").order("created_at", desc=True).limit(3).execute()
        return response.data
    except:
        return []

# --- MAIN UI ---

# HEADER
st.title("🦅 PROJECT DAYLIGHT")
st.caption(f"Open Source Intelligence (OSINT) Console | Public Beta | {time.strftime('%Y-%m-%d')}")
st.divider()

# 1. METRICS ROW
case_num, vault_num, ev_num, active_cases = get_system_status()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(label="Active Operations", value=case_num, delta="Live Cases")
with c2:
    st.metric(label="Global Signals", value=vault_num, delta="Intel Feed")
with c3:
    st.metric(label="Secured Evidence", value=ev_num, delta="Files")
with c4:
    st.metric(label="System Status", value="OPERATIONAL", delta_color="normal")

# 2. FLASH TRAFFIC (LATEST INTEL)
st.subheader("⚡ Global Flash Traffic")
recent_news = get_flash_traffic()

if recent_news:
    for news in recent_news:
        st.info(f"**{news['source']}**: {news['title']}")
else:
    st.caption("No recent signals. Go to 'The Vault' to ingest live feeds.")

# 3. ACTIVE OPERATIONS BOARD
st.divider()
st.subheader("📂 Active Operations")

if not active_cases:
    st.warning("No active investigations. Go to 'The Vault' to find leads.")
else:
    cols = st.columns(3)
    for i, case in enumerate(active_cases):
        col = cols[i % 3]
        with col:
            with st.container(border=True):
                st.markdown(f"### 📁 {case['title']}")
                st.caption(f"Status: {case['status']}")
                st.markdown("**Mission:** Extract entities and map connections.")

# 4. ANALYST FIELD GUIDE (ONBOARDING)
st.markdown("---")
with st.expander("📖 **READ ME: Analyst Field Guide (How to use this tool)**", expanded=True):
    st.markdown("""
    Welcome to **Project Daylight**. This is an AI-powered intelligence suite.

    **STEP 1: SCAN THE WORLD 👁️**
    * Go to **'The Vault'** (Sidebar).
    * Click **'Ingest Global Feeds'** to pull live news from US, Russia, China, & Middle East.
    * Find a story you want to track and select **'✨ CREATE NEW CASE'** or assign it to an existing one.

    **STEP 2: INVESTIGATE 🕵️**
    * Go to **'Investigations'** (Sidebar).
    * Open your Case File.
    * **Analyze:** Paste text or URLs into the **Auto-Analyst** to extract People, Organizations, and Links.
    * **Visualize:** Click the **'Network Graph'** tab to see the hidden connections.

    **STEP 3: REPORT 🖨️**
    * Click **'Export Dossier'** to generate a classified PDF report of your findings.
    """)