"""
Checkmate — Dash layout builder (Antigravity theme).
"""
from dash import html, dcc


# ── Quick-chip labels ───────────────────────────────────
QUICK_CHIPS = [
    "Find unsupported claims across all slides",
    "Verify numbers on the current slide",
    "Which rows support this slide?",
    "Format citation for selected data",
    "Show me all ⚠️ gaps",
    "Summarize the Excel data",
]


def _upload_zone(file_type: str) -> html.Div:
    """Inner content for an upload drop-zone."""
    icon = "📊" if file_type == "pptx" else "📈"
    label = ".pptx file" if file_type == "pptx" else ".xlsx file"
    return html.Div(
        [
            html.Div(icon, className="drop-zone-icon"),
            html.Div(f"Drop {label} here", className="drop-zone-label"),
            html.Div("or click to browse", className="drop-zone-hint"),
        ],
        className="drop-zone",
    )


def build_layout() -> html.Div:
    """Construct the full Checkmate Antigravity layout."""
    return html.Div(
        [
            # ── Hidden stores ────────────────────────────
            dcc.Store(id="store-slides", data=[]),
            dcc.Store(id="store-sheets", data={}),
            dcc.Store(id="store-messages", data=[]),
            dcc.Store(id="store-selected-slide", data=None),
            dcc.Store(id="store-selected-sheet", data=None),
            dcc.Store(id="store-pptx-filename", data=None),
            dcc.Store(id="store-xlsx-filename", data=None),
            dcc.Store(id="store-loading", data=False),

            # ── Header ──────────────────────────────────
            html.Header(
                [
                    html.Div(
                        [
                            html.Div("C", className="logo-icon"),
                            html.Span("Checkmate", className="logo-text"),
                        ],
                        className="logo-group",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.Span(className="dot"), "PPTX"],
                                id="pptx-status",
                                className="status-pill",
                            ),
                            html.Div(
                                [html.Span(className="dot"), "XLSX"],
                                id="xlsx-status",
                                className="status-pill",
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

            # ── Upload row ──────────────────────────────
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
                id="upload-row",
            ),

            # ── Main split ──────────────────────────────
            html.Div(
                [
                    # ── Left panel ───────────────────────
                    html.Div(
                        [
                            # Tab bar
                            html.Div(
                                [
                                    html.Button(
                                        "Slides",
                                        id="tab-slides-btn",
                                        className="doc-tab active",
                                        n_clicks=0,
                                    ),
                                    html.Button(
                                        "Data",
                                        id="tab-data-btn",
                                        className="doc-tab",
                                        n_clicks=0,
                                    ),
                                ],
                                className="tab-container",
                            ),
                            # Tab content
                            html.Div(
                                id="tab-content",
                                className="tab-content",
                                children=[
                                    html.Div(
                                        className="empty-state",
                                        children=[
                                            html.Div("📊", className="empty-state-icon"),
                                            html.Div(
                                                "Upload a .pptx to view slides",
                                                className="empty-state-text",
                                            ),
                                        ],
                                    )
                                ],
                            ),
                            # Slide preview
                            html.Div(
                                id="slide-preview",
                                className="slide-preview",
                                style={"display": "none"},
                            ),
                        ],
                        className="left-panel",
                    ),

                    # ── Chat panel ───────────────────────
                    html.Div(
                        [
                            # Messages area
                            html.Div(
                                id="chat-messages",
                                className="chat-scroll",
                                children=[
                                    html.Div(
                                        [
                                            html.Div("🔬", className="chat-welcome-icon"),
                                            html.H3("Welcome to Checkmate"),
                                            html.P(
                                                "Upload your PowerPoint and Excel files, "
                                                "then ask me to find citations, verify numbers, "
                                                "or identify unsupported claims."
                                            ),
                                        ],
                                        className="chat-welcome",
                                    )
                                ],
                            ),
                            # Quick chips
                            html.Div(
                                [
                                    html.Button(
                                        chip,
                                        id={"type": "quick-chip", "index": i},
                                        className="quick-chip",
                                        n_clicks=0,
                                    )
                                    for i, chip in enumerate(QUICK_CHIPS)
                                ],
                                className="quick-chips",
                                id="quick-chips-bar",
                            ),
                            # Input row
                            html.Div(
                                [
                                    dcc.Textarea(
                                        id="chat-input",
                                        className="chat-input",
                                        placeholder="Ask about citations, data verification, or gaps...",
                                        n_blur=0,
                                        style={"height": "44px"},
                                    ),
                                    html.Button(
                                        "↑",
                                        id="send-btn",
                                        className="send-btn",
                                        n_clicks=0,
                                    ),
                                ],
                                className="input-row",
                            ),
                        ],
                        className="chat-panel",
                    ),
                ],
                className="main-layout",
            ),
        ],
        className="app-root",
    )
