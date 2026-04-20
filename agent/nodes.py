"""
CiteMind Agent — LangGraph node functions.
Each node receives the full CitationState and returns a partial update dict.
"""

import json
import logging
import traceback
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt

from agent.llm_utils import llm_service, llm_exec_with_retry  # ← moved to top-level
from agent.prompts import (
    SYSTEM_PROMPT,
    ROUTING_PROMPT,
    SUGGEST_PROMPT,
    VERIFY_PROMPT,
    FORMAT_PROMPT,
    FLAG_PROMPT,
    RESOLVE_MENTIONS_PROMPT,
    FIND_RELATION_PROMPT,
    PLANNER_PROMPT,
    FACT_RETRIEVAL_PROMPT,
)
from agent.agent_logger import log_node_execution
from utils.pptx_parser import format_slides_for_prompt
from utils.xlsx_parser import format_sheets_for_prompt

logger = logging.getLogger(__name__)


def _log_node_entry(node_name: str) -> None:
    border = "_" * 60
    print(border)
    print(f"LOG:: {node_name}")
    print(border)


# ── LLM client ─────────────────────────────────────────


def _call_claude(node_name: str, system: str, user_message: str) -> str:
    """Low-level API call using the integrated llm_service."""
    messages = [SystemMessage(content=system), HumanMessage(content=user_message)]
    result = llm_service(messages)
    log_node_execution(node_name, user_message, result)
    return result


def _build_system_context(state: dict):
    slides = state.get("active_slides") or state.get("slides", [])
    sheets = state.get("active_sheets") or state.get("sheets", {})
    slides_ctx = format_slides_for_prompt(slides)
    sheets_ctx = format_sheets_for_prompt(sheets)
    return slides_ctx, sheets_ctx


def _build_system_prompt(state: dict) -> str:
    """Inject slide & sheet context into the system prompt."""
    slides_ctx, sheets_ctx = _build_system_context(state)
    return SYSTEM_PROMPT.format(
        slides_context=slides_ctx,
        sheets_context=sheets_ctx,
    )


# ── Graph Nodes ─────────────────────────────────────────


def resolve_mentions(state: dict) -> dict:
    """
    Use LLM to determine bounded active_slides and active_sheets based on user query.
    Optionally flags for 'hil_context' if intent is ambiguous.
    """
    _log_node_entry("resolve_mentions")
    query = state.get("current_query", "")
    slides = state.get("slides")
    if not isinstance(slides, dict):
        slides = {}

    sheets_raw = state.get("sheets") or {}
    sheets = sheets_raw.get("cleaned", {}) if isinstance(sheets_raw, dict) else {}

    pptx_filename = state.get("pptx_filename", "Unknown PPTX")
    xlsx_filename = state.get("xlsx_filename", "Unknown XLSX")
    total_slides = len(slides)

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
        "resolve_mentions",
        "You are a helpful JSON-only output assistant.",
        prompt,
    )

    try:
        if isinstance(reply, str):
            try:
                reply = json.loads(reply)
            except json.JSONDecodeError:
                logger.warning(
                    "resolve_mentions: reply is a string but not JSON: %s", reply
                )
                # Fallback or error
                update = {"loop_count": state.get("loop_count", 0) + 1}
                return update

        idx_list = reply.get("slide_indexes", [])
        sheet_list = reply.get("sheet_names", [])
        logger.debug("resolve_mentions reply: %s", reply)

        slide_keys = list(slides.keys())
        active_slides = {
            slide_keys[i]: slides[slide_keys[i]]
            for i in idx_list
            if i < len(slide_keys)
        }
        active_sheets = {k: sheets[k] for k in sheet_list if k in sheets}

        logger.debug("Resolved active slides: %s", list(active_slides.keys()))
        logger.debug("Resolved active sheets: %s", list(active_sheets.keys()))

        needs_clarif = reply.get("needs_clarification", False)

        update: dict = {
            "active_slides": active_slides,
            "active_sheets": active_sheets,
            "last_agent_action": "resolve_mentions",
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

    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.warning("resolve_mentions failed to parse LLM reply: %s", e)
        error_update = {
            "loop_count": state.get("loop_count", 0) + 1,
            "last_agent_action": "resolve_mentions",
        }
        return error_update


def hil_context(state: dict) -> dict:
    """Human-in-the-loop checkpoint for context resolution ambiguity."""
    _log_node_entry("hil_context")
    payload = state.get("hil_payload", {})
    answer = interrupt(payload)
    print(answer)
    update = {"pending_hil_approval": False, "hil_payload": {}}
    return update


def route_query(state: dict) -> str:
    """
    Conditional edge: classify the user query into one of: suggest, verify, format, flag.
    Returns a string key used by the conditional edge.
    """
    _log_node_entry("route_query")
    query = state.get("current_query", "")
    logger.debug("Routing query: %s", query)
    system = _build_system_prompt(state)
    prompt = ROUTING_PROMPT.format(query=query)
    planning = PLANNER_PROMPT.format(
        query=query,
        max_iterations=state.get("max_iterations", 25),
        iteration_count=state.get("loop_count", 1),
        last_agent_action=state.get("last_agent_action", "None"),
    )
    to_write = _call_claude("planner", system, planning)
    result = _call_claude("route_query", system, prompt).strip().lower()
    logger.debug("Routing result: %s", result)

    valid = {"suggest", "verify", "format", "flag", "find_facts"}
    routing_result = result if result in valid else "suggest"

    return routing_result


def suggest_citations(state: dict) -> dict:
    """Find matching Excel rows for a claim and propose citations."""
    _log_node_entry("suggest_citations")
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = SUGGEST_PROMPT.format(query=query)
    reply = _call_claude("suggest_citations", system, prompt)

    update = {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "suggest",
        "loop_count": state.get("loop_count", 0) + 1,
    }
    return update


def verify_consistency(state: dict) -> dict:
    """Cross-check numbers in slides against Excel data."""
    _log_node_entry("verify_consistency")
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = VERIFY_PROMPT.format(query=query)
    reply = _call_claude("verify_consistency", system, prompt)

    gaps = [line for line in reply.split("\n") if "⚠️ Gap" in line]

    update = {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "verify",
        "gaps_found": gaps,
        "loop_count": state.get("loop_count", 0) + 1,
    }
    return update


def find_relation(state: dict) -> dict:
    """
    Agentic loop node to look for semantic matches for all identified gaps.
    Processes every gap, not just the last one, and triggers HIL for the first
    actionable candidate set found.
    """
    _log_node_entry("find_relation")
    gaps = state.get("gaps_found", [])
    if not gaps:
        update = {"loop_count": state.get("loop_count", 0) + 1}
        return update

    sheets_raw = state.get("sheets") or {}
    if isinstance(sheets_raw, dict):
        sheets = state.get("active_sheets") or sheets_raw.get("cleaned", {})
    else:
        sheets = {}
    sheets_ctx = format_sheets_for_prompt(sheets)

    # FIX: iterate all gaps instead of silently ignoring all but the last
    for gap in gaps:
        prompt = FIND_RELATION_PROMPT.format(
            claim=gap, active_sheets_context=sheets_ctx
        )
        parsed = _call_claude(
            "find_relation", "You are a helpful JSON-only output assistant.", prompt
        )

        if not parsed or not isinstance(parsed, list):
            continue

        needs_transform = parsed[0].get("needs_transformation", False)
        payload_type = (
            "transformation_request" if needs_transform else "relation_verification"
        )

        if needs_transform:
            # FIX: import moved to module level; no fragile conditional relative import
            try:
                messages = [
                    SystemMessage(
                        content=(
                            "You are a python coding assistant. Write a python function "
                            "`def extract_value(sheets):` that extracts or calculates the "
                            "required value from the `sheets` dictionary using the provided "
                            "reasoning and hints. The `sheets` dictionary maps sheet names to "
                            "2D lists (rows and columns). Return JSON with 'response' containing "
                            "ONLY the python code."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Claim: {gap}\n"
                            f"Reason: {parsed[0].get('reason')}\n"
                            f"Hint cell: {parsed[0].get('row_ref')} (and surrounding rows if aggregating)."
                        )
                    ),
                ]

                exec_result = llm_exec_with_retry(
                    fn_name="extract_value",
                    messages=messages,
                    fn_kwargs={
                        "sheets": state.get("active_sheets") or state.get("sheets", {})
                    },
                )

                parsed[0]["formula"] = exec_result["response"].get("response", "")
                parsed[0]["computed_value"] = exec_result["result"]

            except Exception as e:
                logger.error(
                    "Failed to generate transformation code: %s\n%s",
                    e,
                    traceback.format_exc(),
                )
                parsed[0]["formula"] = (
                    "# Failed to generate code. Please write it manually.\n"
                    "def extract_value(sheets):\n"
                    "    result = None\n"
                    "    return result\n"
                )
                parsed[0]["computed_value"] = "Error"

        update = {
            "candidate_citations": parsed,
            "pending_hil_approval": True,
            "hil_payload": {
                "type": payload_type,
                "claim": gap,
                "candidates": parsed,
            },
            "loop_count": state.get("loop_count", 0) + 1,
        }
        return update

    # All gaps exhausted without a parseable result
    update = {"loop_count": state.get("loop_count", 0) + 1}

    return update


def hil_verify(state: dict) -> dict:
    """Human-in-the-loop checkpoint for discrepancy relational gap filling."""
    _log_node_entry("hil_verify")
    payload = state.get("hil_payload", {})
    user_decision = interrupt(payload)

    messages_update = []
    if not (user_decision and isinstance(user_decision, dict)):
        update = {
            "pending_hil_approval": False,
            "hil_payload": {},
            "messages": messages_update,
        }
        return update

    # Use LLM to determine action from user input
    interpretation_prompt = f"""Based on the user's input, determine what action they intend to take.

User Input: {json.dumps(user_decision, indent=2)}

Available actions:
- "accept": User accepts the proposed relation mapping
- "reject": User rejects the proposed relation mapping
- "transform": User provides code to transform/extract the value

Respond with ONLY valid JSON in this format:
{{
  "action": "accept|reject|transform",
  "code": "python code if action is 'transform', otherwise empty string",
  "reasoning": "brief explanation of why you interpreted it this way"
}}"""

    llm_interpretation = _call_claude(
        "hil_verify",
        "You are a JSON-only output assistant that interprets user decisions.",
        interpretation_prompt,
    )

    try:
        action = llm_interpretation.get("action", "reject")
        code = llm_interpretation.get("code", "")
    except (AttributeError, KeyError):
        logger.warning("Failed to interpret user decision, defaulting to reject")
        action = "reject"
        code = ""

    if action == "accept":
        messages_update.append(
            {
                "role": "assistant",
                "content": "You accepted the newly proposed relation mapping.",
            }
        )

    elif action == "reject":
        messages_update.append(
            {
                "role": "assistant",
                "content": "You rejected the proposed relation mapping. Flagging as unsolved gap.",
            }
        )

    elif action == "transform":
        sheets = state.get("active_sheets") or state.get("sheets", {})
        local_vars: dict = {"sheets": sheets}

        try:
            exec(
                code, local_vars, local_vars
            )  # noqa: S102 — intentional user-driven execution

            if "extract_value" in local_vars and callable(local_vars["extract_value"]):
                result_val = local_vars["extract_value"](sheets=sheets)
            else:
                result_val = local_vars.get("result", "Undefined")

            candidate_citations = state.get("candidate_citations", [])
            if candidate_citations and isinstance(candidate_citations, list):
                candidate_citations[0]["formula"] = code
                candidate_citations[0]["computed_value"] = result_val

            messages_update.append(
                {
                    "role": "assistant",
                    "content": (
                        f"Transformation evaluated successfully. "
                        f"Extracted value: {result_val}. Validation successful."
                    ),
                }
            )

        except Exception as e:
            # FIX: traceback was imported but never used; now included in the message
            error_detail = traceback.format_exc()
            logger.error("hil_verify transform exec failed:\n%s", error_detail)
            messages_update.append(
                {
                    "role": "assistant",
                    "content": f"Transformation Code Execution Failed: {e}\n\n{error_detail}",
                }
            )

    update = {
        "pending_hil_approval": False,
        "hil_payload": {},
        "messages": messages_update,
    }
    return update


def format_citation(state: dict) -> dict:
    """Format a citation in the requested style."""
    _log_node_entry("format_citation")
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = FORMAT_PROMPT.format(query=query)
    reply = _call_claude("format_citation", system, prompt)

    update = {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "format",
        "loop_count": state.get("loop_count", 0) + 1,
    }
    return update


def flag_gaps(state: dict) -> dict:
    """Identify claims with no supporting Excel data."""
    _log_node_entry("flag_gaps")
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    prompt = FLAG_PROMPT.format(query=query)
    reply = _call_claude("flag_gaps", system, prompt)

    update = {
        "messages": [{"role": "assistant", "content": reply}],
        "last_agent_action": "flag",
        "loop_count": state.get("loop_count", 0) + 1,
    }
    return update


def find_facts(state: dict) -> dict:
    """Simple retrieval of relevant facts without verification (used for context or exploration, not final citations)."""
    _log_node_entry("find_facts")
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    slides_ctx, sheets_ctx = _build_system_context(state)
    prompt = FACT_RETRIEVAL_PROMPT.format(
        query=query,
        slide_context=slides_ctx,
    )  # Reusing flag prompt for simplicity; ideally should have its own
    reply = _call_claude("find_facts", system, prompt)

    update = {
        "messages": [
            {"role": "assistant", "content": json.dumps(reply.get("response", {}))}
        ],
        "last_agent_action": "find_facts",
        "loop_count": state.get("loop_count", 0) + 1,
    }
    return update
