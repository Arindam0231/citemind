"""
CiteMind — Slide and App callbacks.
Handles file upload, slide navigation, and rendering shape overlays.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from dash import Input, Output, State, callback_context, dcc, html, no_update, ALL
from dash.exceptions import PreventUpdate

from components.slide_panel import build_shape_overlay
from components.excel_strip import build_sheet_tabs, build_mini_table
from db.queries import (
    create_project,
    get_citation,
    get_citations_for_project,
    get_citations_for_slide,
    get_excel_sheets,
    get_cells_for_sheet,
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
    get_xlsx_file_by_sha256,
    get_xlsx_file,
    mark_pptx_parsed,
    mark_xlsx_parsed,
)
from parsers.pptx_parser import parse_pptx_file
from parsers.slide_renderer import render_slide_to_html
from parsers.xlsx_parser import parse_workbook

import openpyxl

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
        Output("store-chat-history", "data", allow_duplicate=True),
        Input("upload-xlsx", "contents"),
        State("upload-xlsx", "filename"),
        State("store-chat-history", "data"),
        prevent_initial_call=True,
    )
    def upload_xlsx(contents, filename, chat_history):
        if not contents:
            raise PreventUpdate
        try:
            # We strip data URI prefix to hash
            raw = base64.b64decode(
                contents.split(",", 1)[1] if "," in contents else contents
            )
            sha = hashlib.sha256(raw).hexdigest()

            search_sha = sha

            # Fast-check if this is a previously cleaned file with embedded metadata
            try:
                temp_wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
                prop_id = temp_wb.properties.identifier
                temp_wb.close()
                if prop_id and str(prop_id).startswith("citemind_"):
                    search_sha = str(prop_id).split("citemind_")[1]
            except Exception:
                pass

            # Check if exists (original or embedded hash)
            existing = get_xlsx_file_by_sha256(search_sha)
            # if existing:
            #     fid = existing["id"]
            #     sheets_db = get_excel_sheets(fid)
            #     sheets_raw = {"original": {}, "cleaned": {}}
            #     for s in sheets_db:
            #         sid = s["id"]
            #         cells = get_cells_for_sheet(sid)
            #         cat = "cleaned" if s.get("is_cleaned", 1) else "original"
            #         sheets_raw[cat][s["sheet_name"]] = {
            #             "sheet_index": s["sheet_index"],
            #             "row_count": s["row_count"],
            #             "col_count": s["col_count"],
            #             "header_row": s["header_row"],
            #             "headers": json.loads(s["headers_json"]) if s.get("headers_json") else [],
            #             "cells": cells
            #         }
            #     return (
            #         "file-badge loaded",
            #         [html.Span(className="dot"), f" ✓ {filename}"],
            #         filename,
            #         fid,
            #         sheets_raw,
            #     )

            # Not cached, parse normally
            parsed = parse_workbook(contents, filename)

            fid = insert_xlsx_file(
                original_name=filename,
                storage_path=parsed.get("processed_path", ""),
                sheet_names=parsed["sheet_names"],
                sha256=parsed["sha256"],
            )

            # Insert sheets & cells
            sheets_raw = {"original": {}, "cleaned": {}}
            for cat, sheets_dict, is_clean in [
                ("original", parsed["original_sheets"], False),
                ("cleaned", parsed["cleaned_sheets"], True),
            ]:
                for sname, sdata in sheets_dict.items():
                    sid = insert_excel_sheet(
                        xlsx_file_id=fid,
                        sheet_name=sname,
                        sheet_index=sdata["sheet_index"],
                        row_count=sdata["row_count"],
                        col_count=sdata["col_count"],
                        header_row=sdata["header_row"],
                        headers_json=json.dumps(sdata["headers"]),
                        is_cleaned=is_clean,
                    )
                    if sdata["cells"]:
                        bulk_cells = []
                        for c in sdata["cells"]:
                            c["sheet_id"] = sid
                            bulk_cells.append(c)
                        insert_cells_bulk(bulk_cells)
                    sheets_raw[cat][sname] = sdata

            mark_xlsx_parsed(fid)
            ingestion_report = parsed.get("ingestion_report", {})
            chat_history.append(
                {
                    "role": "system",
                    "content": f"Excel file '{filename}' ingested {json.dumps(ingestion_report,indent=4)}",
                }
            )
            return (
                "file-badge loaded",
                [html.Span(className="dot"), f" ✓ {filename}"],
                filename,
                fid,
                sheets_raw,
                chat_history,
            )
        except Exception as e:
            chat_history.append(
                {
                    "role": "system",
                    "content": f"Error ingesting Excel file '{filename}': {str(e)}",
                }
            )
            log.error("XLSX error: %s", e)
            return (
                "file-badge",
                [html.Span(className="dot"), " XLSX"],
                None,
                None,
                {},
                chat_history,
            )

    # ─────────────────────────────────────────────────────────
    # Download Cleaned Excel
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("download-processed-xlsx", "data"),
        Input("download-processed-btn", "n_clicks"),
        State("store-xlsx-file-id", "data"),
        prevent_initial_call=True,
    )
    def download_cleaned_xlsx(n_clicks, fid):
        if not n_clicks or not fid:
            raise PreventUpdate

        file_info = get_xlsx_file(fid)
        if not file_info or not file_info.get("storage_path"):
            log.warning("No storage path found for file %s", fid)
            raise PreventUpdate

        storage_path = file_info["storage_path"]
        if not os.path.exists(storage_path):
            log.warning("Storage path does not exist: %s", storage_path)
            raise PreventUpdate

        return dcc.send_file(storage_path)

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
        citations = get_citations_for_slide(project_id, slide_id)

        # # Build overlays
        overlays = []
        for s in shapes:
            overlay = build_shape_overlay(s)

            # Apply citation status colors
            shape_cits = [c for c in citations if c["shape_id"] == s["id"]]
            if shape_cits:
                status_set = {c["status"] for c in shape_cits}
                if "pending" in status_set:
                    overlay.className += " has-pending"
                elif "rejected" in status_set:
                    overlay.className += " has-rejected"
                else:
                    overlay.className += " has-confirmed"

            overlays.append(overlay)

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

    # ─────────────────────────────────────────────────────────
    # 5. Excel Strip Callbacks
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("sheet-tabs", "children"),
        Output("excel-strip-table", "children"),
        Output("store-selected-sheet", "data"),
        Input("store-sheets-raw", "data"),
        Input({"type": "sheet-tab-btn", "sheet": ALL}, "n_clicks"),
        Input("data-view-toggle", "value"),
        State("store-selected-sheet", "data"),
        prevent_initial_call=True,
    )
    def update_excel_strip(sheets_data, tab_clicks, view_mode, current_sheet):
        if not sheets_data:
            raise PreventUpdate

        view_mode = view_mode or "cleaned"
        target_view_data = sheets_data.get(view_mode, sheets_data.get("cleaned", {}))

        if not target_view_data:
            return [], html.Div("No Excel data loaded.", className="empty-state"), None

        ctx = callback_context
        # Default target sheet
        target_sheet = current_sheet
        if not target_sheet or target_sheet not in target_view_data:
            target_sheet = (
                list(target_view_data.keys())[0] if target_view_data else None
            )

        if ctx.triggered:
            trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
            if "sheet-tab-btn" in trigger_id:
                try:
                    trigger_dict = json.loads(trigger_id)
                    target_sheet = trigger_dict.get("sheet", target_sheet)
                except Exception:
                    pass

        if not target_sheet:
            return [], html.Div("No Excel data loaded.", className="empty-state"), None

        sheet_names = list(target_view_data.keys())
        tabs = build_sheet_tabs(sheet_names, active=target_sheet)

        sdata = target_view_data[target_sheet]
        headers = sdata.get("headers", [])
        col_count = len(headers) or sdata.get("col_count", 0)

        # Build rows from cells
        cells = sdata.get("cells", [])
        rows_map = {}
        for c in cells:
            ri = c["row_index"]
            # Skip header row if it exists
            if ri == 0 and sdata.get("header_row") == 1:
                continue
            if ri not in rows_map:
                rows_map[ri] = [""] * col_count
            ci = c["col_index"]
            if 0 <= ci < col_count:
                rows_map[ri][ci] = c.get("display_value", "")

        rows = []
        for ri in sorted(rows_map.keys()):
            rows.append(rows_map[ri])

        table_component = build_mini_table(headers, rows)

        return tabs, table_component, target_sheet

    # ─────────────────────────────────────────────────────────
    # 6. UI Toggle Callbacks
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("slide-viewer-wrapper", "className"),
        Input("toggle-slide-viewer-btn", "n_clicks"),
        State("slide-viewer-wrapper", "className"),
        prevent_initial_call=True,
    )
    def toggle_slide_viewer(n_clicks, current_class):
        if not current_class:
            current_class = "slide-viewer"
        if "collapsed" in current_class:
            return current_class.replace(" collapsed", "")
        else:
            return current_class + " collapsed"

    @app.callback(
        Output("excel-strip-root", "className"),
        Input("toggle-excel-strip-btn", "n_clicks"),
        State("excel-strip-root", "className"),
        prevent_initial_call=True,
    )
    def toggle_excel_strip(n_clicks, current_class):
        if not current_class:
            current_class = "excel-strip"
        if "collapsed-strip" in current_class:
            return current_class.replace(" collapsed-strip", "")
        else:
            return current_class + " collapsed-strip"
