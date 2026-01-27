import streamlit as st
import os
import time
import json
import requests
import sys
from supabase import create_client, Client
from openai import OpenAI
from bs4 import BeautifulSoup
from fpdf import FPDF
from streamlit_agraph import agraph, Node, Edge, Config
import wikipedia

st.set_page_config(page_title="Daylight: Investigations", page_icon="🕵️", layout="wide")

# --- 1. SETUP & CREDENTIALS ---
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    openai_api_key = st.secrets["OPENAI_API_KEY"]
except:
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")

supabase: Client = create_client(supabase_url, supabase_key)
client = OpenAI(api_key=openai_api_key)

# --- 2. HELPER FUNCTIONS ---

def create_case_dossier(case_data, intel_data):
    """Generates a PDF Mission Report."""
    pdf = FPDF()
    pdf.add_page()

    def sanitize(text):
        return text.encode('latin-1', 'replace').decode('latin-1')

    pdf.set_font("Arial", "B", 20)
    pdf.cell(0, 10, sanitize(f"OPERATION: {case_data['title'].upper()}"), ln=True, align="C")
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, sanitize(f"Status: {case_data['status']} | Date: {time.strftime('%Y-%m-%d')}"), ln=True, align="C")
    pdf.line(10, 30, 200, 30)
    pdf.ln(10)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "1. MISSION OBJECTIVE", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 7, sanitize(case_data['description']))
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "2. VERIFIED ENTITIES", ln=True)
    pdf.set_font("Arial", "", 10)
    entities = [i for i in intel_data if "Entity" in i['type']]
    if not entities:
        pdf.cell(0, 7, "No entities confirmed.", ln=True)
    else:
        for ent in entities:
            clean_type = ent['type'].replace("Entity: ", "")
            pdf.cell(0, 7, sanitize(f"- {ent['content']} ({clean_type})"), ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "3. ESTABLISHED CONNECTIONS", ln=True)
    links = [i for i in intel_data if "Relationship" in i['type']]
    if not links:
        pdf.cell(0, 7, "No connections mapped.", ln=True)
    else:
        for link in links:
            parts = link['content'].split('|')
            if len(parts) == 3:
                pdf.cell(0, 7, sanitize(f"- {parts[0]} -> {parts[1]} -> {parts[2]}"), ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "4. ANALYST HYPOTHESES", ln=True)
    hyps = [i for i in intel_data if "Hypothesis" in i['type']]
    if not hyps:
        pdf.cell(0, 7, "No hypotheses generated.", ln=True)
    else:
        for h in hyps:
            pdf.multi_cell(0, 7, sanitize(f"* {h['content']}"))
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "5. ARCHIVE LEADS", ln=True)
    leads = [i for i in intel_data if "Lead" in i['type']]
    if not leads:
        pdf.cell(0, 7, "No leads found.", ln=True)
    else:
        for l in leads:
            clean_lead = l['content']
            if "](" in clean_lead:
                parts = clean_lead.split("](")
                title = parts[0].replace("[", "")
                url = parts[1].replace(")", "")
                clean_lead = f"{title}: {url}"
            clean_lead = clean_lead.replace("📂", "").replace("📍", "")
            pdf.multi_cell(0, 6, sanitize(f"- {clean_lead}"))

    return pdf.output(dest="S").encode("latin-1")

def perform_deep_search(query_entity, query_context):
    results = []
    try:
        search_results = wikipedia.search(query_entity, results=3)
        for title in search_results:
            try:
                page = wikipedia.page(title, auto_suggest=False)
                results.append({
                    "title": f"📂 Archive: {page.title}",
                    "href": page.url,
                    "body": page.summary[:200] + "..." 
                })
            except:
                continue
    except:
        return []
    return results

def fetch_content_from_url(url):
    """Safe Fetcher: Handles Websites. Manual Text for YouTube."""

    # 1. YOUTUBE LOGIC (Disabled for Stability)
    if "youtube.com" in url or "youtu.be" in url:
        return "⚠️ SYSTEM NOTICE: Please copy the transcript from YouTube manually and paste it here. The automated scraper is blocked."

    # 2. WEBSITE LOGIC
    else:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator=' ')
            return text[:15000] 
        except Exception as e:
            return f"Error scraping website: {str(e)}"

def extract_intel_from_text(text):
    """Robust Extraction with Markdown Cleaning"""
    system_prompt = """
    You are an Intelligence Analyst. Extract:
    1. Entities (People, Organizations, Events).
    2. Relationships (Source -> Label -> Target).

    IMPORTANT: Return ONLY valid raw JSON. Do not use Markdown blocks (```json).
    Format: {"entities": [{"name": "X", "type": "Person"}], "relationships": [{"source": "X", "target": "Y", "label": "Z"}]}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content

        # --- FIX: Strip Markdown if AI adds it ---
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        print(f"DEBUG AI OUTPUT: {content[:100]}...") # Print to console for debugging
        return json.loads(content.strip())
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        return None

def generate_lateral_hypotheses(current_intel):
    system_prompt = """
    Apply 'Cui Bono' (Who Benefits?) logic.
    Return 3 short hypotheses. JSON: { "hypotheses": ["Hypothesis 1...", "Hypothesis 2..."] }
    """
    try:
        intel_context = json.dumps(current_intel)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": intel_context}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except:
        return None

# --- 3. MAIN UI ---

st.title("🕵️ INVESTIGATIONS BUREAU")
st.caption("Deep Pattern Analysis & Entity Tracking")
st.divider()

# Sidebar
st.sidebar.header("🗂️ Case Files")
try:
    response = supabase.table("investigations").select("*").order("created_at", desc=True).execute()
    cases = response.data
except:
    cases = []
case_titles = [c['title'] for c in cases]
selected_case_name = st.sidebar.selectbox("Open Case File:", ["-- New Case --"] + case_titles)

active_case = None
if selected_case_name != "-- New Case --":
    active_case = next((c for c in cases if c['title'] == selected_case_name), None)

    # PDF EXPORT BUTTON
    st.sidebar.markdown("---")
    st.sidebar.write("🔒 **Classified Actions**")
    intel_res = supabase.table("intel_ledger").select("*").eq("investigation_id", active_case['id']).execute()
    intel_items = intel_res.data

    if st.sidebar.button("🖨️ Export Dossier (PDF)"):
        pdf_bytes = create_case_dossier(active_case, intel_items)
        st.sidebar.download_button(
            label="📥 Download PDF",
            data=pdf_bytes,
            file_name=f"Dossier_{active_case['title']}.pdf",
            mime="application/pdf"
        )

# Main Area
if selected_case_name == "-- New Case --":
    st.subheader("📂 Open New Investigation")
    with st.form("new_case_form"):
        new_title = st.text_input("Operation Name")
        new_desc = st.text_area("Mission Objective / Context")
        submitted = st.form_submit_button("🚀 Initialize Case")
        if submitted and new_title:
            data = {"title": new_title, "description": new_desc, "status": "Active"}
            supabase.table("investigations").insert(data).execute()
            st.success(f"Case '{new_title}' opened.")
            time.sleep(1)
            st.rerun()

elif active_case:
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1: st.header(f"📂 {active_case['title']}")
    with c2: st.metric("Status", active_case['status'])
    with c3:
        if st.button("🗑️ Archive"):
            supabase.table("investigations").delete().eq("id", active_case['id']).execute()
            st.rerun()

    tab1, tab2 = st.tabs(["📝 Intelligence Ledger", "🕸️ Network Graph"])

    # FETCH DATA AGAIN FOR TABS
    intel_res = supabase.table("intel_ledger").select("*").eq("investigation_id", active_case['id']).order("created_at", desc=True).execute()
    intel_items = intel_res.data
    existing_entities = [i['content'] for i in intel_items if "Entity" in i['type']]

    with tab1:
        col_input, col_view = st.columns([1, 1])

        with col_input:
            st.subheader("1. Ingest Intelligence")

            # AUTO ANALYST
            with st.container(border=True):
                st.markdown("### ✨ AI Auto-Analyst")
                input_content = st.text_area("Source Material (Paste Text, URL, or YouTube Transcript):", height=100)

                if st.button("🔍 Analyze Source"):
                    if not input_content:
                        st.warning("⚠️ Input is empty.")
                    else:
                        final_text = input_content
                        # Only fetch if it looks like a URL (and NOT YouTube)
                        if "http" in input_content:
                            with st.spinner("🌍 Fetching content..."):
                                fetched = fetch_content_from_url(input_content)
                                # If it's a YouTube link, the function returns the warning message
                                # If it's a website, it returns the text
                                final_text = fetched

                        # Only proceed if we have valid text (not a short error message)
                        if "SYSTEM NOTICE" in final_text:
                             st.warning(final_text)
                        elif len(final_text) > 20:
                            with st.spinner("Extracting Intelligence..."):
                                data = extract_intel_from_text(final_text)
                                if data:
                                    # INSERT ENTITIES
                                    new_count = 0
                                    for ent in data.get('entities', []):
                                        if ent['name'] not in existing_entities:
                                            supabase.table("intel_ledger").insert({
                                                "investigation_id": active_case['id'],
                                                "type": f"Entity: {ent['type']}",
                                                "content": ent['name']
                                            }).execute()
                                            new_count += 1

                                    # INSERT RELATIONSHIPS
                                    for rel in data.get('relationships', []):
                                        content = f"{rel['source']}|{rel['label']}|{rel['target']}"
                                        supabase.table("intel_ledger").insert({
                                            "investigation_id": active_case['id'],
                                            "type": "Relationship",
                                            "content": content
                                        }).execute()

                                    st.success(f"Extraction Complete. Added {new_count} new entities.")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("AI returned no data. Check input.")
                        else:
                            st.error("Input too short to analyze.")

            # LATERAL THINKING
            st.markdown("---")
            with st.container(border=True):
                st.markdown("### 🧠 Lateral Thinking Engine")
                if st.button("🔮 Generate Hypotheses"):
                    if not intel_items:
                        st.warning("Add data first.")
                    else:
                        with st.spinner("Applying 'Cui Bono' Logic..."):
                            analysis = generate_lateral_hypotheses(intel_items)
                            if analysis:
                                st.session_state['generated_hypotheses'] = analysis['hypotheses']

                if 'generated_hypotheses' in st.session_state:
                    for idx, hyp in enumerate(st.session_state['generated_hypotheses']):
                        col_h, col_s = st.columns([4, 1])
                        with col_h: st.info(hyp)
                        with col_s:
                            if st.button("Save", key=f"save_{idx}"):
                                supabase.table("intel_ledger").insert({
                                    "investigation_id": active_case['id'],
                                    "type": "Hypothesis",
                                    "content": hyp
                                }).execute()
                                st.rerun()

        with col_view:
            st.subheader("2. Verified Ledger")
            if not intel_items:
                st.info("No intelligence gathered yet.")
            else:
                for item in intel_items:
                    icon = "📄"
                    display_text = item['content']

                    if "Person" in item['type']: icon = "👤"
                    elif "Organization" in item['type']: icon = "🏢"
                    elif "Event" in item['type']: icon = "📅"
                    elif "Hypothesis" in item['type']: icon = "🤔"
                    elif "Lead" in item['type']: icon = "📍"
                    elif "Relationship" in item['type']:
                        icon = "🔗"
                        parts = item['content'].split('|')
                        if len(parts) == 3:
                            display_text = f"**{parts[0]}** → *{parts[1]}* → **{parts[2]}**"

                    with st.expander(f"{icon} {item['type']}"):
                        st.markdown(display_text)

                        # ARCHIVE SEARCH
                        if "Entity" in item['type']:
                            if st.button(f"🔎 Dig for '{item['content']}'", key=f"search_{item['id']}"):
                                with st.spinner(f"Hunting intel on {item['content']}..."):
                                    results = perform_deep_search(item['content'], active_case['title'])
                                    if results:
                                        count = 0
                                        for res in results:
                                            lead_text = f"[{res['title']}]({res['href']})"
                                            supabase.table("intel_ledger").insert({
                                                "investigation_id": active_case['id'],
                                                "type": "Lead",
                                                "content": lead_text
                                            }).execute()
                                            count += 1
                                        st.success(f"Hunter Report: Found {count} new leads.")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("No archives found.")

                        if st.button("Delete", key=item['id']):
                            supabase.table("intel_ledger").delete().eq("id", item['id']).execute()
                            st.rerun()

    # GRAPH TAB
    with tab2:
        st.subheader("Interactive Entity Map")
        nodes = []
        edges = []

        if not intel_items:
            st.warning("Add data to generate graph.")
        else:
            for item in intel_items:
                if "Entity" in item['type']:
                    img_url = "[https://cdn-icons-png.flaticon.com/512/3135/3135715.png](https://cdn-icons-png.flaticon.com/512/3135/3135715.png)"
                    if "Organization" in item['type']:
                        img_url = "[https://cdn-icons-png.flaticon.com/512/4300/4300059.png](https://cdn-icons-png.flaticon.com/512/4300/4300059.png)"
                    elif "Event" in item['type']:
                        img_url = "[https://cdn-icons-png.flaticon.com/512/747/747310.png](https://cdn-icons-png.flaticon.com/512/747/747310.png)"
                    nodes.append(Node(id=item['content'], label=item['content'], size=25, shape="circularImage", image=img_url))

            for item in intel_items:
                if "Relationship" in item['type']:
                    parts = item['content'].split('|')
                    if len(parts) == 3:
                        edges.append(Edge(source=parts[0], target=parts[2], label=parts[1], color="#ff4b4b"))

            config = Config(width=900, height=650, directed=True, nodeHighlightBehavior=True, highlightColor="#F7A7A6")
            if nodes:
                agraph(nodes=nodes, edges=edges, config=config)
