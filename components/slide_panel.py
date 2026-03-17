"""
CiteMind — Slide panel component.
Displays the slide as rendered HTML with shape overlays and navigation.
"""
from __future__ import annotations

import json
from typing import List, Optional

from dash import html, dcc


def build_slide_panel() -> html.Div:
    """Build the left slide panel with viewer, overlays, and excel strip."""
    return html.Div(
        [
            # Slide navigation bar
            html.Div(
                [
                    html.Button(
                        "← Prev",
                        id="slide-prev-btn",
                        className="slide-nav-btn",
                        n_clicks=0,
                    ),
                    html.Span(
                        "Slide 0 / 0",
                        id="slide-counter",
                        className="slide-counter",
                    ),
                    html.Button(
                        "Next →",
                        id="slide-next-btn",
                        className="slide-nav-btn",
                        n_clicks=0,
                    ),
                ],
                className="slide-nav",
            ),
            # Slide viewer area
            html.Div(
                html.Div(
                    [
                        # HTML-rendered slide (replaces LibreOffice PNG)
                        html.Iframe(
                            id="slide-html-render",
                            className="slide-html-render",
                            style={"display": "none"},
                            srcDoc="",
                        ),
                        # Placeholder when no slide is loaded
                        html.Div(
                            [
                                html.Div("📊", className="slide-placeholder-icon"),
                                html.Div("Upload a .pptx to view slides"),
                            ],
                            id="slide-placeholder",
                            className="slide-placeholder",
                        ),
                        # Shape overlays container (positioned on top of the HTML render)
                        html.Div(
                            id="shape-overlays",
                            className="shape-overlays",
                        ),
                        # Canvas for drag selection
                        html.Canvas(
                            id="selection-canvas",
                            className="selection-canvas",
                        ),
                    ],
                    id="slide-container",
                    className="slide-container",
                ),
                className="slide-viewer",
            ),
            # Excel strip at bottom
            html.Div(id="excel-strip-container", className="excel-strip"),
        ],
        className="slide-panel",
    )


def build_shape_overlay(shape: dict) -> html.Div:
    """Build a single shape overlay div with run spans."""
    runs = json.loads(shape.get("runs_json") or "[]")
    run_spans = []
    for r in runs:
        run_spans.append(
            html.Span(
                r["text"],
                **{"data-run": str(r["index"])},
                className="citable-run" if r.get("is_numeric") else "plain-run",
            )
        )

    return html.Div(
        run_spans or shape.get("full_text", ""),
        className="shape-overlay",
        id={"type": "shape-overlay", "shape_id": shape["id"]},
        **{"data-shape-id": shape["id"]},
        n_clicks=0,
        style={
            "position": "absolute",
            "left": "{:.3f}%".format(shape["x_pct"] * 100),
            "top": "{:.3f}%".format(shape["y_pct"] * 100),
            "width": "{:.3f}%".format(shape["w_pct"] * 100),
            "height": "{:.3f}%".format(shape["h_pct"] * 100),
            "cursor": "pointer",
            "zIndex": 10,
            "userSelect": "text",
        },
    )
