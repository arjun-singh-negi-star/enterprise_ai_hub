from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    request_type: str
    rag_context: str
    crm_context: str
    draft_response: str
    sender_email: str         # NEW: Captures client's email address dynamically
    final_edited_text: str    # NEW: Stores the text edited by the manager
    human_approved: bool
    human_feedback: str