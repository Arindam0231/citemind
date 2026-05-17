"""
CiteMind — Citation panel component.
Displays citation cards with status, confidence, and action buttons.
"""
from __future__ import annotations

from typing import List, Optional

from dash import html


def build_citation_panel() -> html.Div:
    """Build the citation panel with tabs and card list."""
    return html.Div(
        [
            # Panel header with tabs
            html.Div(
                [
                    html.Div("Citations", className="citation-panel-title"),
                    html.Div(
                        [
                            html.Button(
                                ["All", html.Span("0", id="count-all", className="citation-count-badge")],
                                id="cit-tab-all",
                                className="citation-tab-btn active",
                                n_clicks=0,
                            ),
                            html.Button(
                                ["Pending", html.Span("0", id="count-pending", className="citation-count-badge")],
                                id="cit-tab-pending",
                                className="citation-tab-btn",
                                n_clicks=0,
                            ),
                            html.Button(
                                ["Confirmed", html.Span("0", id="count-confirmed", className="citation-count-badge")],
                                id="cit-tab-confirmed",
                                className="citation-tab-btn",
                                n_clicks=0,
                            ),
                        ],
                        className="citation-tabs",
                    ),
                ],
                className="citation-panel-header",
            ),
            # HIL Verification Card Container
            html.Div(id="hil-verification-container"),
            # Citation cards list
            html.Div(
                html.Div(
                    [
                        html.Div("📎", className="empty-state-icon"),
                        html.Div("No citations yet", className="empty-state-text"),
                    ],
                    className="empty-state",
                ),
                id="citation-list",
                className="citation-list",
            ),
        ],
        className="citation-panel",
    )


def build_citation_card(citation: dict) -> html.Div:
    """Build a single citation card."""
    status = citation.get("status", "pending")
    confidence = citation.get("ai_confidence")
    cit_id = citation.get("id", "")
    short_id = cit_id[:8] if cit_id else ""

    # Confidence formatting
    conf_class = "confidence-low"
    conf_text = "—"
    if confidence is not None:
        conf_text = "{:.0f}%".format(confidence * 100)
        if confidence >= 0.85:
            conf_class = "confidence-high"
        elif confidence >= 0.6:
            conf_class = "confidence-medium"

    # Source info
    source_label = "SOURCE"
    source_value = "—"
    sheet_name = citation.get("sheet_name")
    cell_addr = citation.get("cell_address")
    cell_display = citation.get("cell_display")
    if sheet_name and cell_addr:
        source_label = "{}!{}".format(sheet_name, cell_addr)
        source_value = cell_display or "—"

    # Target info
    shape_name = citation.get("shape_name", "Shape")
    text_snippet = citation.get("text_snippet", "")

    # AI reasoning
    reasoning = citation.get("ai_reasoning", "")

    return html.Div(
        html.Div(
            [
                # Top row: ID + confidence
                html.Div(
                    [
                        html.Span(short_id, className="citation-id"),
                        html.Span(conf_text, className="confidence-badge {}".format(conf_class)),
                    ],
                    className="citation-card-top",
                ),
                # Source box
                html.Div(
                    [
                        html.Div(source_label, className="citation-source-label"),
                        html.Div(source_value, className="citation-source-value"),
                    ],
                    className="citation-source",
                ),
                # Arrow
                html.Div("→", className="citation-arrow"),
                # Target box
                html.Div(
                    [
                        html.Div(shape_name, className="citation-target-label"),
                        html.Div(text_snippet, className="citation-target-value"),
                    ],
                    className="citation-target",
                ),
                # Reasoning
                html.Div(reasoning, className="citation-reasoning") if reasoning else None,
                # Action buttons
                html.Div(
                    [
                        html.Button(
                            "✓ Confirm",
                            id={"type": "confirm-btn", "cit_id": cit_id},
                            className="ghost-btn ghost-btn-confirm",
                            n_clicks=0,
                        ),
                        html.Button(
                            "✗ Reject",
                            id={"type": "reject-btn", "cit_id": cit_id},
                            className="ghost-btn ghost-btn-reject",
                            n_clicks=0,
                        ),
                        html.Button(
                            "✎ Edit",
                            id={"type": "edit-btn", "cit_id": cit_id},
                            className="ghost-btn ghost-btn-edit",
                            n_clicks=0,
                        ),
                    ],
                    className="citation-actions",
                ),
            ],
            className="citation-card-inner status-{}".format(status),
        ),
        className="citation-card{}".format(
            " active" if citation.get("is_active") else ""
        ),
        id={"type": "citation-card", "cit_id": cit_id},
    )
