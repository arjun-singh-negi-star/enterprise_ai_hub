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

# ✅ CONFIRMED WORKING MODELS
GEMINI_MODEL   = "google/gemini-2.5-flash"
DEEPSEEK_MODEL = "deepseek/deepseek-r1"


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
# 🔧 HELPER: OpenRouter API call
# =====================================================================
def _call_openrouter(prompt: str, model: str, max_tokens: int) -> tuple:
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
        "model":       model,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  max_tokens,
        "temperature": 0.3,
        "stream":      False
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers, json=payload, timeout=120
        )

        if response.status_code == 200:
            data    = response.json()
            choices = data.get('choices', [])
            if not choices:
                return False, "", "", 200

            message   = choices[0].get('message', {})
            content   = (message.get('content')   or '').strip()
            reasoning = (message.get('reasoning') or '').strip()

            # reasoning_details array (some providers)
            if not reasoning:
                rd_list = message.get('reasoning_details', [])
                if rd_list:
                    reasoning = ' '.join([
                        rd.get('text', '') for rd in rd_list if rd.get('text')
                    ]).strip()

            # DeepSeek via Azure: content=null, reasoning has the actual draft
            if not content and reasoning:
                _, from_r = _extract_reasoning_and_content(reasoning)
                content   = from_r if len(from_r) > 50 else reasoning

            # <think> blocks inside content
            if content and "<think>" in content:
                think_r, content = _extract_reasoning_and_content(content)
                if think_r and not reasoning:
                    reasoning = think_r

            if not content or len(content.strip()) < 10:
                print(f"    ⚠️ [OpenRouter] {model} → content too short")
                return False, "", "", 200

            print(f"    ✅ [OpenRouter] {model} → {len(content)}ch content, {len(reasoning)}ch reasoning")
            return True, content.strip(), reasoning.strip(), 200

        else:
            print(f"    ⚠️ [OpenRouter] {model} → Status {response.status_code}")
            return False, "", "", response.status_code

    except requests.exceptions.Timeout:
        print(f"    ⚠️ [OpenRouter] {model} → Timeout")
        return False, "", "", 408
    except Exception as e:
        print(f"    ⚠️ [OpenRouter] {model} → {str(e)}")
        return False, "", "", 0


# =====================================================================
# 🔧 HELPER: Direct DeepSeek API (Layer 3 backup)
# =====================================================================
def _call_direct_deepseek(prompt: str, max_tokens: int) -> tuple:
    """Returns: (success, content, reasoning)"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("    ⚠️ [Direct DeepSeek] DEEPSEEK_API_KEY not in .env")
        return False, "", ""

    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json"
            },
            json={
                "model":       "deepseek-reasoner",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  max_tokens,
                "temperature": 0.3
            },
            timeout=120
        )
        if response.status_code == 200:
            data      = response.json()
            message   = data['choices'][0]['message']
            content   = (message.get('content')           or '').strip()
            reasoning = (message.get('reasoning_content') or '').strip()
            if not reasoning:
                reasoning, content = _extract_reasoning_and_content(content)
            print(f"    ✅ [Direct DeepSeek] {len(content)}ch content, {len(reasoning)}ch reasoning")
            return True, content, reasoning
        else:
            print(f"    ⚠️ [Direct DeepSeek] Status {response.status_code}")
            return False, "", ""
    except Exception as e:
        print(f"    ⚠️ [Direct DeepSeek] {str(e)}")
        return False, "", ""


# =====================================================================
# 🔧 HELPER: Gemini Reasoning Generator
# Jab DeepSeek credits nahi → Gemini se 6-step reasoning banao
# =====================================================================
def _generate_reasoning_via_gemini(
        email_context: str,
        draft_content: str,
        request_type:  str
) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "Reasoning unavailable — API key missing."

    reasoning_prompt = f"""You are an AI reasoning engine for SwiftCart enterprise email system.

EMAIL TYPE: {request_type}
CUSTOMER EMAIL: {email_context[:400]}
DRAFT RESPONSE: {draft_content[:500]}

Provide detailed step-by-step reasoning:

**📧 Step 1 — Intent Analysis:**
[What did the customer need?]

**🔍 Step 2 — Key Info Extracted:**
[What facts/issues were identified from the email?]

**🎯 Step 3 — Response Strategy:**
[Why was this approach chosen over alternatives?]

**📋 Step 4 — Policy Applied:**
[Which SwiftCart policies/guidelines were referenced?]

**✍️ Step 5 — Tone & Format:**
[Why this tone and structure was selected?]

**⚡ Step 6 — Risk Assessment:**
[Any escalation risks? Follow-up needed?]

Be specific and analytical."""

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "https://enterprise-ai-hub.local"
            },
            json={
                "model":       GEMINI_MODEL,
                "messages":    [{"role": "user", "content": reasoning_prompt}],
                "max_tokens":  800,
                "temperature": 0.2,
                "stream":      False
            },
            timeout=45
        )
        if r.status_code == 200:
            result = r.json()['choices'][0]['message']['content']
            return f"🤖 [Gemini 2.5 Flash — Add OpenRouter credits for real DeepSeek R1 <think>]\n\n{result}"
        return f"Reasoning generation failed (Status: {r.status_code})"
    except Exception as e:
        return f"Reasoning error: {str(e)}"


# =====================================================================
# 🔑 MASTER LLM CALLER — 3 Layer Automatic Fallback
#
# Layer 1 → OpenRouter DeepSeek R1  (real <think> + reasoning field)
# Layer 2 → OpenRouter Gemini 2.5 Flash  ✅ CONFIRMED 200 OK
# Layer 3 → Direct DeepSeek API  (DEEPSEEK_API_KEY in .env)
# =====================================================================
def call_llm(
    prompt:           str,
    model:            str  = DEEPSEEK_MODEL,
    expect_reasoning: bool = False,
    email_context:    str  = "",
    request_type:     str  = "[SUPPORT]"
) -> str:
    content     = ""
    reasoning   = ""
    success     = False
    used_gemini = False

    # ── Layer 1: DeepSeek R1 ────────────────────────────────────────
    if model.startswith("deepseek") or model == DEEPSEEK_MODEL:
        print(f"    🔵 [Layer 1] {DEEPSEEK_MODEL}...")
        success, content, reasoning, status = _call_openrouter(
            prompt, DEEPSEEK_MODEL, 90   # 94 tokens max available
        )
        if success:
            print("    ✅ DeepSeek R1 succeeded!")
        else:
            print(f"    ⚠️ DeepSeek R1 failed (status={status}) → Layer 2")

    # ── Layer 1B: Gemini directly requested ─────────────────────────
    elif model.startswith("google"):
        print(f"    🟡 [Layer 1B] {GEMINI_MODEL}...")
        success, content, reasoning, status = _call_openrouter(
            prompt, GEMINI_MODEL, 1500
        )
        if success:
            if expect_reasoning and not reasoning:
                reasoning = _generate_reasoning_via_gemini(
                    email_context, content, request_type
                )
            if expect_reasoning:
                return (f"System Reasoning Log:\n"
                        f"{reasoning or '[Response generated]'}\n\n"
                        f"---DRAFT---\n{content}")
            return content

    # ── Layer 2: Gemini 2.5 Flash fallback ──────────────────────────
    if not success:
        print(f"    🟡 [Layer 2] {GEMINI_MODEL} fallback...")
        success, content, reasoning, status = _call_openrouter(
            prompt, GEMINI_MODEL, 1500
        )
        if success:
            used_gemini = True
            print("    ✅ Gemini 2.5 Flash succeeded!")
        else:
            print(f"    ⚠️ Gemini failed (status={status}) → Layer 3")

    # ── Layer 3: Direct DeepSeek API ────────────────────────────────
    if not success:
        print("    🔴 [Layer 3] Direct DeepSeek API...")
        success, content, reasoning = _call_direct_deepseek(prompt, 1500)

    # ── Total failure ───────────────────────────────────────────────
    if not success or not content.strip():
        print("    ❌ [ALL LAYERS FAILED]")
        return "[LLM_ERROR] All layers failed"

    # ── Return with or without reasoning ────────────────────────────
    if expect_reasoning:
        if not reasoning and used_gemini:
            print("    🧠 Generating reasoning via Gemini 2.5 Flash...")
            reasoning = _generate_reasoning_via_gemini(
                email_context, content, request_type
            )
        return (f"System Reasoning Log:\n"
                f"{reasoning or '[Response generated successfully]'}\n\n"
                f"---DRAFT---\n{content}")

    return content


# =====================================================================
# 🤖 NODE 1: SUPERVISOR — Intent Classifier
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

    intent = call_llm(classification_prompt, model=GEMINI_MODEL).strip()

    for tag in ["[RFQ]", "[SUPPORT]", "[ESCALATION]", "[SPAM]"]:
        if tag in intent:
            intent = tag
            break
    else:
        intent = "[SUPPORT]"

    print(f"    📧 Intent Classified: {intent}")

    log_audit_event(
        "Supervisor Node",
        GEMINI_MODEL,
        f"Intent Classified as {intent}",
        f"Secured {pii_count} PII tokens."
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
# 📚 NODE 2: RAG AGENT — Knowledge Base
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
        print(f"    ⚠️ RAG Error: {e}")

    return {
        "rag_context": rag_result,
        "messages": [AIMessage(content=f"[RAG] Retrieved {len(rag_result)} chars.")]
    }


# =====================================================================
# 🔗 NODE 3: API AGENT — CRM Data
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
        print(f"    ⚠️ CRM Error: {e}")

    return {
        "crm_context": crm_result,
        "messages": [AIMessage(content="[CRM] Telemetry fetched.")]
    }


# =====================================================================
# ✍️ NODE 4: PLANNER — Draft Generator
# DeepSeek R1 primary → Gemini 2.5 Flash fallback → Direct DeepSeek
# =====================================================================
def planner_agent(state: AgentState) -> dict:
    print("--- [NODE 4/5] PLANNER AGENT ---")

    masked_body    = state.get("masked_email_body", "")
    request_type   = state.get("request_type",  "[SUPPORT]")
    rag_context    = state.get("rag_context",    "No knowledge base data available.")
    crm_context    = state.get("crm_context",    "No CRM history found.")
    human_feedback = state.get("human_feedback", "")
    vault          = state.get("pii_vault",      {})

    # Get sender placeholder tag
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

    # ── Primary call: DeepSeek R1 (auto-falls to Gemini if 402) ─────
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

    # ── Emergency: direct Gemini if all layers failed ────────────────
    if "[LLM_ERROR]" in draft_content or not draft_content.strip():
        print("    🔄 [EMERGENCY] All layers failed → direct Gemini call...")

        emergency_prompt = f"""Write a professional customer support email for SwiftCart.

Customer issue type: {request_type}
Customer email: {masked_body[:300]}

Rules:
- Use {sender_tag} as the ONLY recipient placeholder (never real emails)
- Professional, warm, helpful tone
- First line: subject only (NO "Subject:" prefix label)
- Second line: blank
- Then full email body
- Sign as: Arjun Singh Negi, Customer Success Team, SwiftCart"""

        gemini_response = call_llm(
            emergency_prompt,
            model=GEMINI_MODEL,
            expect_reasoning=True,
            email_context=masked_body,
            request_type=request_type
        )

        if "System Reasoning Log:" in gemini_response and "---DRAFT---" in gemini_response:
            parts           = gemini_response.split("---DRAFT---")
            reasoning_trace = parts[0].replace("System Reasoning Log:\n", "").strip()
            draft_content   = parts[1].strip()
        elif "[LLM_ERROR]" not in gemini_response and gemini_response.strip():
            draft_content   = gemini_response
            reasoning_trace = _generate_reasoning_via_gemini(
                masked_body, draft_content, request_type
            )
        else:
            # Absolute last resort template
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
            reasoning_trace = (
                "⚠️ All AI layers unavailable — professional template used.\n\n"
                "To restore full AI: Add OpenRouter credits → "
                "https://openrouter.ai/settings/credits"
            )

    print(f"    ✍️ Draft: {len(draft_content)} chars")
    print(f"    🧠 Reasoning: {len(reasoning_trace)} chars")

    log_audit_event(
        "Planner Node",
        f"{DEEPSEEK_MODEL}→{GEMINI_MODEL}",
        "Generated Response Draft",
        "Used RAG & CRM Context. PII mappings executed safely."
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
# 🚀 NODE 5: EXECUTOR — SMTP Dispatcher
# ✅ NOTE: Supabase CRM insert is handled by app.py on Approve click
#          (to avoid duplicate records in mail_dispatch_ledger)
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

    # ✅ Unmask all PII tags → real values
    unmasked_full    = unmask_pii(final_text, vault)
    actual_recipient = (
        unmask_pii(recipient_tag, vault)
        if recipient_tag.startswith("<")
        else recipient_tag
    )

    # ✅ Extract subject / body cleanly
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

    # Final PII unmask on body (double-pass for safety)
    email_body = unmask_pii(email_body, vault)

    smtp_user       = os.getenv("SENDER_EMAIL_ADDRESS")
    smtp_pass       = os.getenv("GMAIL_APP_PASSWORD")
    dispatch_status = "[EXECUTOR] Email NOT sent — SMTP credentials missing."

    if smtp_user and smtp_pass and actual_recipient and "@" in actual_recipient:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email_subject   # ✅ Clean subject — no "Subject:" prefix
            msg["From"]    = smtp_user
            msg["To"]      = actual_recipient
            msg.attach(MIMEText(email_body, "plain"))  # ✅ Clean body only

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, actual_recipient, msg.as_string())

            dispatch_status = f"[EXECUTOR] ✅ Email dispatched to {actual_recipient}"
            print(f"    ✅ SMTP SUCCESS → {actual_recipient}")
            print(f"    📧 Subject: {email_subject}")

            # ✅ Local ledger backup (text file)
            try:
                with open("mail_dispatch_ledger.txt", "a", encoding="utf-8") as f:
                    from datetime import datetime
                    now = datetime.now()
                    f.write(
                        f"{smtp_user} → {actual_recipient} | "
                        f"Subject: {email_subject} | "
                        f"Date: {now.strftime('%d/%m/%Y')} | "
                        f"Time: {now.strftime('%H:%M')}\n"
                    )
            except Exception as ledger_err:
                print(f"    ⚠️ Local ledger write failed: {ledger_err}")

            # ✅ SOC2 Audit Log
            log_audit_event(
                "Execution Node",
                "System API",
                f"Dispatched SMTP Email to {actual_recipient}",
                f"Subject: {email_subject} | UI payload securely unmasked and sent."
            )

        except smtplib.SMTPAuthenticationError:
            dispatch_status = "[EXECUTOR] ❌ SMTP Auth Failed — Check GMAIL_APP_PASSWORD in .env"
            print("    ❌ SMTP Authentication Error")
        except smtplib.SMTPRecipientsRefused:
            dispatch_status = f"[EXECUTOR] ❌ Recipient refused: {actual_recipient}"
            print(f"    ❌ Recipient refused: {actual_recipient}")
        except Exception as e:
            dispatch_status = f"[EXECUTOR] ❌ SMTP Error: {str(e)}"
            print(f"    ❌ SMTP Exception: {e}")
    else:
        print(
            f"    ⚠️ SMTP skipped — "
            f"smtp_user: {smtp_user} | "
            f"recipient: {actual_recipient}"
        )

    return {"messages": [AIMessage(content=dispatch_status)]}