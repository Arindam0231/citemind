"""
CiteMind Agent — LangGraph StateGraph definition.
"""
from typing import TypedDict, List, Annotated
import operator

from langgraph.graph import StateGraph, END

from .nodes import (
    route_query,
    suggest_citations,
    verify_consistency,
    format_citation,
    flag_gaps,
)


# ── State Schema ────────────────────────────────────────


class CitationState(TypedDict):
    # Document context (loaded once, passed through)
    slides: List[dict]          # [{"slide": 1, "text": "..."}]
    sheets: dict                # {"Sheet1": [["hdr",...], ["row",...], ...]}

    # Conversation
    messages: Annotated[List[dict], operator.add]  # [{role, content}]
    current_query: str

    # Agent working memory
    candidate_citations: List[dict]
    gaps_found: List[str]
    last_agent_action: str  # "suggest" | "verify" | "format" | "flag"


# ── Graph Construction ──────────────────────────────────


def _routing_decision(state: dict) -> str:
    """Conditional edge: classify query, return the node name to route to."""
    return route_query(state)


def build_graph() -> StateGraph:
    """
    Build and compile the CiteMind LangGraph.

    Flow:
        START → route (conditional) → suggest / verify / format / flag → END
    """
    graph = StateGraph(CitationState)

    # Add nodes
    graph.add_node("suggest_citations", suggest_citations)
    graph.add_node("verify_consistency", verify_consistency)
    graph.add_node("format_citation", format_citation)
    graph.add_node("flag_gaps", flag_gaps)

    # Entry point is the conditional router
    graph.set_conditional_entry_point(
        _routing_decision,
        {
            "suggest": "suggest_citations",
            "verify": "verify_consistency",
            "format": "format_citation",
            "flag": "flag_gaps",
        },
    )

    # All nodes lead to END
    graph.add_edge("suggest_citations", END)
    graph.add_edge("verify_consistency", END)
    graph.add_edge("format_citation", END)
    graph.add_edge("flag_gaps", END)

    return graph


# ── Agent class ─────────────────────────────────────────


class CiteMindGraph:
    """
    Encapsulates the compiled LangGraph agent.
    Holds the compiled graph as an instance attribute to avoid global state.
    """

    def __init__(self) -> None:
        self._compiled = build_graph().compile()

    def invoke(self, state: dict, config: dict | None = None):
        """Pass-through to the underlying compiled graph's invoke."""
        if config is not None:
            return self._compiled.invoke(state, config)
        return self._compiled.invoke(state)

    def run_agent(
        self,
        query: str,
        slides: list[dict],
        sheets: dict,
        messages: list[dict],
    ) -> dict:
        """
        Invoke the CiteMind agent with a user query.

        Returns the updated state dict with new messages appended.
        """
        input_state = {
            "slides": slides or [],
            "sheets": sheets or {},
            "messages": messages or [],
            "current_query": query,
            "candidate_citations": [],
            "gaps_found": [],
            "last_agent_action": "",
        }
        return self._compiled.invoke(input_state)


# ── Module-level accessor (lazy, no global keyword) ─────

import functools


@functools.lru_cache(maxsize=1)
def get_graph() -> CiteMindGraph:
    """Return the cached (singleton) CiteMindGraph instance."""
    return CiteMindGraph()


# ── Public API (module-level convenience wrapper) ───────


def run_agent(
    query: str,
    slides: list[dict],
    sheets: dict,
    messages: list[dict],
) -> dict:
    """Module-level convenience wrapper around CiteMindGraph.run_agent."""
    return get_graph().run_agent(query, slides, sheets, messages)
