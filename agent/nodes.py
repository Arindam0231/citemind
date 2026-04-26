"""
Checkmate Agent — LangGraph node functions.
Each node receives the full CitationState and returns a partial update dict.
"""

import json
import logging
import traceback
import pandas as pd
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
from utils.xlsx_parser import format_sheets_for_prompt, get_dataFrame_from_sheet_details

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


def _get_schema_summary(state: dict) -> str:
    """
    Returns a string summary of the available Excel sheets:
    Sheet names, column headers, and approximate row counts.
    """

    sheets_raw = state.get("sheets") or {}
    sheets_dict = sheets_raw.get("cleaned", {}) if isinstance(sheets_raw, dict) else {}
    if not sheets_dict:
        return "No Excel sheets loaded."
    data = get_dataFrame_from_sheet_details(sheets_dict)
    summary = ["Available Excel Sheets:"]
    for name, df in data.items():
        headers = df.columns.tolist()
        row_count = len(df) - 1
        cols_str = ", ".join([str(h) for h in headers])
        summary.append(f"- Sheet: {name} ({row_count} rows) | Columns: [{cols_str}]")

    return "\n".join(summary)


def _get_node_results_summary(state: dict) -> str:
    """
    Returns a truncated summary of previous node outputs for the planner.
    """
    outputs = state.get("step_outputs", {})
    if not outputs:
        return "No previous step results."

    summary = []
    for step_id, result in outputs.items():
        # Truncate result if it's too long
        res_str = str(result)
        if len(res_str) > 300:
            res_str = res_str[:300] + "... [truncated]"
        summary.append(f"Step {step_id} Output: {res_str}")

    return "\n".join(summary)


def _get_action_history_summary(state: dict) -> str:
    """
    Formats the action_history list for the prompt.
    """
    history = state.get("action_history", [])
    if not history:
        return "No actions attempted yet."

    summary = []
    for i, item in enumerate(history):
        summary.append(
            f"{i+1}. Action: {item.get('action')} | Outcome: {item.get('outcome')}"
        )

    return "\n".join(summary)


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
            "action_history": state.get("action_history", [])
            + [
                {"action": "resolve_mentions", "outcome": "Resolved slides and sheets."}
            ],
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
    update = {
        "pending_hil_approval": False,
        "hil_payload": {},
        "action_history": state.get("action_history", [])
        + [
            {
                "action": "hil_context",
                "outcome": f"Human provided context resolution: {answer}",
            }
        ],
    }
    return update


def planner(state: dict) -> dict:
    """
    Autonomous planning node. Observes state and returns a structured plan.
    """
    _log_node_entry("planner")
    query = state.get("current_query", "")
    system = _build_system_prompt(state)
    print("Holalfja")
    # Enrich prompt with state-specific info
    print(1)
    schema_summary = _get_schema_summary(state)
    print(2)
    action_history = _get_action_history_summary(state)
    print(3)
    node_results = _get_node_results_summary(state)
    planning_prompt = PLANNER_PROMPT.format(
        query=query,
        max_iterations=state.get("max_iterations", 10),
        iteration_count=state.get("loop_count", 0),
        schema_summary=schema_summary,
        action_history=action_history,
        node_results=node_results,
    )
    print("flsjfaoi")
    reply = _call_claude("planner", system, planning_prompt)
    print(reply)
    try:
        if isinstance(reply, str):
            reply = json.loads(reply)

        plan = reply.get("plan", {})
        current_step = reply.get("current_step", "1")

        update = {
            "last_agent_action": "planner",
            "action_history": state.get("action_history", [])
            + [
                {
                    "action": "planner",
                    "outcome": f"Generated plan with {len(plan)} steps.",
                }
            ],
            "loop_count": state.get("loop_count", 0) + 1,
            "pending_hil_approval": False,  # Clear HIL flag unless plan sets it
        }

        # If the plan specifies a HIL step as current, set the flag
        target_action = plan.get(current_step, {}).get("action", "")
        if target_action in ["hil_context", "hil_verify"]:
            update["pending_hil_approval"] = True

        # Store the plan and current step in state
        # (Assuming these fields are added to state in graph.py)
        update["plan"] = plan
        update["current_step_id"] = current_step

        return update

    except Exception as e:
        logger.error("Planner failed to parse JSON: %s", e)
        return {"loop_count": state.get("loop_count", 0) + 1}


def code_executor(state: dict) -> dict:
    """
    Executes Python code on DataFrames derived from Excel sheets.
    """
    _log_node_entry("code_executor")

    plan = state.get("plan", {})
    current_step_id = state.get("current_step_id", "1")
    step_info = plan.get(current_step_id, {})
    md_script = step_info.get("md_script", "")

    if not md_script:
        logger.warning("code_executor: No md_script found for step %s", current_step_id)
        return {"loop_count": state.get("loop_count", 0) + 1}

    # Prepare historical context (outputs of previous steps)
    step_outputs = state.get("step_outputs", {})

    # Load DataFrames
    sheets_raw = state.get("sheets") or {}
    sheets_dict = sheets_raw.get("cleaned", {}) if isinstance(sheets_raw, dict) else {}

    # Convert to DataFrames for execution
    dfs = {}
    for name, rows in sheets_dict.items():
        if rows and len(rows) > 0:
            dfs[name] = pd.DataFrame(rows[1:], columns=rows[0])
        else:
            dfs[name] = pd.DataFrame()

    messages = [
        SystemMessage(
            content="You are a Python data analyst. Write a function `def extract_value(dfs):` as requested."
        ),
        HumanMessage(content=md_script),
    ]

    try:
        exec_result = llm_exec_with_retry(
            fn_name="extract_value",
            messages=messages,
            fn_kwargs={"dfs": dfs},
            exec_globals={"pd": pd},
        )

        result_val = exec_result["result"]

        # Store output for planner to see in next iteration
        new_outputs = {**step_outputs, current_step_id: result_val}

        update = {
            "step_outputs": new_outputs,
            "last_agent_action": "code_executor",
            "action_history": state.get("action_history", [])
            + [
                {
                    "action": "code_executor",
                    "outcome": f"Executed code. Result: {result_val}",
                }
            ],
            "loop_count": state.get("loop_count", 0) + 1,
            "messages": [
                {"role": "assistant", "content": f"Code execution result: {result_val}"}
            ],
        }
        return update

    except Exception as e:
        logger.error("code_executor failed: %s", e)
        return {
            "loop_count": state.get("loop_count", 0) + 1,
            "messages": [
                {
                    "role": "assistant",
                    "content": f"Failed to execute code for step {current_step_id}: {str(e)}",
                }
            ],
        }


def route_query(state: dict) -> str:
    """
    Conditional edge: uses the plan from state to decide which node to visit next.
    """
    plan = state.get("plan", {})
    current_step_id = state.get("current_step_id", "1")

    if not plan or current_step_id not in plan:
        return "END"

    action = plan[current_step_id].get("action", "suggest")

    # Map action names to graph node keys
    mapping = {
        "suggest_citations": "suggest_citations",
        "code_executor": "code_executor",
        "verify_consistency": "verify_consistency",
        "find_relation": "find_relation",
        "flag_gaps": "flag_gaps",
        "format_citation": "format_citation",
        "hil_context": "hil_context",
        "hil_verify": "hil_verify",
    }

    return mapping.get(action, "END")


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
        "action_history": state.get("action_history", [])
        + [
            {
                "action": "suggest_citations",
                "outcome": (
                    "Found citation candidates."
                    if "📌 Cite" in reply
                    else "No candidates found."
                ),
            }
        ],
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
        "action_history": state.get("action_history", [])
        + [
            {
                "action": "verify_consistency",
                "outcome": f"Verified claim. Found {len(gaps)} gaps.",
            }
        ],
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
            "action_history": state.get("action_history", [])
            + [
                {
                    "action": "find_relation",
                    "outcome": f"Found {len(parsed)} candidates for gap. Escalated to HIL.",
                }
            ],
            "loop_count": state.get("loop_count", 0) + 1,
        }
        return update

    # All gaps exhausted without a parseable result
    update = {
        "action_history": state.get("action_history", [])
        + [
            {
                "action": "find_relation",
                "outcome": "No related data found for any gaps.",
            }
        ],
        "loop_count": state.get("loop_count", 0) + 1,
    }

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
        "action_history": state.get("action_history", [])
        + [{"action": "hil_verify", "outcome": f"Human decided: {action}."}],
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
        "action_history": state.get("action_history", [])
        + [{"action": "format_citation", "outcome": "Formatted citation."}],
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
        "action_history": state.get("action_history", [])
        + [{"action": "flag_gaps", "outcome": "Identified unsupported claims."}],
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
        "action_history": state.get("action_history", [])
        + [
            {
                "action": "find_facts",
                "outcome": f"Extracted {len(reply.get('response', {}))} claims from slides.",
            }
        ],
        "loop_count": state.get("loop_count", 0) + 1,
    }
    return update
