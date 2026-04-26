"""
Checkmate Agent — LangGraph StateGraph definition.
"""

from typing import TypedDict, List, Annotated
import operator
import functools

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .nodes import (
    resolve_mentions,
    planner,
    code_executor,
    route_query,
    suggest_citations,
    verify_consistency,
    format_citation,
    flag_gaps,
    find_relation,
    hil_context,
    hil_verify,
    find_facts,
)
from .agent_logger import clear_log, log_graph_invocation, log_graph_completion


# ── State Schema ────────────────────────────────────────


class CitationState(TypedDict):
    # Document context (loaded once, passed through)
    slides: dict  # {"slide_<id>" : ["shape id":"", "text": "..."]}
    sheets: dict  # {"Sheet1": [["hdr",...], ["row",...], ...]}
    pptx_filename: str
    xlsx_filename: str

    # Scoped context (resolved by resolve_mentions tool)
    active_slides: List[dict]
    active_sheets: dict

    # Conversation
    messages: Annotated[List[dict], operator.add]  # [{role, content}]
    current_query: str

    # Agent working memory
    plan: dict
    current_step_id: str
    step_outputs: dict
    candidate_citations: List[dict]
    gaps_found: List[str]
    last_agent_action: str  # "suggest" | "verify" | "format" | "flag" | "code_executor"
    action_history: List[dict]  # List of { "action": str, "outcome": str }

    # Human-in-the-Loop & Safety
    pending_hil_approval: bool
    hil_payload: dict
    loop_count: int

    max_iterations: int  # Optional: to prevent infinite loops, can be set in config
    iteration_count: int  # Track the number of iterations


# ── Graph Construction ──────────────────────────────────


def build_graph() -> StateGraph:
    """
    Build and compile the Checkmate LangGraph.
    """
    graph = StateGraph(CitationState)

    # Add nodes
    graph.add_node("resolve_mentions", resolve_mentions)
    graph.add_node("planner", planner)
    graph.add_node("code_executor", code_executor)
    graph.add_node("suggest_citations", suggest_citations)
    graph.add_node("verify_consistency", verify_consistency)
    graph.add_node("format_citation", format_citation)
    graph.add_node("flag_gaps", flag_gaps)
    graph.add_node("find_relation", find_relation)
    graph.add_node("find_facts", find_facts)
    graph.add_node("hil_context", hil_context)
    graph.add_node("hil_verify", hil_verify)

    # Entry point: resolve mentions first to scope the context
    graph.set_entry_point("resolve_mentions")

    # From resolve_mentions, always go to planner (unless HIL needed)
    graph.add_conditional_edges(
        "resolve_mentions",
        lambda s: "hil_context" if s.get("pending_hil_approval") else "find_facts",
        {
            "hil_context": "hil_context",
            "find_facts": "find_facts",
        },
    )

    # After HIL context, go to planner
    graph.add_edge("hil_context", "planner")

    # Planner decides what to do next based on current step
    graph.add_conditional_edges(
        "planner",
        route_query,
        {
            "suggest_citations": "suggest_citations",
            "code_executor": "code_executor",
            "verify_consistency": "verify_consistency",
            "find_relation": "find_relation",
            "flag_gaps": "flag_gaps",
            "format_citation": "format_citation",
            "hil_context": "hil_context",
            "hil_verify": "hil_verify",
            "END": END,
        },
    )

    # All action nodes loop back to planner
    graph.add_edge("find_facts", "planner")
    graph.add_edge("suggest_citations", "planner")
    graph.add_edge("code_executor", "planner")
    graph.add_edge("verify_consistency", "planner")
    graph.add_edge("find_relation", "planner")
    graph.add_edge("format_citation", "planner")
    graph.add_edge("flag_gaps", "planner")

    # HIL Verify loops back to planner after completion
    graph.add_edge("hil_verify", "planner")

    return graph


# ── Agent class ─────────────────────────────────────────


class CheckmateGraph:
    """
    Encapsulates the compiled LangGraph agent.
    Holds the compiled graph as an instance attribute to avoid global state.
    """

    def __init__(self) -> None:
        memory = MemorySaver()
        self._compiled = build_graph().compile(checkpointer=memory)

    def invoke(self, state: dict, config: dict | None = None):
        """Pass-through to the underlying compiled graph's invoke."""
        clear_log()  # Clear log file before each invocation
        log_graph_invocation(state)

        if config is not None:
            result = self._compiled.invoke(state, config)
        else:
            result = self._compiled.invoke(state)

        log_graph_completion(result)
        return result

    def run_agent(
        self,
        query: str,
        slides: list[dict],
        sheets: dict,
        messages: list[dict],
        pptx_filename: str = "",
        xlsx_filename: str = "",
    ) -> dict:
        """
        Invoke the Checkmate agent with a user query.
        """
        input_state = {
            "slides": slides or [],
            "sheets": sheets or {},
            "pptx_filename": pptx_filename,
            "xlsx_filename": xlsx_filename,
            "active_slides": [],
            "active_sheets": {},
            "messages": messages or [],
            "current_query": query,
            "candidate_citations": [],
            "gaps_found": [],
            "last_agent_action": "",
            "pending_hil_approval": False,
            "hil_payload": {},
            "loop_count": 0,
            "max_iterations": 10,
            "plan": {},
            "current_step_id": "",
            "step_outputs": {},
            "action_history": [],
        }

        # Give a default config thread_id if invoking directly via run_agent without config
        # (Usually run_agent shouldn't be used async, but keep it for test scripts)
        config = {"configurable": {"thread_id": "default_run_agent"}}
        return self._compiled.invoke(input_state, config)


# ── Module-level accessor (lazy, no global keyword) ─────


@functools.lru_cache(maxsize=1)
def get_graph() -> CheckmateGraph:
    """Return the cached (singleton) CheckmateGraph instance."""
    return CheckmateGraph()


# ── Public API (module-level convenience wrapper) ───────


def run_agent(
    query: str,
    slides: list[dict],
    sheets: dict,
    messages: list[dict],
) -> dict:
    """Module-level convenience wrapper around CheckmateGraph.run_agent."""
    return get_graph().run_agent(query, slides, sheets, messages)
