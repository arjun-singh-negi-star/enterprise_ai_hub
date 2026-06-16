# backend/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from backend.state import AgentState
from backend.nodes import supervisor_agent, rag_agent, api_agent, planner_agent, executor_agent

def build_graph():
    workflow = StateGraph(AgentState)

    # ✅ Register all 5 nodes
    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("rag_agent", rag_agent)
    workflow.add_node("api_agent", api_agent)
    workflow.add_node("planner", planner_agent)
    
    # HITL Interrupt — empty passthrough node (interrupt_before handles the pause)
    def human_review(state: AgentState):
        return {}  # ✅ Returns empty dict, not None — prevents state corruption
    
    workflow.add_node("human_review", human_review)
    workflow.add_node("executor", executor_agent)

    # ✅ Pipeline wiring
    workflow.set_entry_point("supervisor")
    workflow.add_edge("supervisor", "rag_agent")
    workflow.add_edge("rag_agent", "api_agent")
    workflow.add_edge("api_agent", "planner")
    workflow.add_edge("planner", "human_review")
    
    # ✅ Conditional routing after HITL
    def decide_next_step(state: AgentState):
        if state.get("human_approved"):
            return "executor"
        return "planner"  # Loop back for rewrite if rejected

    workflow.add_conditional_edges(
        "human_review",
        decide_next_step,
        {"executor": "executor", "planner": "planner"}
    )
    workflow.add_edge("executor", END)

    # ✅ Compile with memory + interrupt BEFORE human_review
    try:
        memory = MemorySaver()
        compiled = workflow.compile(
            checkpointer=memory,
            interrupt_before=["human_review"]
        )
        print("✅ [GRAPH] LangGraph compiled successfully — 5 nodes active")
        return compiled
    except Exception as e:
        print(f"❌ [CRITICAL GRAPH ERROR] {str(e)}")
        return None