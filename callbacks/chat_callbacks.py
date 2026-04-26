"""
Checkmate — Chat panel callbacks.
UI side only. Hooks form inputs into generating AI responses via LangGraph.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from dash import Input, Output, State, callback_context, dcc, no_update
from dash.exceptions import PreventUpdate

from components.chat_panel import render_chat_bubbles
from agent.graph import get_graph
log = logging.getLogger(__name__)

# Executor for sync graph calls to avoid blocking Dash reactor thread
executor = ThreadPoolExecutor(max_workers=4)


def register_chat_callbacks(app):

    # ─────────────────────────────────────────────────────────
    # Chat Input / Quick Chip Submit
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-chat-history", "data", allow_duplicate=True),
        Output("chat-input", "value"),
        Output("store-loading", "data"),
        Input("send-btn", "n_clicks"),
        State("chat-input", "value"),
        State("store-chat-history", "data"),
        prevent_initial_call=True,
    )
    def handle_chat_input(send_btn, input_val, history):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        user_message = (input_val or "").strip()
        if not user_message:
            raise PreventUpdate

        if not history:
            history = []

        history.append({"role": "user", "content": user_message})
        return history, "", True

    # ─────────────────────────────────────────────────────────
    # Async AI Resolution (stubbed until agent node hook)
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-chat-history", "data"),
        Output("store-loading", "data", allow_duplicate=True),
        Output("store-citations", "data", allow_duplicate=True),
        Output("store-hil-payload", "data"),
        Input("store-loading", "data"),
        State("store-chat-history", "data"),
        State("store-project-id", "data"),
        State("store-current-slide-idx", "data"),
        State("store-slide-ids", "data"),
        State("store-selection", "data"),
        State("store-slide-shapes", "data"),
        State("store-sheets-raw", "data"),
        State("store-pptx-filename", "data"),
        State("store-xlsx-filename", "data"),
        prevent_initial_call=True,
    )
    def process_ai_response(
        is_loading,
        history,
        project_id,
        slide_idx,
        slide_ids,
        selection,
        slide_shapes,
        sheets,
        pptx_filename,
        xlsx_filename,
    ):
        if not is_loading or not history:
            raise PreventUpdate

        # Only process if last message is user (avoids loops)
        last_msg = history[-1]
        if last_msg["role"] != "user":
            raise PreventUpdate

        try:
            query = last_msg["content"]
            cfg = {"configurable": {"thread_id": project_id or "default"}}
            slides = {}
            for sid in slide_ids:
                slides[sid] = []
            for shape in slide_shapes:
                sid = shape.get("slide_id")
                if sid in slides:
                    slides[sid].append(shape)

            app_state = {
                "slides": slides or [],
                "sheets": sheets or {},
                "pptx_filename": pptx_filename or "",
                "xlsx_filename": xlsx_filename or "",
                "messages": [{"role": "user", "content": query}],
                "current_query": query,
            }

            # Invoke Graph
            graph = get_graph()
            final_state = executor.submit(graph.invoke, app_state, cfg).result()

            hil_payload = None
            if isinstance(final_state, dict):
                hil_payload = final_state.get("hil_payload", None)

            agent_msg = ""
            if (
                isinstance(final_state, dict)
                and "messages" in final_state
                and final_state["messages"]
            ):
                last_ai = final_state["messages"][-1]
                if isinstance(last_ai, dict):
                    if last_ai.get("role") in ("ai", "assistant"):
                        agent_msg = last_ai.get("content", "")
                else:
                    if getattr(last_ai, "type", "") in ("ai", "assistant"):
                        agent_msg = getattr(last_ai, "content", "")

            if hil_payload:
                agent_msg = (
                    "Please review the verification card in the Citations panel."
                )
            elif not agent_msg:
                agent_msg = "My scan complete. See citations panel for results."

            history.append({"role": "assistant", "content": agent_msg})

            return history, False, [{"ts": "ai_update"}], hil_payload

        except ImportError as e:
            # Fallback if graph not ready
            history.append(
                {
                    "role": "assistant",
                    "content": f"AI Agent graph not yet implemented: {e}",
                }
            )
            return history, False, [{"ts": "ai_update"}], None
        except Exception as e:
            log.error("AI processing error: %s", e)
            history.append({"role": "assistant", "content": f"Failed to reach AI: {e}"})
            return history, False, [{"ts": "ai_update"}], None

    # ─────────────────────────────────────────────────────────
    # Render Chat History
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("chat-messages", "children"),
        Input("store-chat-history", "data"),
        Input("store-loading", "data"),
    )
    def render_history(history, is_loading):
        history = history or []
        is_loading = bool(is_loading)
        return render_chat_bubbles(history, is_loading)

    # ─────────────────────────────────────────────────────────
    # HIL Action Resumption
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-chat-history", "data", allow_duplicate=True),
        Output("store-hil-payload", "data", allow_duplicate=True),
        Input("hil-accept-btn", "n_clicks"),
        Input("hil-reject-btn", "n_clicks"),
        Input("hil-transform-btn", "n_clicks"),
        State("hil-transform-code", "value"),
        State("store-chat-history", "data"),
        State("store-project-id", "data"),
        prevent_initial_call=True,
    )
    def handle_hil_action(accept_clicks, reject_clicks, transform_clicks, transform_code, history, project_id):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        
        if "accept" in trigger_id:
            action = "accept"
            resume_data = {"action": action}
        elif "transform" in trigger_id:
            action = "transform"
            resume_data = {"action": action, "code": transform_code or ""}
        else:
            action = "reject"
            resume_data = {"action": action}

        cfg = {"configurable": {"thread_id": project_id or "default"}}
        graph = get_graph()

        try:
            from langgraph.types import Command

            # Resume graph with user decision
            final_state = executor.submit(
                graph.invoke, Command(resume=resume_data), cfg
            ).result()

            hil_payload = None
            if isinstance(final_state, dict):
                hil_payload = final_state.get("hil_payload", None)

            agent_msg = ""
            if (
                isinstance(final_state, dict)
                and "messages" in final_state
                and final_state["messages"]
            ):
                last_ai = final_state["messages"][-1]
                if isinstance(last_ai, dict):
                    if last_ai.get("role") in ("ai", "assistant"):
                        agent_msg = last_ai.get("content", "")
                else:
                    if getattr(last_ai, "type", "") in ("ai", "assistant"):
                        agent_msg = getattr(last_ai, "content", "")

            if not agent_msg:
                agent_msg = f"Confirmed user decision: {action}"

            if not history:
                history = []
            history.append({"role": "assistant", "content": agent_msg})

            return history, hil_payload
        except Exception as e:
            log.error("Resume graph error: %s", e)
            if not history:
                history = []
            history.append({"role": "assistant", "content": f"Graph resume error: {e}"})
            return history, None
