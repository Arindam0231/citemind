"""
CiteMind Agent — LangGraph node functions.
Each node receives the full CitationState and returns a partial update dict.
"""

import os
import json
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from agent.llm_utils import llm_service
from agent.prompts import (
    SYSTEM_PROMPT,
    ROUTING_PROMPT,
    SUGGEST_PROMPT,
    VERIFY_PROMPT,
    FORMAT_PROMPT,
    FLAG_PROMPT,
    RESOLVE_MENTIONS_PROMPT,
    FIND_RELATION_PROMPT,
)
from utils.pptx_parser import format_slides_for_prompt
from utils.xlsx_parser import format_sheets_for_prompt

# ── LLM client ─────────────────────────────────────────


def _call_claude(system: str, user_message: str, max_tokens: int = 2048) -> str:
    """Low-level API call using the integrated llm_service."""
    messages = [SystemMessage(content=system), HumanMessage(content=user_message)]
    # Assuming llm_service handles the max_tokens or it's statically configured in that service wrapper
    result = llm_service(messages)
    return result


def _build_system_prompt(state: dict) -> str:
    """Inject slide & sheet context into the system prompt."""
    slides = state.get("active_slides") or state.get("slides", [])
    sheets = state.get("active_sheets") or state.get("sheets", {})
    slides_ctx = format_slides_for_prompt(slides)
    sheets_ctx = format_sheets_for_prompt(sheets)
    print(2)
    return SYSTEM_PROMPT.format(
        slides_context=slides_ctx,
        sheets_context=sheets_ctx,
    )


def _extract_json(text: str) -> dict | list:
    """Helper to extract JSON from LLM markdown wrappers."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    return json.loads(text.strip())


# ── Graph Nodes ─────────────────────────────────────────


def resolve_mentions(state: dict) -> dict:
    """
    Use LLM to determine bounded active_slides and active_sheets based on user query.
    Optionally flags for 'hil_context' if intent is ambiguous.
    """
    query = state.get("current_query", "")
    slides = state.get("slides", [])
    sheets = state.get("sheets", {}).get("cleaned", {})

    pptx_filename = state.get("pptx_filename", "Unknown PPTX")
    xlsx_filename = state.get("xlsx_filename", "Unknown XLSX")
    total_slides = len(slides)
    # Formatter for available options
    available_slides = "\n".join(
        [f"[{i}] {'Slide '+str(i+1)} (ID: {s})" for i, s in enumerate(slides.keys())]
    )
    available_sheets = "\n".join([f"- {s}" for s in sheets.keys()])

    prompt = RESOLVE_MENTIONS_PROMPT.format(
        query=query,
        pptx_name=pptx_filename,
        total_slides=total_slides,
        available_slides=available_slides,
        xlsx_name=xlsx_filename,
        available_sheets=available_sheets,
    )

    reply = _call_claude(
        "You are a helpful JSON-only output assistant.", prompt, max_tokens=1000
    )
    try:
        idx_list = reply.get("slide_indexes", [])
        sheet_list = reply.get("sheet_names", [])
        print("In resolve_mentions: got reply:", reply)
        active_slides = {
            list(slides.keys())[i]: slides[list(slides.keys())[i]]
            for i in idx_list
            if i < len(slides)
        }
        active_sheets = {k: sheets[k] for k in sheet_list if k in sheets}
        print("Resolved active slides:", list(active_slides.keys()))
        print("Resolved active sheets:", list(active_sheets.keys()))
        needs_clarif = reply.get("needs_clarification", False)

        update = {
            "active_slides": active_slides,
            "active_sheets": active_sheets,
            "loop_count": state.get("loop_count", 0) + 1,
        }

        if needs_clarif:
            update["pending_hil_approval"] = True
            update["hil_payload"] = {
                "type": "context_clarification",
                "message": reply.get("clarification_message", ""),
                "proposed_slides": idx_list,
                "proposed_sheets": sheet_list,
            }
        return update
    except Exception as e:
        # Default fallback: do not bound the context explicitly
        return {"loop_count": state.get("loop_count", 0) + 1}


def hil_context(state: dict) -> dict:
    """Human-in-the-loop checkpoint for context resolution ambiguity."""
    payload = state.get("hil_payload", {})
    # Suspend here, wait for UI to supply user_decision
    user_decision = interrupt(payload)

    # Once resumed, process decision.
    # Let's say user_decision overrides active_slides / sheets if desired.
    # We just clear the HIL flags.
    return {"pending_hil_approval": False, "hil_payload": {}}


def route_query(state: dict) -> str:
    """
    Classify the user query into one of: suggest, verify, format, flag.
    Returns a string key used by the conditional edge.
    """
    print("Routing query:", state.get("current_query", ""))
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    print("Gett system prompt for routing:", system)
    prompt = ROUTING_PROMPT.format(query=query)
    print("System prompt for routing:", system)
    result = _call_claude(system, prompt, max_tokens=20).strip().lower()
    print("Routing result:", result)
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
        "loop_count": state.get("loop_count", 0) + 1,
    }


def verify_consistency(state: dict) -> dict:
    """Cross-check numbers in slides against Excel data."""
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = VERIFY_PROMPT.format(query=query)
    reply = _call_claude(system, prompt)

    # Simplified stub for gap finding detection logic based on AI reply:
    # We look for "⚠️ Gap" to trigger the 'find_relation'
    gaps = []
    for line in reply.split("\n"):
        if "⚠️ Gap" in line:
            gaps.append(line)

    return {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "verify",
        "gaps_found": gaps,
        "loop_count": state.get("loop_count", 0) + 1,
    }


def find_relation(state: dict) -> dict:
    """Agentic loop node to look for semantic matches for the identified gaps."""
    gaps = state.get("gaps_found", [])
    if not gaps:
        return {"loop_count": state.get("loop_count", 0) + 1}

    # Process the most severe or first gap
    last_gap = gaps[-1]

    sheets = state.get("active_sheets") or state.get("sheets", {})
    sheets_ctx = format_sheets_for_prompt(sheets)

    prompt = FIND_RELATION_PROMPT.format(
        claim=last_gap, active_sheets_context=sheets_ctx
    )

    reply = _call_claude(
        "You are a helpful JSON-only output assistant.", prompt, max_tokens=1000
    )

    try:
        parsed = _extract_json(reply)
        return {
            "candidate_citations": parsed,
            "pending_hil_approval": True,
            "hil_payload": {
                "type": "relation_verification",
                "claim": last_gap,
                "candidates": parsed,
            },
            "loop_count": state.get("loop_count", 0) + 1,
        }
    except Exception as e:
        return {"loop_count": state.get("loop_count", 0) + 1}


def hil_verify(state: dict) -> dict:
    """Human-in-the-loop checkpoint for discrepancy relational gap filling."""
    payload = state.get("hil_payload", {})
    user_decision = interrupt(payload)

    messages_update = []
    if user_decision and isinstance(user_decision, dict):
        if user_decision.get("action") == "accept":
            messages_update.append(
                {
                    "role": "assistant",
                    "content": "You accepted the newly proposed relation mapping.",
                }
            )
        elif user_decision.get("action") == "reject":
            messages_update.append(
                {
                    "role": "assistant",
                    "content": "You rejected the proposed relation mapping. Flagging as unsolved gap.",
                }
            )

    return {
        "pending_hil_approval": False,
        "hil_payload": {},
        "messages": messages_update,
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
        "loop_count": state.get("loop_count", 0) + 1,
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
        "loop_count": state.get("loop_count", 0) + 1,
    }
