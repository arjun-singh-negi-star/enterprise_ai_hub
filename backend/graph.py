from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from backend.state import AgentState
from backend.nodes import supervisor_agent, rag_agent, api_agent, planner_agent, executor_agent

def build_graph():
    workflow = StateGraph(AgentState)

    # Register Processing Nodes
    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("rag_agent", rag_agent)
    workflow.add_node("api_agent", api_agent)
    workflow.add_node("planner", planner_agent)
    
    # HITL Interrupt Execution Checkpoint
    def human_review(state):
        pass
    workflow.add_node("human_review", human_review)
    workflow.add_node("executor", executor_agent)

    # Direct Structural Pipeline
    workflow.set_entry_point("supervisor")
    workflow.add_edge("supervisor", "rag_agent")
    workflow.add_edge("rag_agent", "api_agent")
    workflow.add_edge("api_agent", "planner")
    workflow.add_edge("planner", "human_review")
    
    # State-Driven Conditional Routing Engine
    def decide_next_step(state: AgentState):
        if state.get("human_approved"):
            return "executor"
        return "planner"

    workflow.add_conditional_edges(
        "human_review",
        decide_next_step,
        {"executor": "executor", "planner": "planner"}
    )
    workflow.add_edge("executor", END)

    # Setup standard volatile storage layer for handling process interrupts
    memory = MemorySaver()
    # Setup standard volatile storage layer
    try:
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory, interrupt_before=["human_review"])
    except Exception as e:
        print(f"--- 🚨 CRITICAL GRAPH ERROR: {str(e)} ---")
        return None  # Isse hume pata chalega ki fail hua hai