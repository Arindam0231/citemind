"""
CiteMind Agent — LangGraph node functions.
Each node receives the full CitationState and returns a partial update dict.
"""
import os
from anthropic import Anthropic
from .prompts import (
    SYSTEM_PROMPT,
    ROUTING_PROMPT,
    SUGGEST_PROMPT,
    VERIFY_PROMPT,
    FORMAT_PROMPT,
    FLAG_PROMPT,
)
from utils.pptx_parser import format_slides_for_prompt
from utils.xlsx_parser import format_sheets_for_prompt

# ── LLM client ─────────────────────────────────────────
_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _client


def _call_claude(system: str, user_message: str, max_tokens: int = 2048) -> str:
    """Low-level Claude API call."""
    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def _build_system_prompt(state: dict) -> str:
    """Inject slide & sheet context into the system prompt."""
    slides_ctx = format_slides_for_prompt(state.get("slides", []))
    sheets_ctx = format_sheets_for_prompt(state.get("sheets", {}))
    return SYSTEM_PROMPT.format(
        slides_context=slides_ctx,
        sheets_context=sheets_ctx,
    )


# ── Graph Nodes ─────────────────────────────────────────


def route_query(state: dict) -> str:
    """
    Classify the user query into one of: suggest, verify, format, flag.
    Returns a string key used by the conditional edge.
    """
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = ROUTING_PROMPT.format(query=query)

    result = _call_claude(system, prompt, max_tokens=20).strip().lower()

    # Normalize — fall back to 'suggest' if unrecognized
    valid = {"suggest", "verify", "format", "flag"}
    if result not in valid:
        result = "suggest"

    return result


def suggest_citations(state: dict) -> dict:
    """Find matching Excel rows for a claim and propose citations."""
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = SUGGEST_PROMPT.format(query=query)
    reply = _call_claude(system, prompt)

    return {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "suggest",
    }


def verify_consistency(state: dict) -> dict:
    """Cross-check numbers in slides against Excel data."""
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = VERIFY_PROMPT.format(query=query)
    reply = _call_claude(system, prompt)

    return {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "verify",
    }


def format_citation(state: dict) -> dict:
    """Format a citation in the requested style."""
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = FORMAT_PROMPT.format(query=query)
    reply = _call_claude(system, prompt)

    return {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "format",
    }


def flag_gaps(state: dict) -> dict:
    """Identify claims with no supporting Excel data."""
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = FLAG_PROMPT.format(query=query)
    reply = _call_claude(system, prompt)

    return {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "flag",
    }
