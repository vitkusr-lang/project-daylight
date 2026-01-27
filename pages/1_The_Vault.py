import streamlit as st
import xml.etree.ElementTree as ET
import requests
import time
from io import BytesIO
from openai import OpenAI
import os
import re
from supabase import create_client, Client

# --- PAGE SETUP ---
st.set_page_config(page_title="Daylight: The Vault", layout="wide", page_icon="👁️")
st.title("👁️ DAYLIGHT: THE VAULT")
st.caption("Global Intelligence Grid (v2.9) | Visual Status Log Restored")

# --- CONFIGURATION ---
try:
    openai_api_key = st.secrets["OPENAI_API_KEY"]
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
except:
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

if supabase_url and supabase_key:
    supabase: Client = create_client(supabase_url, supabase_key)
else:
    st.error("🚨 Database Connection Failed.")
    st.stop()

# --- DATA SOURCES ---
FEED_DB = [
    {'region': 'WEST', 'country': '🇺🇸 USA', 'source': 'CNN', 'url': 'http://rss.cnn.com/rss/edition_world.rss'},
    {'region': 'WEST', 'country': '🇬🇧 UK', 'source': 'BBC', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml'},
    {'region': 'WEST', 'country': '🇪🇺 EU', 'source': 'Politico', 'url': 'https://www.politico.eu/feed/'},
    {'region': 'RUSSIA', 'country': '🔴 STATE', 'source': 'RT', 'url': 'https://www.rt.com/rss/news/'},
    {'region': 'RUSSIA', 'country': '⚪ EXILE', 'source': 'Meduza', 'url': 'https://meduza.io/rss/en/all'},
    {'region': 'UKRAINE', 'country': '🇺🇦 UKR', 'source': 'Kyiv Indep.', 'url': 'https://kyivindependent.com/news-archive/rss/'},
    {'region': 'ASIA', 'country': '🇨🇳 CHN', 'source': 'Global Times', 'url': 'https://www.globaltimes.cn/rss/outbrain.xml'},
    {'region': 'ASIA', 'country': '🇮🇳 IND', 'source': 'Times of India', 'url': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'},
    {'region': 'MIDEAST', 'country': '🇶🇦 QAT', 'source': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml'},
]

# --- HELPER FUNCTIONS ---

def create_new_case(title, description):
    try:
        data = {"title": title[:100], "description": f"Auto-generated from Vault:\n{description}", "status": "Active"}
        response = supabase.table("investigations").insert(data).execute()
        return response.data[0]['id'] if response.data else None
    except: return None

def save_lead_to_case(case_id, title, url):
    try:
        content = f"[{title}]({url})"
        supabase.table("intel_ledger").insert({"investigation_id": case_id, "type": "Lead", "content": content}).execute()
        return True
    except: return False

def parse_rss(feed_obj):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(feed_obj['url'], headers=headers, timeout=10)
        root = ET.fromstring(response.content)
        items = []
        is_atom = 'feed' in root.tag.lower()
        iter_items = root.findall('{http://www.w3.org/2005/Atom}entry') if is_atom else root.findall('.//item')
        for item in iter_items[:5]: 
            if is_atom:
                title = item.findtext('{http://www.w3.org/2005/Atom}title')
                link = item.find('{http://www.w3.org/2005/Atom}link').attrib.get('href')
                desc = item.findtext('{http://www.w3.org/2005/Atom}summary')
            else:
                title = item.findtext('title')
                link = item.findtext('link')
                desc = item.findtext('description')
            clean_desc = re.sub('<[^<]+?>', '', str(desc))[:200] + "..." if desc else "No description."
            if title:
                items.append({'source': feed_obj['source'], 'country': feed_obj['country'], 'region': feed_obj['region'], 'title': title, 'description': clean_desc, 'url': link})
        return items, "🟢"
    except: return [], "🔴"

def save_to_vault(items):
    data = [{"source": i['source'], "country": i['country'], "region": i['region'], "title": i['title'], "url": i['url'], "description": i['description']} for i in items]
    try: supabase.table("news_archive").upsert(data, on_conflict="url", ignore_duplicates=True).execute()
    except: pass

def fetch_from_vault():
    try: return supabase.table("news_archive").select("*").order("created_at", desc=True).limit(500).execute().data
    except: return []

def upload_evidence(file_obj, notes):
    try:
        file_name = f"{int(time.time())}_{file_obj.name}"
        file_bytes = file_obj.getvalue()
        supabase.storage.from_("evidence").upload(path=file_name, file=file_bytes, file_options={"content-type": file_obj.type})
        public_url = supabase.storage.from_("evidence").get_public_url(file_name)
        data = {"filename": file_name, "file_url": public_url, "media_type": file_obj.type.split('/')[0], "description": notes}
        supabase.table("evidence_locker").insert(data).execute()
        return True, public_url
    except Exception as e: return False, str(e)

def analyze_narrative_clash(topic, articles):
    if not openai_api_key: return "⚠️ OpenAI Key Missing."
    client = OpenAI(api_key=openai_api_key)
    context = ""
    for a in articles[:25]:
        context += f"SOURCE: {a.get('source')} | TITLE: {a.get('title')} | URL: {a.get('url')}\n"

    system_prompt = f"""
    You are a Senior Intelligence Analyst. Topic: "{topic}"
    OBJECTIVE: Produce a Narrative Landscape Report.
    STRUCTURE: 1. CORE CONFLICT. 2. REGIONAL SPLIT. 3. MISSING CONTEXT. 4. VERDICT.
    CITATION RULE (STRICT): You MUST hyperlink sources. Example: "According to [CNN](http://cnn.com/story)..."
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"DATA:\n{context}"}]
        )
        return response.choices[0].message.content
    except Exception as e: return f"Analysis Failed: {e}"

# --- MAIN UI ---

# 1. SIDEBAR
st.sidebar.header("🎛️ Mission Control")

# --- THE RESTORED INGESTION BUTTON ---
if st.sidebar.button("🔄 Ingest Global Feeds"):
    st.toast("Contacting Satellites...")
    all_items = []
    progress = st.sidebar.progress(0)

    # VISUAL STATUS LOG
    status_box = st.sidebar.empty()
    with status_box.container():
        st.caption("📡 Connection Status:")
        for i, feed in enumerate(FEED_DB):
            items, status = parse_rss(feed)
            all_items.extend(items)

            # Print Red/Green status
            if "🔴" in status:
                st.error(f"{status} {feed['source']}")
            else:
                st.write(f"{status} **{feed['source']}**")

            progress.progress((i+1)/len(FEED_DB))
            time.sleep(0.1) # Tiny pause so user can see the list building

    save_to_vault(all_items)
    st.sidebar.success(f"Ingested {len(all_items)} signals.")
    time.sleep(2) # Give time to read logs
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("📂 Evidence Locker")
uploaded_file = st.sidebar.file_uploader("Upload Intel", type=['png', 'jpg', 'pdf'])
evidence_note = st.sidebar.text_input("Context Note")
if uploaded_file and st.sidebar.button("💾 Secure Upload"):
    success, res = upload_evidence(uploaded_file, evidence_note)
    if success: st.sidebar.success("File Secured.")
    else: st.sidebar.error(f"Error: {res}")

# 2. MAIN FEED
vault_data = fetch_from_vault()
try:
    active_cases = supabase.table("investigations").select("id, title").eq("status", "Active").execute().data
    case_options = {"✨ CREATE NEW CASE FROM THIS": "NEW_CASE_TRIGGER"}
    for c in active_cases: case_options[c['title']] = c['id']
except: case_options = {"✨ CREATE NEW CASE FROM THIS": "NEW_CASE_TRIGGER"}

tabs = st.tabs(["ALL", "RUSSIA", "WEST", "MIDEAST", "ASIA"])

def render_feed(region_filter, tab):
    with tab:
        items = [x for x in vault_data if region_filter == "ALL" or x['region'] == region_filter]
        if not items:
            st.info("No data. Click 'Ingest' in sidebar.")
            return

        for i, item in enumerate(items):
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{item['country']} | {item['source']}**")
                    st.markdown(f"[{item['title']}]({item['url']})")
                    st.caption(item['description'])
                with c2:
                    unique_id = f"{region_filter}_{i}_{item['url']}"
                    target_case_name = st.selectbox("Assign Case:", list(case_options.keys()), key=f"sel_{unique_id}", label_visibility="collapsed")
                    if st.button("🚀 Promote", key=f"btn_{unique_id}"):
                        selected_id = case_options[target_case_name]
                        if selected_id == "NEW_CASE_TRIGGER":
                            with st.spinner("Initializing..."):
                                new_id = create_new_case(item['title'], item['description'])
                                if new_id:
                                    save_lead_to_case(new_id, item['title'], item['url'])
                                    st.success("Case Opened!")
                                    time.sleep(1)
                                else: st.error("Failed.")
                        else:
                            if save_lead_to_case(selected_id, item['title'], item['url']):
                                st.toast("Sent!")
                            else: st.error("Failed.")

render_feed("ALL", tabs[0])
render_feed("RUSSIA", tabs[1])
render_feed("WEST", tabs[2])
render_feed("MIDEAST", tabs[3])
render_feed("ASIA", tabs[4])

# 3. NARRATIVE PRISM
st.divider()
st.header("💎 The Narrative Prism")

if 'report_content' not in st.session_state:
    st.session_state.report_content = None
if 'report_topic' not in st.session_state:
    st.session_state.report_topic = ""

topic = st.text_input("Analyze Topic (e.g. 'Ukraine', 'Election')", placeholder="Enter keyword...")

if st.button("⚡ Generate Intelligence Report"):
    if not topic:
        st.warning("Enter a topic.")
    else:
        relevant = [d for d in vault_data if topic.lower() in d['title'].lower()]
        if relevant:
            with st.spinner("Analyzing Global Narratives..."):
                report = analyze_narrative_clash(topic, relevant)
                st.session_state.report_content = report
                st.session_state.report_topic = topic
        else:
            st.error("No signals found in the Vault for this topic.")

if st.session_state.report_content:
    st.markdown("### 📂 CLASSIFIED BRIEFING")
    st.markdown(st.session_state.report_content)
    st.divider()

    clean_content = st.session_state.report_content.replace("`", "\\`")
    html_string = f"""
    <html>
    <head><style>body {{ font-family: sans-serif; max-width: 800px; margin: auto; padding: 40px; }} a {{ color: #E63946; text-decoration: none; font-weight: bold; }}</style></head>
    <body>
    <h1>📂 DAYLIGHT BRIEF: {st.session_state.report_topic}</h1>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <div id="content"></div>
    <script>document.getElementById('content').innerHTML = marked.parse(`{clean_content}`);</script>
    </body></html>
    """
    st.download_button("📤 Share / Download Briefing (HTML)", data=html_string, file_name=f"Brief_{st.session_state.report_topic}.html", mime="text/html")
