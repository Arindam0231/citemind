"""
CiteMind — Excel data preview strip component.
Compact table display at the bottom of the slide panel.
"""
from __future__ import annotations

from typing import List, Optional

from dash import html


def build_excel_strip() -> html.Div:
    """Build the empty excel strip container."""
    return html.Div(
        [
            html.Div(
                [
                    html.Span("EXCEL DATA", className="excel-strip-title"),
                    html.Div(id="sheet-tabs", className="sheet-tabs"),
                ],
                className="excel-strip-header",
            ),
            html.Div(
                html.Div(
                    [
                        html.Div("📈", className="empty-state-icon"),
                        html.Div("Upload .xlsx to see data", className="empty-state-text"),
                    ],
                    className="empty-state",
                ),
                id="excel-strip-table",
                className="excel-strip-content",
            ),
        ],
        className="excel-strip",
    )


def build_sheet_tabs(sheet_names: List[str], active: Optional[str] = None) -> List[html.Button]:
    """Build sheet tab buttons."""
    tabs = []
    for name in sheet_names:
        is_active = name == active or (active is None and name == sheet_names[0])
        tabs.append(
            html.Button(
                name,
                id={"type": "sheet-tab-btn", "sheet": name},
                className="sheet-tab-btn{}".format(" active" if is_active else ""),
                n_clicks=0,
            )
        )
    return tabs


def build_mini_table(
    headers: List[str],
    rows: List[List[str]],
    cited_cells: Optional[List[str]] = None,
) -> html.Table:
    """Build a compact table for the excel strip."""
    cited = set(cited_cells or [])

    header_row = html.Thead(
        html.Tr([html.Th(h) for h in headers])
    )

    body_rows = []
    for row_data in rows[:50]:  # limit display to 50 rows
        cells = []
        for cell_val in row_data:
            cls = "cited" if str(cell_val) in cited else ""
            cells.append(html.Td(str(cell_val), className=cls))
        body_rows.append(html.Tr(cells))

    return html.Table(
        [header_row, html.Tbody(body_rows)],
        className="mini-table",
    )
