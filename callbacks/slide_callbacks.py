"""
CiteMind — Slide and App callbacks.
Handles file upload, slide navigation, and rendering shape overlays.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from dash import Input, Output, State, callback_context, dcc, html, no_update
from dash.exceptions import PreventUpdate

from components.slide_panel import build_shape_overlay
from db.queries import (
    create_project,
    get_citation,
    get_citations_for_project,
    get_citations_for_slide,
    get_excel_sheets,
    get_project_stats,
    get_shapes_for_slide,
    get_slide,
    get_slides_for_pptx,
    insert_cells_bulk,
    insert_excel_sheet,
    insert_pptx_file,
    insert_shape,
    insert_shapes_bulk,
    insert_slide,
    insert_xlsx_file,
    mark_pptx_parsed,
    mark_xlsx_parsed,
)
from parsers.pptx_parser import parse_pptx_file
from parsers.slide_renderer import render_slide_to_html
from parsers.xlsx_parser import parse_workbook

log = logging.getLogger(__name__)


def register_slide_callbacks(app):

    # ─────────────────────────────────────────────────────────
    # 1. File Upload & Project Initialization
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("pptx-badge", "className"),
        Output("pptx-badge", "children"),
        Output("store-pptx-filename", "data"),
        Output("store-pptx-file-id", "data"),
        Output("store-pptx-file-temp", "data"),
        Input("upload-pptx", "contents"),
        State("upload-pptx", "filename"),
        prevent_initial_call=True,
    )
    def upload_pptx(contents, filename):
        if not contents:
            raise PreventUpdate
        try:
            parsed = parse_pptx_file(contents)
            # Insert file record
            fid = insert_pptx_file(
                original_name=filename,
                storage_path="",  # We're holding it in memory/DB for now
                slide_count=parsed["slide_count"],
                slide_width_emu=parsed["slide_width_emu"],
                slide_height_emu=parsed["slide_height_emu"],
                sha256=parsed["sha256"],
            )

            # Save raw file temporarily for slide renderer
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(tmp_dir, f"{fid}.pptx")
            if "," in contents:
                raw_bytes = base64.b64decode(contents.split(",", 1)[1])
                with open(tmp_path, "wb") as f:
                    f.write(raw_bytes)

            # Insert slides & shapes
            for s in parsed["slides"]:
                sid = insert_slide(
                    pptx_file_id=fid,
                    slide_index=s["slide_index"],
                    slide_number=s["slide_number"],
                    title=s["title"],
                    shape_count=s["shape_count"],
                    has_table=s["has_table"],
                    has_chart=s["has_chart"],
                )
                if s["shapes"]:
                    bulk_shapes = []
                    for sh in s["shapes"]:
                        sh["slide_id"] = sid
                        bulk_shapes.append(sh)
                    insert_shapes_bulk(bulk_shapes)

            mark_pptx_parsed(fid)

            return (
                "file-badge loaded",
                [html.Span(className="dot"), f" ✓ {filename}"],
                filename,
                fid,
                tmp_path,
            )
        except Exception as e:
            log.error("PPTX error: %s", e)
            return "file-badge", [html.Span(className="dot"), " PPTX"], None, None

    @app.callback(
        Output("xlsx-badge", "className"),
        Output("xlsx-badge", "children"),
        Output("store-xlsx-filename", "data"),
        Output("store-xlsx-file-id", "data"),
        Output("store-sheets-raw", "data"),
        Input("upload-xlsx", "contents"),
        State("upload-xlsx", "filename"),
        prevent_initial_call=True,
    )
    def upload_xlsx(contents, filename):
        if not contents:
            raise PreventUpdate
        try:
            parsed = parse_workbook(contents)

            fid = insert_xlsx_file(
                original_name=filename,
                storage_path="",
                sheet_names=parsed["sheet_names"],
                sha256=parsed["sha256"],
            )

            # Insert sheets & cells
            for sname, sdata in parsed["sheets"].items():
                sid = insert_excel_sheet(
                    xlsx_file_id=fid,
                    sheet_name=sname,
                    sheet_index=sdata["sheet_index"],
                    row_count=sdata["row_count"],
                    col_count=sdata["col_count"],
                    header_row=sdata["header_row"],
                    headers_json=json.dumps(sdata["headers"]),
                )
                if sdata["cells"]:
                    bulk_cells = []
                    for c in sdata["cells"]:
                        c["sheet_id"] = sid
                        bulk_cells.append(c)
                    insert_cells_bulk(bulk_cells)

            mark_xlsx_parsed(fid)

            return (
                "file-badge loaded",
                [html.Span(className="dot"), f" ✓ {filename}"],
                filename,
                fid,
                parsed["sheets"],
            )
        except Exception as e:
            log.error("XLSX error: %s", e)
            return "file-badge", [html.Span(className="dot"), " XLSX"], None, None, {}

    # ─────────────────────────────────────────────────────────
    # 2. Workspace View Transition
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("upload-landing", "style"),
        Output("main-workspace", "style"),
        Output("store-project-id", "data"),
        Output("store-slide-ids", "data"),
        Input("store-pptx-file-id", "data"),
        Input("store-xlsx-file-id", "data"),
        prevent_initial_call=True,
    )
    def initialize_project(pptx_fid, xlsx_fid):
        if pptx_fid and xlsx_fid:
            pid = create_project("CiteMind Project", pptx_fid, xlsx_fid)
            slides = get_slides_for_pptx(pptx_fid)
            slide_ids = [s["id"] for s in slides]
            return {"display": "none"}, {"display": "grid"}, pid, slide_ids
        return {"display": "flex"}, {"display": "none"}, None, []

    # ─────────────────────────────────────────────────────────
    # 3. Slide Navigation & Rendering
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-current-slide-idx", "data"),
        Input("slide-prev-btn", "n_clicks"),
        Input("slide-next-btn", "n_clicks"),
        State("store-current-slide-idx", "data"),
        State("store-slide-ids", "data"),
        prevent_initial_call=True,
    )
    def navigate_slides(btn_prev, btn_next, current_idx, slide_ids):
        if not slide_ids:
            raise PreventUpdate
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_id == "slide-prev-btn":
            new_idx = max(0, current_idx - 1)
        else:
            new_idx = min(len(slide_ids) - 1, current_idx + 1)

        if new_idx == current_idx:
            raise PreventUpdate
        return new_idx

    @app.callback(
        Output("slide-prev-btn", "disabled"),
        Output("slide-next-btn", "disabled"),
        Output("slide-counter", "children"),
        Output("slide-placeholder", "style"),
        Output("slide-html-render", "style"),
        Output("slide-html-render", "srcDoc"),
        Output("shape-overlays", "children"),
        Output("store-slide-shapes", "data"),
        Input("store-current-slide-idx", "data"),
        Input("store-slide-ids", "data"),
        Input("store-project-id", "data"),
        Input("store-pptx-file-id", "data"),
        Input("store-pptx-file-temp", "data"),
        prevent_initial_call=True,
    )
    def render_current_slide(
        current_idx, slide_ids, project_id, pptx_fid, pptx_temp_path
    ):
        if not slide_ids or project_id is None:
            raise PreventUpdate
        slide_id = slide_ids[current_idx]
        total = len(slide_ids)
        counter_text = f"Slide {current_idx + 1} / {total}"
        prev_disabled = current_idx == 0
        next_disabled = current_idx == total - 1

        # Render slide to HTML/CSS via python-pptx (no LibreOffice needed)

        slide_html = ""
        if os.path.exists(pptx_temp_path):
            try:
                with open(pptx_temp_path, "rb") as f:
                    pptx_bytes = f.read()
                slide_html = render_slide_to_html(pptx_bytes, current_idx)

            except Exception as e:
                log.error("HTML render error: %s", e)

        render_style = {"display": "none"}
        placeholder_style = {"display": "flex"}
        src_doc = ""
        if slide_html:
            render_style = {
                "display": "block",
                "position": "absolute",
                "inset": "0",
                "width": "100%",
                "height": "100%",
                "border": "none",
            }
            placeholder_style = {"display": "none"}
            src_doc = slide_html

        # Get shapes & citations
        shapes = get_shapes_for_slide(slide_id)
        # citations = get_citations_for_slide(project_id, slide_id)

        # # Build overlays
        overlays = []
        # for s in shapes:
        #     overlay = build_shape_overlay(s)

        #     # Apply citation status colors
        #     shape_cits = [c for c in citations if c["shape_id"] == s["id"]]
        #     if shape_cits:
        #         status_set = {c["status"] for c in shape_cits}
        #         if "pending" in status_set:
        #             overlay.className += " has-pending"
        #         elif "rejected" in status_set:
        #             overlay.className += " has-rejected"
        #         else:
        #             overlay.className += " has-confirmed"

        #     overlays.append(overlay)

        return (
            prev_disabled,
            next_disabled,
            counter_text,
            placeholder_style,
            render_style,
            src_doc,
            overlays,
            shapes,
        )

    # ─────────────────────────────────────────────────────────
    # 4. Header Stats Update
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("stat-confirmed-num", "children"),
        Output("stat-pending-num", "children"),
        Output("stat-rejected-num", "children"),
        Input("store-citations", "data"),  # Trigger on citation updates
        State("store-project-id", "data"),
        prevent_initial_call=True,
    )
    def update_header_stats(dummy_cits, project_id):
        if not project_id:
            raise PreventUpdate
        stats = get_project_stats(project_id)
        return (
            str(stats.get("confirmed", 0)),
            str(stats.get("pending", 0)),
            str(stats.get("rejected", 0)),
        )
