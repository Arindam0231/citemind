"""
CiteMind — Dash application entry point.
4-zone layout: Header, Slide Panel, Citations Panel, Chat Panel.
"""

from __future__ import annotations
import os
import sys

import dash
from dash import html, dcc

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from components.slide_panel import build_slide_panel
from components.citation_panel import build_citation_panel
from components.chat_panel import build_chat_panel

app = dash.Dash(
    __name__,
    external_scripts=[
        {"src": "https://cdn.tailwindcss.com"},
    ],
    suppress_callback_exceptions=True,
    title="CiteMind",
    update_title="CiteMind · thinking...",
)


def _upload_zone(file_type: str) -> html.Div:
    """Upload drop-zone content."""
    icon = "📊" if file_type == "pptx" else "📈"
    label = ".pptx file" if file_type == "pptx" else ".xlsx file"
    return html.Div(
        [
            html.Div(icon, className="drop-zone-icon"),
            html.Div("Drop {} here".format(label), className="drop-zone-label"),
            html.Div("or click to browse", className="drop-zone-hint"),
        ],
        className="drop-zone",
    )


def build_layout() -> html.Div:
    """Build the complete CiteMind layout."""
    return html.Div(
        [
            # ── Hidden Stores ──────────────────────────────
            dcc.Store(id="store-session", data={}),
            dcc.Store(id="store-slide-shapes", data=[]),
            dcc.Store(id="store-selection", data={}),
            dcc.Store(id="store-drag", data={}),
            dcc.Store(id="store-citations", data=[]),
            dcc.Store(id="store-chat-history", data=[]),
            dcc.Store(id="store-active-citation", data=None),
            # Additional state stores
            dcc.Store(id="store-project-id", data=None),
            dcc.Store(id="store-pptx-file-id", data=None),
            dcc.Store(id="store-pptx-file-temp", data=None),
            dcc.Store(id="store-xlsx-file-id", data=None),
            dcc.Store(id="store-current-slide-idx", data=0),
            dcc.Store(id="store-slide-ids", data=[]),
            dcc.Store(id="store-pptx-filename", data=None),
            dcc.Store(id="store-xlsx-filename", data=None),
            dcc.Store(id="store-sheets-raw", data={}),
            dcc.Store(id="store-loading", data=False),
            dcc.Store(id="store-selected-sheet", data=None),
            # ── Header ─────────────────────────────────────
            html.Header(
                [
                    html.Div(
                        [
                            html.Div("C", className="logo-icon"),
                            html.Span("CiteMind", className="logo-text"),
                        ],
                        className="logo-group",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.Span(className="dot"), "PPTX"],
                                id="pptx-badge",
                                className="file-badge",
                            ),
                            html.Div(
                                [html.Span(className="dot"), "XLSX"],
                                id="xlsx-badge",
                                className="file-badge",
                            ),
                        ],
                        className="header-center",
                    ),
                    html.Div(
                        [
                            html.Span(
                                ["✓ ", html.Span("0", id="stat-confirmed-num")],
                                className="stat-badge stat-confirmed",
                            ),
                            html.Span(
                                ["◯ ", html.Span("0", id="stat-pending-num")],
                                className="stat-badge stat-pending",
                            ),
                            html.Span(
                                ["✗ ", html.Span("0", id="stat-rejected-num")],
                                className="stat-badge stat-rejected",
                            ),
                            html.Div(
                                "claude-sonnet-4-20250514",
                                className="model-badge",
                            ),
                        ],
                        className="header-right",
                    ),
                ],
                className="app-header",
            ),
            # ── Upload Landing ──────────────────────────────
            html.Div(
                [
                    html.Div("CiteMind", className="upload-title"),
                    html.Div(
                        "Upload your PowerPoint and Excel files to begin "
                        "linking citations between slides and data.",
                        className="upload-subtitle",
                    ),
                    html.Div(
                        [
                            dcc.Upload(
                                id="upload-pptx",
                                children=_upload_zone("pptx"),
                                className="upload-component",
                                accept=".pptx",
                            ),
                            dcc.Upload(
                                id="upload-xlsx",
                                children=_upload_zone("xlsx"),
                                className="upload-component",
                                accept=".xlsx",
                            ),
                        ],
                        className="upload-row",
                    ),
                ],
                id="upload-landing",
                className="upload-landing",
            ),
            # ── Main 3-Column Workspace ─────────────────────
            html.Div(
                [
                    build_slide_panel(),
                    build_citation_panel(),
                    build_chat_panel(),
                ],
                id="main-workspace",
                className="main-workspace",
                style={"display": "none"},
            ),
        ],
        className="app-root",
    )


app.layout = build_layout()

# ── Register callbacks ──────────────────────────────────
from callbacks.slide_callbacks import register_slide_callbacks

from callbacks.citation_callbacks import register_citation_callbacks
from callbacks.chat_callbacks import register_chat_callbacks
from callbacks.selection_callbacks import register_selection_callbacks

register_slide_callbacks(app)
register_citation_callbacks(app)
register_chat_callbacks(app)
register_selection_callbacks(app)


server = app.server


@server.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


if __name__ == "__main__":
    app.run(debug=True, port=8080)
