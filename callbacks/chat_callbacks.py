"""
CiteMind — Chat panel callbacks.
UI side only. Hooks form inputs into generating AI responses via LangGraph.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from dash import Input, Output, State, callback_context, dcc, no_update
from dash.exceptions import PreventUpdate

from components.chat_panel import render_chat_bubbles

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
        Input("chat-input", "n_submit"),
        Input({"type": "quick-chip", "index": "ALL"}, "n_clicks"),
        State({"type": "quick-chip", "index": "ALL"}, "children"),
        State("chat-input", "value"),
        State("store-chat-history", "data"),
        prevent_initial_call=True,
    )
    def handle_chat_input(
        send_btn, n_submit, chip_clicks, chip_labels, input_val, history
    ):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        user_message = ""

        if "quick-chip" in trigger_id:
            # Reconstruct the index
            import json
            idx = json.loads(trigger_id)["index"]
            if chip_clicks[idx] > 0:
                user_message = chip_labels[idx]
            else:
                raise PreventUpdate
        else:
            if not input_val or not input_val.strip():
                raise PreventUpdate
            user_message = input_val.strip()

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
        Input("store-loading", "data"),
        State("store-chat-history", "data"),
        State("store-project-id", "data"),
        State("store-current-slide-idx", "data"),
        State("store-slide-ids", "data"),
        State("store-selection", "data"),
        prevent_initial_call=True,
    )
    def process_ai_response(is_loading, history, project_id, slide_idx, slide_ids, selection):
        if not is_loading or not history:
            raise PreventUpdate

        # Only process if last message is user (avoids loops)
        last_msg = history[-1]
        if last_msg["role"] != "user":
            raise PreventUpdate

        try:
            from agent.graph import _get_graph
            
            app_state = {
                "messages": [{"role": "user", "content": last_msg["content"]}],
                "project_id": project_id,
                "slide_id": slide_ids[slide_idx] if slide_ids else None,
                "selection_context": selection,
                "active_sheet_id": None,
                "results": [],
            }
            
            # Invoke Graph
            # In a generic loop, we'll just inject the config thread_id for persistence later
            cfg = {"configurable": {"thread_id": project_id or "default"}}
            graph = _get_graph()
            final_state = executor.submit(graph.invoke, app_state, cfg).result()
            
            agent_msg = ""
            if "messages" in final_state and final_state["messages"]:
                last_ai = final_state["messages"][-1]
                if last_ai.get("role") == "ai" or getattr(last_ai, "type", "") == "ai":
                    agent_msg = getattr(last_ai, "content", "") if not isinstance(last_ai, dict) else last_ai.get("content", "")
            
            if not agent_msg:
                agent_msg = "My scan complete. See citations panel for results."

            history.append({"role": "assistant", "content": agent_msg})

            return history, False, [{"ts": "ai_update"}]
            
        except ImportError:
            # Fallback if graph not ready
            history.append({"role": "assistant", "content": "AI Agent graph not yet implemented."})
            return history, False, [{"ts": "ai_update"}]
        except Exception as e:
            log.error("AI processing error: %s", e)
            history.append({"role": "assistant", "content": f"Failed to reach AI: {e}"})
            return history, False, [{"ts": "ai_update"}]

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
