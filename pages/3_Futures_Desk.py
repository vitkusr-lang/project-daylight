import streamlit as st
from supabase import create_client, Client
import datetime
import time
import os

st.set_page_config(page_title="Daylight: Futures Desk", page_icon="🔮", layout="wide")

# --- CREDENTIALS (Robust for Replit & Cloud) ---
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
except:
    # Fallback for Replit environment variables
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

if not supabase_url:
    st.error("🚨 System Offline: Database Credentials Missing.")
    st.stop()

supabase: Client = create_client(supabase_url, supabase_key)

# --- HELPER FUNCTIONS ---
def get_user_score(username):
    """Fetch user score or create if new."""
    try:
        data = supabase.table("analyst_scores").select("score").eq("user_name", username).execute().data
        if data:
            return data[0]['score']
        else:
            # New user gets 1000 points
            supabase.table("analyst_scores").insert({"user_name": username, "score": 1000}).execute()
            return 1000
    except Exception as e:
        return 1000

def place_bet(username, claim, deadline, confidence, wager):
    """Record the prediction and deduct points."""
    current_score = get_user_score(username)
    if wager > current_score:
        return False, "Insufficient funds! You cannot bet what you do not have."

    # 1. Deduct points immediately (Escrow)
    new_score = current_score - wager
    supabase.table("analyst_scores").update({"score": new_score}).eq("user_name", username).execute()

    # 2. Record Prediction
    data = {
        "user_name": username,
        "claim": claim,
        "deadline": str(deadline),
        "confidence": confidence,
        "wager": wager,
        "status": "Open"
    }
    supabase.table("predictions").insert(data).execute()
    return True, "Prediction Locked."

def resolve_bet(pred_id, won: bool):
    """Payout if correct, simply close if wrong."""
    # Fetch prediction details
    pred = supabase.table("predictions").select("*").eq("id", pred_id).execute().data[0]
    user = pred['user_name']
    wager = pred['wager']

    if won:
        # User gets wager back + profit (Simple 1:1 payout for MVP)
        winnings = wager * 2
        current = get_user_score(user)
        supabase.table("analyst_scores").update({"score": current + winnings}).eq("user_name", user).execute()
        supabase.table("predictions").update({"status": "Resolved", "outcome": "Correct"}).eq("id", pred_id).execute()
    else:
        # User already paid the wager, just mark as lost
        supabase.table("predictions").update({"status": "Resolved", "outcome": "Incorrect"}).eq("id", pred_id).execute()

# --- UI ---
st.title("🔮 THE FUTURES DESK")
st.caption("Prediction Market & Accountability Ledger")

# User Identity (Simulated for Public Version)
with st.sidebar:
    st.header("🆔 Analyst ID")
    # This simulates a login. In the future, we replace this with real Auth.
    username = st.text_input("Enter Codename:", value="Analyst_01")

    if username:
        score = get_user_score(username)
        st.metric("Credibility Score", f"{score} pts")
        st.info("Start: 1000 pts. Predictions cost points. Wins double your wager.")

tab1, tab2 = st.tabs(["🎲 Make Prediction", "📜 Ledger of Truth"])

with tab1:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("New Forecast")
        with st.form("prediction_form"):
            claim = st.text_input("I predict that...", placeholder="e.g. Bitcoin will cross $100k")
            c1, c2 = st.columns(2)
            with c1:
                deadline = st.date_input("By Date", min_value=datetime.date.today())
            with c2:
                confidence = st.slider("Confidence Level", 0, 100, 70)

            wager = st.number_input("Wager (Points)", min_value=10, max_value=score, step=10)

            if st.form_submit_button("🔒 Lock Prediction"):
                if not claim:
                    st.warning("Prediction cannot be empty.")
                else:
                    success, msg = place_bet(username, claim, deadline, confidence, wager)
                    if success:
                        st.success(f"Bet Placed! {wager} points deducted.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)

    with col2:
        st.markdown("### 🧠 The Rules")
        st.info("""
        **1. Skin in the Game:** Talk is cheap. Points are not.
        **2. The Payoff:** If you are right, you double your wager.
        **3. The Risk:** If you are wrong, the points are gone forever.
        """)

with tab2:
    st.subheader("Active Positions")

    # Active Bets
    try:
        active = supabase.table("predictions").select("*").eq("status", "Open").order("created_at", desc=True).execute().data
    except:
        active = []

    if not active:
        st.info("No active predictions.")

    for p in active:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.markdown(f"**{p['user_name']}** predicts: {p['claim']}")
                st.caption(f"Deadline: {p['deadline']} | Confidence: {p['confidence']}%")
            with c2:
                st.metric("Wager", p['wager'])
            with c3:
                # In a real app, only Admins resolve. Here, anyone can (Honor System).
                st.markdown("**Resolve:**")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("✅", key=f"t_{p['id']}"):
                        resolve_bet(p['id'], True)
                        st.rerun()
                with b2:
                    if st.button("❌", key=f"f_{p['id']}"):
                        resolve_bet(p['id'], False)
                        st.rerun()

    st.divider()
    st.subheader("Resolved History")
    try:
        history = supabase.table("predictions").select("*").eq("status", "Resolved").order("created_at", desc=True).limit(10).execute().data
    except:
        history = []

    for h in history:
        color = "green" if h['outcome'] == "Correct" else "red"
        st.markdown(f":{color}[**{h['outcome']}**]: {h['user_name']} - {h['claim']}")