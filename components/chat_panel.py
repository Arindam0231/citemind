"""
CiteMind — AI chat panel component.
Message scroll, context pills, suggestion chips, and input.
"""
from __future__ import annotations

from typing import List, Optional

from dash import html, dcc


QUICK_CHIPS = [
    "Scan this slide for citations",
    "Find source for selected value",
    "Show all unsupported claims",
    "Verify numbers on this slide",
    "What data supports this?",
    "Summarize citation coverage",
]


def build_chat_panel() -> html.Div:
    """Build the right chat panel."""
    return html.Div(
        [
            # Panel header
            html.Div(
                html.Div("AI Assistant", className="chat-panel-title"),
                className="chat-panel-header",
            ),
            # Messages area
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("🔬", className="chat-welcome-icon"),
                            html.H3("CiteMind"),
                            html.P(
                                "Upload your files, then select shapes "
                                "or ask me to find citations."
                            ),
                        ],
                        className="chat-welcome",
                    ),
                ],
                id="chat-messages",
                className="chat-scroll",
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
                        placeholder="Ask about citations...",
                        n_blur=0,
                        style={"height": "40px"},
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
    )


def render_chat_bubbles(
    messages: List[dict],
    is_loading: bool = False,
) -> List[html.Div]:
    """Render chat messages as bubbles."""
    if not messages:
        return [
            html.Div(
                [
                    html.Div("🔬", className="chat-welcome-icon"),
                    html.H3("CiteMind"),
                    html.P(
                        "Upload your files, then select shapes "
                        "or ask me to find citations."
                    ),
                ],
                className="chat-welcome",
            ),
        ]

    bubbles = []  # type: List[html.Div]
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "user":
            bubbles.append(
                html.Div(
                    [
                        html.Span("You", className="bubble-label"),
                        html.Div(_format_message(content)),
                    ],
                    className="bubble-user",
                )
            )
        else:
            bubbles.append(
                html.Div(
                    [
                        html.Span("CiteMind", className="bubble-label"),
                        html.Div(_format_agent_message(content)),
                    ],
                    className="bubble-agent",
                )
            )

    if is_loading:
        bubbles.append(
            html.Div(
                [
                    html.Div(className="orbital"),
                    html.Span("Analyzing...", className="loading-text"),
                ],
                className="loading-bubble",
            )
        )

    return bubbles


def _format_message(text: str) -> list:
    """Format a user message preserving line breaks."""
    lines = text.split("\n")
    parts = []  # type: list
    for i, line in enumerate(lines):
        parts.append(line)
        if i < len(lines) - 1:
            parts.append(html.Br())
    return parts


def _format_agent_message(text: str) -> list:
    """Format agent message with citation styling."""
    lines = text.split("\n")
    parts = []  # type: list
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("✅"):
            parts.append(html.Span(line, className="cite-supported"))
        elif stripped.startswith("⚠️"):
            parts.append(html.Span(line, className="cite-gap"))
        elif stripped.startswith("📌"):
            parts.append(html.Span(line, className="cite-ref"))
        elif "[Sheet:" in line:
            parts.append(html.Span(line, className="cite-ref"))
        else:
            parts.append(html.Span(line))

        if i < len(lines) - 1:
            parts.append(html.Br())

    return parts
