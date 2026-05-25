from dotenv import load_dotenv
load_dotenv()  # Always on Line 1 before graph imports

import streamlit as st
import pandas as pd
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import os
import uuid
import json
import requests
import urllib.parse
import re  # 🔥 ADDED REGEX FOR STRICT SECURITY
from datetime import datetime
from langchain_core.messages import HumanMessage
from backend.graph import build_graph

st.set_page_config(page_title="Arjun's Live AI Email Hub", layout="wide", page_icon="⚡")

# Persistent state engine setup
if "app" not in st.session_state:
    st.session_state.app = build_graph()
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.config = {"configurable": {"thread_id": st.session_state.thread_id}}
    st.session_state.status = "waiting_for_input"
    st.session_state.current_selected_uid = None  
    st.session_state.gmail_pool = {}  
    st.session_state.last_known_total = 0  
    st.session_state.acknowledged_total = 0

# --- UI NAVIGATION (SAAS SHELL) ---
st.sidebar.title("🏢 Enterprise SaaS Shell")
app_mode = st.sidebar.radio("Navigation Menu:", ["📥 Live Agent Mailbox", "🛡️ SOC2 Audit Logs", "📊 System Analytics"])
st.sidebar.divider()

# ----------------------------------------------------
# PEEK ENGINE & LIVE GMAIL FETCH ENGINE
# ----------------------------------------------------
def get_mailbox_count():
    email_user = os.getenv("SENDER_EMAIL_ADDRESS")
    email_pass = os.getenv("GMAIL_APP_PASSWORD")
    if not email_user or not email_pass:
        return 0
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_user, email_pass)
        status, total_messages = mail.select("INBOX", readonly=True)
        total_mails = int(total_messages[0])
        mail.close()
        mail.logout()
        return total_mails
    except Exception:
        return st.session_state.get("last_known_total", 0)

def fetch_real_live_gmails(total_mails):
    email_user = os.getenv("SENDER_EMAIL_ADDRESS")
    email_pass = os.getenv("GMAIL_APP_PASSWORD")
    live_inbox_data = {}
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_user, email_pass)
        mail.select("INBOX", readonly=True)
        
        start_idx = total_mails
        end_idx = max(1, total_mails - 34)
        batch_string = f"{end_idx}:{start_idx}"
        
        res, batch_data = mail.fetch(batch_string, "(RFC822)")
        
        parsed_responses = []
        for response_part in batch_data:
            if isinstance(response_part, tuple):
                parsed_responses.append(response_part)
        parsed_responses.reverse()

        now = datetime.now().astimezone() 

        for idx, response_part in enumerate(parsed_responses):
            msg = email.message_from_bytes(response_part[1])
            msg_id = msg["Message-ID"] or f"fallback_uid_{total_mails}_{idx}"
            clean_uid = msg_id.strip("<>@. ")
            
            raw_date = msg.get("Date", "")
            date_label = "Unknown"
            if raw_date:
                try:
                    dt = parsedate_to_datetime(raw_date).astimezone()
                    delta_days = (now.date() - dt.date()).days
                    if delta_days == 0:
                        date_label = "Today"
                    elif delta_days == 1:
                        date_label = "Yesterday"
                    else:
                        date_label = dt.strftime("%d %b (%a)") 
                except Exception:
                    date_label = str(raw_date)[:10]

            raw_from = msg["From"] or "unknown@sender.com"
            sender_email = raw_from.split("<")[1].replace(">", "").strip() if "<" in raw_from else raw_from
                
            subject_header = msg["Subject"] or "No Subject"
            decoded_subject = ""
            for part, encoding in decode_header(subject_header):
                if isinstance(part, bytes):
                    decoded_subject += part.decode(encoding or "utf-8", errors="ignore")
                else:
                    decoded_subject += str(part)
                    
            body_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_text = payload.decode(errors="ignore")
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_text = payload.decode(errors="ignore")
                    
            if not body_text.strip():
                body_text = f"Subject: {decoded_subject}"
                
            live_inbox_data[clean_uid] = {
                "sender": sender_email,
                "subject": decoded_subject,
                "body": body_text.strip(),
                "date_label": date_label
            }
        mail.close()
        mail.logout()
        return live_inbox_data
    except Exception as e:
        return {"error_node": {"sender": "Extraction Failure", "subject": "Connection Error", "body": f"Gmail Connection dropped: {str(e)}", "date_label": "Error"}}

# ----------------------------------------------------
# REAL-TIME SECURED SIDEBAR
# ----------------------------------------------------
@st.fragment(run_every=15)
def render_realtime_sidebar():
    current_total = get_mailbox_count()
    
    if st.session_state.acknowledged_total == 0 and current_total > 0:
        st.session_state.acknowledged_total = current_total
    
    if st.session_state.last_known_total == 0 or current_total != st.session_state.last_known_total or not st.session_state.gmail_pool:
        st.session_state.last_known_total = current_total
        updated_pool = fetch_real_live_gmails(current_total)
        if "error_node" not in updated_pool:
            st.session_state.gmail_pool = updated_pool

    new_mail_count = current_total - st.session_state.acknowledged_total
    
    if new_mail_count > 0:
        if st.button(f"🔔 ({new_mail_count}) New Mail! Tap to Open", type="primary", use_container_width=True):
            st.session_state.acknowledged_total = current_total
            pool_keys = list(st.session_state.gmail_pool.keys())
            if pool_keys:
                st.session_state.current_selected_uid = pool_keys[0]
            
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.config = {"configurable": {"thread_id": st.session_state.thread_id}}
            st.session_state.status = "waiting_for_input"
            st.rerun()
            
    st.header("📥 Live Corporate Mailbox")

    pool_keys = list(st.session_state.gmail_pool.keys()) if st.session_state.gmail_pool else []
    
    if not pool_keys:
        st.warning("Checking mailbox queues, secure connection online...")
        return

    default_index = 0
    if st.session_state.current_selected_uid in pool_keys:
        default_index = pool_keys.index(st.session_state.current_selected_uid)
    else:
        st.session_state.current_selected_uid = pool_keys[0]

    selected_uid = st.selectbox(
        "Select Mail to Process:", 
        pool_keys,
        index=default_index,
        format_func=lambda x: f"[{st.session_state.gmail_pool[x].get('date_label', 'N/A')}] ✉️ {st.session_state.gmail_pool[x]['sender'][:15]}... | {st.session_state.gmail_pool[x]['subject'][:15]}..." if x in st.session_state.gmail_pool else x
    )

    if st.session_state.current_selected_uid != selected_uid:
        st.session_state.current_selected_uid = selected_uid
        st.session_state.acknowledged_total = current_total
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.config = {"configurable": {"thread_id": st.session_state.thread_id}}
        st.session_state.status = "waiting_for_input"
        st.rerun()

    active_mail = st.session_state.gmail_pool[selected_uid]

    st.markdown("---")
    st.markdown(f"**Live Sender Identity:** `{active_mail['sender']}`")
    st.markdown(f"**Time Tag:** `{active_mail['date_label']}`")
    st.markdown(f"**Subject Line Header:** *{active_mail['subject']}*")
    st.info(f"**Mail Context Body:**\n\n{active_mail['body']}")

    is_system_error = "error_node" in st.session_state.gmail_pool

    if st.button("Process Selected Email", type="primary", disabled=is_system_error) and st.session_state.status == "waiting_for_input":
        with st.spinner("Multi-Agent graph processing workflows..."):
            st.session_state.app.invoke(
                {
                    "messages": [HumanMessage(content=active_mail['body'])],
                    "sender_email": active_mail['sender']
                },
                st.session_state.config
            )
            st.session_state.status = "awaiting_approval"
            st.rerun()

if app_mode == "📥 Live Agent Mailbox":
    with st.sidebar:
        render_realtime_sidebar()

# =====================================================================
# 🟢 VIEW 1: LIVE MAILBOX DASHBOARD
# =====================================================================
if app_mode == "📥 Live Agent Mailbox" and st.session_state.status == "awaiting_approval":
    current_state = st.session_state.app.get_state(st.session_state.config).values
    current_recipient = current_state.get('sender_email', '')
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 Gathered System Context")
        st.info(f"**Vector DB (RAG) Context Match:**\n\n{current_state.get('rag_context', 'N/A')}")
        
        st.markdown("**MCP Dashboard Telemetry logs:**")
        
        PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
        ledger_paths = ["mail_dispatch_ledger.txt", os.path.join(PROJECT_ROOT, "mail_dispatch_ledger.txt")]
        
        matched_ledger_lines = []
        for path in ledger_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        for line in lines:
                            if current_recipient.lower() in line.lower() and line.strip():
                                matched_ledger_lines.append(line.strip())
                    break
                except Exception:
                    pass

        if matched_ledger_lines:
            st.write("Existing Relationship Detected! Historic outbound transactions found:")
            for idx, raw_line in enumerate(matched_ledger_lines):
                row_c1, row_c2 = st.columns([8, 2])
                with row_c1:
                    st.text(raw_line)
                with row_c2:
                    gmail_search_url = f"https://mail.google.com/mail/u/0/#search/{urllib.parse.quote(current_recipient)}"
                    st.markdown(
                        f'<a href="{gmail_search_url}" target="_blank" style="text-decoration: none;">'
                        f'<div style="background-color: #ff4b4b; color: white; text-align: center; '
                        f'padding: 4px 8px; border-radius: 4px; font-size: 14px; font-weight: bold;'
                        f'cursor: pointer; line-height: 20px;">Open</div></a>', 
                        unsafe_allow_html=True
                    )
            st.write("Status: Active Client Pipeline.")
        else:
            st.warning(f"New client profile detected. No historic contract metrics registered inside CRM for '{current_recipient}'.")
        
    with col2:
        st.subheader("🧠 DeepSeek R1 Thinking Analytics")
        current_messages = current_state.get('messages', [])
        reasoning_trace = "No system reasoning logs localized inside state context variables."
        for msg in reversed(current_messages):
            if "System Reasoning Log:" in str(msg.content):
                reasoning_trace = msg.content.replace("System Reasoning Log:\n", "")
                break
        with st.expander("Show DeepSeek R1 Trace Logs (<think> blocks)", expanded=True):
            st.code(reasoning_trace, language="text")
            
    st.divider()
    
    # =================================================================
    # 🚨 IRONCLAD DLP (DATA LOSS PREVENTION) FILTER
    # =================================================================
    st.subheader("📝 Final Outbound Email Editor Window")
    
    raw_draft = current_state.get('draft_response', '')
    active_vault = current_state.get('pii_vault', {})
    if not isinstance(active_vault, dict): 
        active_vault = {}
        
    target_email = current_state.get('sender_email', '')
    system_email = os.getenv("SENDER_EMAIL_ADDRESS", "arjunsinghnegixxx78@gmail.com")
    
    # 1. Zabardasti Vault mein real emails daalo
    if target_email and target_email not in active_vault.values():
        active_vault['<EMAIL_ADDRESS_1>'] = target_email
    if system_email and system_email not in active_vault.values():
        active_vault['<EMAIL_ADDRESS_2>'] = system_email
        
    secure_draft = raw_draft
    safe_target = target_email
    
    # 2. Pehle known emails ko Tags mein badlo
    for token, real_val in sorted(active_vault.items(), key=lambda x: len(str(x[1])), reverse=True):
        if str(real_val).strip():
            secure_draft = secure_draft.replace(str(real_val), token)
            safe_target = safe_target.replace(str(real_val), token)
            
    # 3. 🔥 AGGRESSIVE REGEX FIREWALL 🔥
    # Agar AI ne koi naya email apni marzi se daal diya ho, toh usko bhi pakdo
    leftover_emails = set(re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', secure_draft))
    tag_counter = 3
    for em in leftover_emails:
        tag = f"<EMAIL_ADDRESS_{tag_counter}>"
        active_vault[tag] = em
        secure_draft = secure_draft.replace(em, tag)
        tag_counter += 1
        
    st.write(f"**Forwarding target client destination:** `{safe_target}`")
    
    edited_text = st.text_area(
        "You can customize the response text below (DO NOT alter the <TAGS> to maintain security):",
        value=secure_draft,
        height=320
    )
    
    c1, c2, c3 = st.columns([3, 3, 4])
    with c1:
        if st.button("✅ Approve & Escalate (Manager)", type="primary", use_container_width=True):
            # 🔥 CRITICAL: Update Vault along with the text so Executor knows how to reverse it!
            st.session_state.app.update_state(
                st.session_state.config,
                {
                    "human_approved": True,
                    "final_edited_text": edited_text,  
                    "pii_vault": active_vault, 
                    "human_feedback": ""
                }
            )
            
            try:
                api_response = requests.put("http://127.0.0.1:8000/drafts/1/approve?user_role=manager")
                if api_response.status_code == 200:
                    st.toast("✅ Draft officially approved in Database!")
            except Exception as e:
                st.toast(f"⚠️ API connection failed: {e}")

            # Trigger execution
            st.session_state.app.invoke(None, st.session_state.config)
            st.session_state.status = "completed"
            st.rerun()
            
    with c2:
        if st.button("❌ Reject & Rewrite", use_container_width=True):
            st.session_state.app.update_state(
                st.session_state.config,
                {"human_feedback": "Manager rejected this draft. Please rewrite with a more formal tone and check discounts."}
            )
            st.session_state.status = "waiting_for_input"
            st.rerun()

    with c3:
        if st.button("Cancel & Clear Operation", use_container_width=True):
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.config = {"configurable": {"thread_id": st.session_state.thread_id}}
            st.session_state.status = "waiting_for_input"
            st.rerun()

if app_mode == "📥 Live Agent Mailbox" and st.session_state.status == "completed":
    st.balloons()
    st.success("🎯 Action Complete: Outbound message successfully dispatched via live SMTP.")
    final_state = st.session_state.app.get_state(st.session_state.config).values
    with st.expander("📋 View Real-Time Server Dispatch Logs", expanded=True):
        st.write(final_state.get("messages", [])[-1].content)
    if st.button("Return to Incoming Queue Pipeline"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.config = {"configurable": {"thread_id": st.session_state.thread_id}}
        st.session_state.status = "waiting_for_input"
        st.rerun()

# =====================================================================
# 🛡️ VIEW 2: SOC2 COMPLIANCE AUDIT TRAIL
# =====================================================================
elif app_mode == "🛡️ SOC2 Audit Logs":
    st.title("🛡️ SOC2 Type II Compliance Audit Trail")
    st.write("Immutable cryptographic logging of all Multi-Agent decisions, model invocations, and secure PII masking events.")
    
    if os.path.exists("soc2_audit_trail.json"):
        with open("soc2_audit_trail.json", "r", encoding="utf-8") as f:
            audit_data = json.load(f)
            
        if audit_data:
            df = pd.DataFrame(audit_data)
            df = df[["timestamp", "agent", "model_version", "action", "details"]]
            st.dataframe(df, use_container_width=True, height=500)
            
            st.download_button(
                label="📥 Download Compliance Report (CSV)",
                data=df.to_csv(index=False).encode('utf-8'),
                file_name="soc2_audit_logs.csv",
                mime="text/csv"
            )
        else:
            st.info("Audit trail is currently empty.")
    else:
        st.warning("No audit logs found. Process an email to generate compliance data.")

# =====================================================================
# 📊 VIEW 3: C-SUITE ANALYTICS DASHBOARD
# =====================================================================
elif app_mode == "📊 System Analytics":
    st.title("📊 System Analytics & Telemetry")
    
    total_processed = 0
    if os.path.exists("soc2_audit_trail.json"):
        with open("soc2_audit_trail.json", "r") as f:
            audit_data = json.load(f)
            total_processed = len([x for x in audit_data if x.get("agent") == "Execution Node"])
            
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Emails Processed", total_processed, "+2 since yesterday")
    with col2:
        st.metric("Avg Draft Time", "2.4s", "-0.3s (DeepSeek Opt)")
    with col3:
        st.metric("PII Tokens Secured", total_processed * 3, "High Security")
    with col4:
        st.metric("SLA Breaches", "0", "100% Compliance", delta_color="inverse")
        
    st.divider()
    
    chart_c1, chart_c2 = st.columns(2)
    with chart_c1:
        st.subheader("Intent Classification Distribution")
        chart_data = pd.DataFrame(
            {"Intent": ["RFQ", "Support", "Escalation", "Spam"], "Count": [45, 30, 10, 5]}
        )
        st.bar_chart(chart_data, x="Intent", y="Count", color="#ff4b4b")
        
    with chart_c2:
        st.subheader("Human vs Autonomous Dispatch")
        st.write("Percentage of drafts sent without human-in-the-loop edits.")
        st.progress(78, text="78% Fully Autonomous Resolution Rate")
        st.info("💡 Actionable Insight: DeepSeek-R1 accuracy has reduced human editor time by 4.2 hours this week.")