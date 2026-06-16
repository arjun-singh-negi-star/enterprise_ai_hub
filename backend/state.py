# backend/state.py
from typing import TypedDict, Annotated, List, Optional
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    request_type: str
    rag_context: str
    crm_context: str
    draft_response: str
    sender_email: str
    final_edited_text: str
    human_approved: bool
    human_feedback: str
    pii_vault: dict          # ✅ YE MISSING THA — app.py crash kar raha tha iske bina
    masked_email_body: str   # ✅ PII-masked version of incoming email