"""
CiteMind — Citation panel callbacks.
Handles citation tab filtering, action buttons (confirm/reject/edit), and live updates.
"""
from __future__ import annotations

import json
import logging

from dash import Input, Output, State, callback_context, dcc, html, no_update
from dash.exceptions import PreventUpdate

from components.citation_panel import build_citation_card
from db.queries import (
    get_citations_for_project,
    get_citations_for_slide,
    update_citation_status,
)

log = logging.getLogger(__name__)


def register_citation_callbacks(app):

    # ─────────────────────────────────────────────────────────
    # HIL Verification Card Rendering
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("hil-verification-container", "children"),
        Input("store-hil-payload", "data"),
    )
    def render_hil_card(payload):
        if not payload:
            return None
            
        payload_type = payload.get("type")
        if payload_type == "relation_verification":
            claim = payload.get("claim", "")
            candidates = payload.get("candidates", [])
            match = candidates[0] if candidates else {}
            
            return html.Div([
                html.Div("⚠️ Gap found — AI suggested a match", className="hil-card-header", style={"fontWeight": "bold", "color": "#f59e0b"}),
                html.Div([
                    html.Strong("Slide claim: "), html.Span(claim)
                ], className="hil-card-row"),
                html.Div([
                    html.Strong("Sheet match: "), html.Span(match.get("row_ref", "Unknown"))
                ], className="hil-card-row"),
                html.Div([
                    html.Strong("Confidence: "), html.Span(match.get("match_strength", "Unknown"))
                ], className="hil-card-row"),
                html.Div([
                    html.Strong("Reason: "), html.Span(match.get("reason", "Unknown"))
                ], className="hil-card-row"),
                html.Div([
                    html.Button("✓ Accept", id="hil-accept-btn", className="ghost-btn ghost-btn-confirm", n_clicks=0),
                    html.Button("✗ Reject", id="hil-reject-btn", className="ghost-btn ghost-btn-reject", n_clicks=0),
                ], className="citation-actions", style={"marginTop": "10px"})
            ], className="hil-verification-card", style={"border": "1px solid #f59e0b", "padding": "10px", "borderRadius": "8px", "marginBottom": "15px"})
            
        elif payload_type == "context_clarification":
            msg = payload.get("message", "Please clarify context scope")
            return html.Div([
                html.Div("❓ Need Clarification", className="hil-card-header", style={"fontWeight": "bold", "color": "#3b82f6"}),
                html.Div(msg, className="hil-card-row", style={"marginBottom": "10px"}),
                html.Div([
                    html.Button("✓ Confirm", id="hil-accept-btn", className="ghost-btn ghost-btn-confirm", n_clicks=0),
                    html.Button("✗ Skip Scope", id="hil-reject-btn", className="ghost-btn ghost-btn-reject", n_clicks=0),
                ], className="citation-actions")
            ], className="hil-verification-card", style={"border": "1px solid #3b82f6", "padding": "10px", "borderRadius": "8px", "marginBottom": "15px"})
            
        return None

    # ─────────────────────────────────────────────────────────
    # Tab Switching & Status Filtering
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("cit-tab-all", "className"),
        Output("cit-tab-pending", "className"),
        Output("cit-tab-confirmed", "className"),
        Output("citation-list", "children"),
        Input("cit-tab-all", "n_clicks"),
        Input("cit-tab-pending", "n_clicks"),
        Input("cit-tab-confirmed", "n_clicks"),
        Input("store-citations", "data"),
        State("store-project-id", "data"),
        State("store-current-slide-idx", "data"),
        State("store-slide-ids", "data"),
        State("store-active-citation", "data"),
    )
    def render_citation_list(
        btn_all, btn_pen, btn_con, cits_data, pid, slide_idx, slide_ids, active_cit
    ):
        if not pid or not slide_ids:
            raise PreventUpdate

        ctx = callback_context
        active_tab = "all"
        if ctx.triggered:
            trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
            if trigger_id == "cit-tab-pending":
                active_tab = "pending"
            elif trigger_id == "cit-tab-confirmed":
                active_tab = "confirmed"

        all_cits = get_citations_for_project(pid)
        slide_cits = get_citations_for_slide(pid, slide_ids[slide_idx])
        display_cits = slide_cits if slide_cits else all_cits

        filtered = []
        for c in display_cits:
            if active_tab == "pending" and c["status"] not in ("pending", "needs_review"):
                continue
            if active_tab == "confirmed" and c["status"] != "confirmed":
                continue
            
            # Decorate for active state
            if active_cit and c["id"] == active_cit:
                c["is_active"] = True
            
            filtered.append(c)

        if not filtered:
            empty_state = html.Div(
                [
                    html.Div("📎", className="empty-state-icon"),
                    html.Div(f"No {active_tab} citations", className="empty-state-text"),
                ],
                className="empty-state",
            )
            return _tab_classes(active_tab) + (empty_state,)

        cards = [build_citation_card(c) for c in filtered]
        return _tab_classes(active_tab) + (cards,)

    def _tab_classes(active_tab):
        return (
            "citation-tab-btn active" if active_tab == "all" else "citation-tab-btn",
            "citation-tab-btn active" if active_tab == "pending" else "citation-tab-btn",
            "citation-tab-btn active" if active_tab == "confirmed" else "citation-tab-btn",
        )

    # ─────────────────────────────────────────────────────────
    # Action Buttons: Confirm & Reject
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-citations", "data", allow_duplicate=True),
        Input({"type": "confirm-btn", "cit_id": "ALL"}, "n_clicks"),
        State({"type": "confirm-btn", "cit_id": "ALL"}, "id"),
        prevent_initial_call=True,
    )
    def handle_confirm(n_clicks_list, ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger = ctx.triggered[0]
        if trigger["value"] == 0:
            raise PreventUpdate

        cit_id = json.loads(trigger["prop_id"].split(".")[0])["cit_id"]
        update_citation_status(cit_id, "confirmed", source="human")
        
        # Trigger re-render by incrementing dummy update store
        return [{"ts": trigger["prop_id"]}]

    @app.callback(
        Output("store-citations", "data", allow_duplicate=True),
        Input({"type": "reject-btn", "cit_id": "ALL"}, "n_clicks"),
        State({"type": "reject-btn", "cit_id": "ALL"}, "id"),
        prevent_initial_call=True,
    )
    def handle_reject(n_clicks_list, ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger = ctx.triggered[0]
        if trigger["value"] == 0:
            raise PreventUpdate

        cit_id = json.loads(trigger["prop_id"].split(".")[0])["cit_id"]
        update_citation_status(cit_id, "rejected", source="human")
        
        return [{"ts": trigger["prop_id"]}]

    # ─────────────────────────────────────────────────────────
    # Action Buttons: Edit (Set Active)
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-active-citation", "data"),
        Input({"type": "edit-btn", "cit_id": "ALL"}, "n_clicks"),
        State({"type": "edit-btn", "cit_id": "ALL"}, "id"),
        prevent_initial_call=True,
    )
    def handle_edit(n_clicks_list, ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger = ctx.triggered[0]
        if trigger["value"] == 0:
            raise PreventUpdate

        cit_id = json.loads(trigger["prop_id"].split(".")[0])["cit_id"]
        return cit_id
