# backend/nodes.py
import os
import requests
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from backend.state import AgentState
from backend.tools import fetch_internal_docs, fetch_crm_data
from backend.pii_vault import mask_pii
from backend.audit import log_audit_event

load_dotenv()

import google.generativeai as genai

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

DEEPSEEK_MODEL = "deepseek/deepseek-r1"

# ✅ Try multiple model names in order — guards against naming/version issues
GEMINI_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-flash-latest",
    "gemini-pro-latest",
]


# =====================================================================
# 🔧 HELPER: <think> block extractor
# =====================================================================
def _extract_reasoning_and_content(raw_text: str):
    reasoning = ""
    content   = raw_text
    if "<think>" in raw_text and "</think>" in raw_text:
        s         = raw_text.find("<think>") + len("<think>")
        e         = raw_text.find("</think>")
        reasoning = raw_text[s:e].strip()
        content   = raw_text[e + len("</think>"):].strip()
    return reasoning, content


# =====================================================================
# 🔧 LAYER 1: OpenRouter DeepSeek R1
# =====================================================================
def _call_openrouter_deepseek(prompt: str, max_tokens: int) -> tuple:
    """Returns: (success, content, reasoning, status_code)"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return False, "", "", 0

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://enterprise-ai-hub.local",
        "X-Title":       "Enterprise AI Email Orchestrator"
    }
    payload = {
        "model":       DEEPSEEK_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  max_tokens,
        "temperature": 0.3,
        "stream":      False
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers, json=payload, timeout=60
        )
        if response.status_code == 200:
            data    = response.json()
            choices = data.get('choices', [])
            if not choices:
                return False, "", "", 200

            message   = choices[0].get('message', {})
            content   = (message.get('content')   or '').strip()
            reasoning = (message.get('reasoning') or '').strip()

            if not reasoning:
                rd_list = message.get('reasoning_details', [])
                if rd_list:
                    reasoning = ' '.join([
                        rd.get('text', '') for rd in rd_list if rd.get('text')
                    ]).strip()

            if not content and reasoning:
                _, from_r = _extract_reasoning_and_content(reasoning)
                content   = from_r if len(from_r) > 50 else reasoning

            if content and "<think>" in content:
                think_r, content = _extract_reasoning_and_content(content)
                if think_r and not reasoning:
                    reasoning = think_r

            if not content or len(content.strip()) < 10:
                return False, "", "", 200

            print(f"    ✅ [DeepSeek R1] {len(content)}ch content")
            return True, content.strip(), reasoning.strip(), 200
        else:
            print(f"    ⚠️ [DeepSeek R1] Status {response.status_code}")
            return False, "", "", response.status_code

    except requests.exceptions.Timeout:
        return False, "", "", 408
    except Exception as e:
        print(f"    ⚠️ [DeepSeek R1] {str(e)}")
        return False, "", "", 0


# =====================================================================
# 🔑 LAYER 2: DIRECT GOOGLE GEMINI API
# ✅ Tries multiple model names. Returns DETAILED error for UI display.
# =====================================================================
def _call_gemini_direct(prompt: str, max_tokens: int) -> tuple:
    """Returns: (success, content, error_message)"""
    if not GOOGLE_API_KEY:
        return False, "", "GOOGLE_API_KEY missing or empty in .env"

    last_error = "Unknown error"

    for model_name in GEMINI_MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": 0.3,
                }
            )

            content = ""
            try:
                content = response.text.strip()
            except Exception:
                if response.candidates:
                    parts   = response.candidates[0].content.parts
                    content = "".join(getattr(p, "text", "") for p in parts).strip()
                    if not content:
                        finish_reason = response.candidates[0].finish_reason
                        last_error = f"{model_name}: blocked/empty (finish_reason={finish_reason})"
                        continue

            if content and len(content) >= 5:
                print(f"    ✅ [Direct Gemini: {model_name}] {len(content)}ch content")
                return True, content, ""
            else:
                last_error = f"{model_name}: empty response"
                continue

        except Exception as e:
            last_error = f"{model_name} → {type(e).__name__}: {str(e)}"
            print(f"    ⚠️ [Direct Gemini: {model_name}] {last_error}")
            continue

    return False, "", last_error


def _generate_reasoning_via_gemini(email_context: str, draft_content: str, request_type: str) -> str:
    reasoning_prompt = f"""You are an AI reasoning engine for SwiftCart enterprise email system.

EMAIL TYPE: {request_type}
CUSTOMER EMAIL: {email_context[:400]}
DRAFT RESPONSE: {draft_content[:500]}

Provide step-by-step reasoning:

**📧 Step 1 — Intent Analysis:**
[What did the customer need?]

**🔍 Step 2 — Key Info Extracted:**
[What facts/issues were identified?]

**🎯 Step 3 — Response Strategy:**
[Why was this approach chosen?]

**📋 Step 4 — Policy Applied:**
[Which SwiftCart policies referenced?]

**✍️ Step 5 — Tone & Format:**
[Why this tone and structure?]

**⚡ Step 6 — Risk Assessment:**
[Escalation risks? Follow-up needed?]"""

    success, result, error = _call_gemini_direct(reasoning_prompt, 800)
    if success:
        return f"🤖 [Gemini — Direct API]\n\n{result}"
    return f"Reasoning generation failed: {error}"


# =====================================================================
# 🔧 LAYER 3: Direct DeepSeek API (last resort backup)
# =====================================================================
def _call_direct_deepseek(prompt: str, max_tokens: int) -> tuple:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return False, "", "", "DEEPSEEK_API_KEY missing"

    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "deepseek-reasoner", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "temperature": 0.3},
            timeout=60
        )
        if response.status_code == 200:
            data      = response.json()
            message   = data['choices'][0]['message']
            content   = (message.get('content')           or '').strip()
            reasoning = (message.get('reasoning_content') or '').strip()
            if not reasoning:
                reasoning, content = _extract_reasoning_and_content(content)
            print(f"    ✅ [Direct DeepSeek] {len(content)}ch")
            return True, content, reasoning, ""
        return False, "", "", f"Status {response.status_code}"
    except Exception as e:
        return False, "", "", str(e)


# =====================================================================
# 🔑 MASTER LLM CALLER
# Layer 1 → OpenRouter DeepSeek R1
# Layer 2 → DIRECT Google Gemini API (tries multiple model names)
# Layer 3 → Direct DeepSeek API
# ✅ On total failure, returns DETAILED error so it's visible in UI
# =====================================================================
def call_llm(
    prompt:           str,
    model:            str  = DEEPSEEK_MODEL,
    expect_reasoning: bool = False,
    email_context:    str  = "",
    request_type:     str  = "[SUPPORT]"
) -> str:
    content      = ""
    reasoning    = ""
    success      = False
    used_gemini  = False
    error_log    = []

    # ── Layer 1: DeepSeek R1 ─────────────────────────────────────
    if model.startswith("deepseek"):
        print("    🔵 [Layer 1] OpenRouter DeepSeek R1...")
        success, content, reasoning, status = _call_openrouter_deepseek(prompt, 90)
        if not success:
            error_log.append(f"DeepSeek R1 (status={status})")

    # ── Layer 2: DIRECT Gemini API ───────────────────────────────
    if not success:
        print("    🟢 [Layer 2] Direct Google Gemini API...")
        gemini_success, gemini_content, gemini_error = _call_gemini_direct(prompt, 2000)
        if gemini_success:
            success     = True
            content     = gemini_content
            used_gemini = True
        else:
            error_log.append(f"Direct Gemini: {gemini_error}")
            print(f"    ⚠️ Direct Gemini failed: {gemini_error}")

    # ── Layer 3: Direct DeepSeek API ─────────────────────────────
    if not success:
        print("    🔴 [Layer 3] Direct DeepSeek API...")
        ds_success, ds_content, ds_reasoning, ds_error = _call_direct_deepseek(prompt, 2000)
        if ds_success:
            success   = True
            content   = ds_content
            reasoning = ds_reasoning
        else:
            error_log.append(f"Direct DeepSeek: {ds_error}")

    # ── Total failure — DETAILED error for visibility ────────────
    if not success or not content.strip():
        detailed_error = " | ".join(error_log) if error_log else "Unknown failure"
        print(f"    ❌ [ALL LAYERS FAILED] {detailed_error}")
        return f"[LLM_ERROR] {detailed_error}"

    # ── Return ────────────────────────────────────────────────
    if expect_reasoning:
        if not reasoning and used_gemini:
            reasoning = _generate_reasoning_via_gemini(email_context, content, request_type)
        return (f"System Reasoning Log:\n"
                f"{reasoning or '[Response generated successfully]'}\n\n"
                f"---DRAFT---\n{content}")

    return content


# =====================================================================
# 🤖 NODE 1: SUPERVISOR
# =====================================================================
def supervisor_agent(state: AgentState) -> dict:
    print("\n" + "="*60)
    print("--- [NODE 1/5] SUPERVISOR AGENT ---")

    last_message = state["messages"][-1].content if state.get("messages") else ""
    sender       = state.get("sender_email", "unknown@client.com")

    existing_vault = state.get("pii_vault", {})
    if not isinstance(existing_vault, dict):
        existing_vault = {}

    masked_body, updated_vault      = mask_pii(last_message, existing_vault)
    also_mask_sender, updated_vault = mask_pii(sender, updated_vault)
    pii_count = len(updated_vault)
    print(f"    🛡️ PII Vault: {pii_count} tokens secured")

    classification_prompt = f"""You are an enterprise email classification agent for SwiftCart.
Classify this email into EXACTLY ONE category.

Email (PII Masked):
{masked_body}

Categories:
- [RFQ]        = pricing inquiry, quote request, bulk order, product availability
- [SUPPORT]    = order tracking, refund, complaint, account issue, technical problem
- [ESCALATION] = legal threat, urgent executive demand, extreme urgency
- [SPAM]       = irrelevant, promotional, unsolicited

Respond with ONLY the tag. Example: [SUPPORT]"""

    intent = call_llm(classification_prompt, model="gemini-direct").strip()

    for tag in ["[RFQ]", "[SUPPORT]", "[ESCALATION]", "[SPAM]"]:
        if tag in intent:
            intent = tag
            break
    else:
        intent = "[SUPPORT]"

    print(f"    📧 Intent Classified: {intent}")

    log_audit_event(
        "Supervisor Node", "gemini-direct",
        f"Intent Classified as {intent}", f"Secured {pii_count} PII tokens."
    )

    return {
        "request_type":      intent,
        "pii_vault":         updated_vault,
        "masked_email_body": masked_body,
        "messages": [AIMessage(
            content=f"[SUPERVISOR] {intent}. PII vault: {pii_count} tokens secured."
        )]
    }


# =====================================================================
# 📚 NODE 2: RAG AGENT
# =====================================================================
def rag_agent(state: AgentState) -> dict:
    print("--- [NODE 2/5] RAG AGENT ---")

    masked_body  = state.get("masked_email_body", "")
    request_type = state.get("request_type", "[SUPPORT]")
    query        = f"{request_type} {masked_body[:300]}"
    role         = "admin" if request_type == "[ESCALATION]" else "sales"

    try:
        rag_result = fetch_internal_docs.invoke({"query": query, "user_role": role})
        print(f"    📚 RAG Retrieved: {len(rag_result)} chars")
    except Exception as e:
        rag_result = f"[RAG_ERROR] {str(e)}"

    return {
        "rag_context": rag_result,
        "messages": [AIMessage(content=f"[RAG] Retrieved {len(rag_result)} chars.")]
    }


# =====================================================================
# 🔗 NODE 3: API/CRM AGENT
# =====================================================================
def api_agent(state: AgentState) -> dict:
    print("--- [NODE 3/5] API/CRM AGENT ---")

    sender         = state.get("sender_email", "")
    crm_identifier = sender if sender else "unknown_client"

    try:
        crm_result = fetch_crm_data.invoke({"client_identifier": crm_identifier})
        print(f"    🔗 CRM: {len(crm_result)} chars")
    except Exception as e:
        crm_result = "New client. No CRM history found."

    return {
        "crm_context": crm_result,
        "messages": [AIMessage(content="[CRM] Telemetry fetched.")]
    }


# =====================================================================
# ✍️ NODE 4: PLANNER
# =====================================================================
def planner_agent(state: AgentState) -> dict:
    print("--- [NODE 4/5] PLANNER AGENT ---")

    masked_body    = state.get("masked_email_body", "")
    request_type   = state.get("request_type",  "[SUPPORT]")
    rag_context    = state.get("rag_context",    "No knowledge base data available.")
    crm_context    = state.get("crm_context",    "No CRM history found.")
    human_feedback = state.get("human_feedback", "")
    vault          = state.get("pii_vault",      {})

    sender_tag = "<EMAIL_ADDRESS_1>"
    for tag in vault.keys():
        if "EMAIL_ADDRESS" in tag:
            sender_tag = tag
            break

    feedback_block = (
        f"\n⚠️ MANAGER FEEDBACK — Apply these corrections:\n{human_feedback}\n"
        if human_feedback else ""
    )

    drafting_prompt = f"""You are a senior customer success manager at SwiftCart, an e-commerce company.

CRITICAL SECURITY RULES — MUST FOLLOW:
1. NEVER write real email addresses — use ONLY placeholder tags like {sender_tag}
2. NEVER reveal internal pricing numbers or confidential policies verbatim
3. Address client using their tag ({sender_tag}), not real name
4. Tone: Professional, warm, solution-focused

EMAIL TYPE: {request_type}

CLIENT EMAIL (PII Masked):
{masked_body}

COMPANY KNOWLEDGE BASE (RAG):
{rag_context[:1500]}

CLIENT HISTORY (CRM):
{crm_context[:400]}
{feedback_block}
Write a complete professional email response.
IMPORTANT FORMAT:
- First line: subject line text only (NO "Subject:" label prefix)
- Second line: blank
- Then: full professional email body
- Use {sender_tag} as recipient placeholder throughout
- Sign as: Arjun Singh Negi, Customer Success Team, SwiftCart"""

    raw_response = call_llm(
        drafting_prompt,
        model=DEEPSEEK_MODEL,
        expect_reasoning=True,
        email_context=masked_body,
        request_type=request_type
    )

    reasoning_trace = ""
    draft_content   = raw_response

    if "System Reasoning Log:" in raw_response and "---DRAFT---" in raw_response:
        parts           = raw_response.split("---DRAFT---")
        reasoning_trace = parts[0].replace("System Reasoning Log:\n", "").strip()
        draft_content   = parts[1].strip() if len(parts) > 1 else raw_response

    # ── If genuinely all layers failed — show REAL error, not generic message ──
    if "[LLM_ERROR]" in draft_content or not draft_content.strip():
        real_error = draft_content.replace("[LLM_ERROR]", "").strip()
        print(f"    🔄 [EMERGENCY] {real_error}")

        draft_content = (
            f"Re: Your Inquiry — SwiftCart Support Team\n\n"
            f"Dear {sender_tag},\n\n"
            f"Thank you for contacting SwiftCart. We have received your "
            f"{request_type.strip('[]')} request and our team is reviewing it.\n\n"
            f"We will respond within 24 hours with a complete solution.\n\n"
            f"Best regards,\n"
            f"Arjun Singh Negi\n"
            f"Customer Success Team, SwiftCart\n"
            f"support@swiftcart.com | +1-800-555-0123"
        )
        # ✅ Real diagnostic info shown in UI — no more generic message
        reasoning_trace = (
            f"⚠️ All AI layers failed. Professional template used.\n\n"
            f"🔍 DIAGNOSTIC DETAIL:\n{real_error}\n\n"
            f"Run `python test_gemini.py` in terminal for full diagnosis."
        )

    print(f"    ✍️ Draft: {len(draft_content)} chars")
    print(f"    🧠 Reasoning: {len(reasoning_trace)} chars")

    log_audit_event(
        "Planner Node", "deepseek-r1→gemini-direct",
        "Generated Response Draft", "Used RAG & CRM Context."
    )

    messages_out = []
    if reasoning_trace:
        messages_out.append(AIMessage(content=f"System Reasoning Log:\n{reasoning_trace}"))
    messages_out.append(AIMessage(content="[PLANNER] Draft generation complete."))

    return {
        "draft_response": draft_content,
        "human_feedback": "",
        "messages":       messages_out
    }


# =====================================================================
# 🚀 NODE 5: EXECUTOR
# =====================================================================
def executor_agent(state: AgentState) -> dict:
    print("--- [NODE 5/5] EXECUTOR AGENT ---")

    import smtplib
    from email.mime.text      import MIMEText
    from email.mime.multipart import MIMEMultipart
    from backend.pii_vault    import unmask_pii

    final_text    = state.get("final_edited_text", "") or state.get("draft_response", "")
    vault         = state.get("pii_vault", {})
    recipient_tag = state.get("sender_email", "")

    if not isinstance(vault, dict):
        vault = {}

    unmasked_full    = unmask_pii(final_text, vault)
    actual_recipient = (
        unmask_pii(recipient_tag, vault)
        if recipient_tag.startswith("<")
        else recipient_tag
    )

    email_subject = "Re: Your Inquiry — SwiftCart Support Team"
    email_body    = unmasked_full

    lines = unmasked_full.strip().split('\n')
    if lines:
        first_line = lines[0].strip()
        if first_line.lower().startswith("subject:"):
            email_subject = first_line[8:].strip()
            email_body    = '\n'.join(lines[1:]).strip()
        elif (len(first_line) < 120
              and not first_line.lower().startswith("dear")
              and not first_line.lower().startswith("hello")):
            email_subject = first_line
            email_body    = '\n'.join(lines[1:]).strip()

    email_body = unmask_pii(email_body, vault)

    smtp_user       = os.getenv("SENDER_EMAIL_ADDRESS")
    smtp_pass       = os.getenv("GMAIL_APP_PASSWORD")
    dispatch_status = "[EXECUTOR] Email NOT sent — SMTP credentials missing."

    if smtp_user and smtp_pass and actual_recipient and "@" in actual_recipient:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email_subject
            msg["From"]    = smtp_user
            msg["To"]      = actual_recipient
            msg.attach(MIMEText(email_body, "plain"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, actual_recipient, msg.as_string())

            dispatch_status = f"[EXECUTOR] ✅ Email dispatched to {actual_recipient}"
            print(f"    ✅ SMTP SUCCESS → {actual_recipient} | Subject: {email_subject}")

            try:
                with open("mail_dispatch_ledger.txt", "a", encoding="utf-8") as f:
                    from datetime import datetime
                    now = datetime.now()
                    f.write(
                        f"{smtp_user} → {actual_recipient} | Subject: {email_subject} | "
                        f"{now.strftime('%d/%m/%Y %H:%M')}\n"
                    )
            except Exception:
                pass

            log_audit_event(
                "Execution Node", "System API",
                f"Dispatched SMTP Email to {actual_recipient}",
                f"Subject: {email_subject}"
            )

        except smtplib.SMTPAuthenticationError:
            dispatch_status = "[EXECUTOR] ❌ SMTP Auth Failed — Check GMAIL_APP_PASSWORD"
        except smtplib.SMTPRecipientsRefused:
            dispatch_status = f"[EXECUTOR] ❌ Recipient refused: {actual_recipient}"
        except Exception as e:
            dispatch_status = f"[EXECUTOR] ❌ SMTP Error: {str(e)}"
    else:
        print(f"    ⚠️ SMTP skipped — smtp:{smtp_user} recipient:{actual_recipient}")

    return {"messages": [AIMessage(content=dispatch_status)]}