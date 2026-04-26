"""
Checkmate — Selection callbacks.
3 Modes: Shape Click, Text Selection, Canvas Drag.
"""
from __future__ import annotations

import json
import logging

from dash import Input, Output, State, callback_context, dcc, no_update
from dash.exceptions import PreventUpdate

from db.queries import get_shape, insert_selection_event

log = logging.getLogger(__name__)


def register_selection_callbacks(app):

    # ─────────────────────────────────────────────────────────
    # Mode 1: Shape Click (Server)
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-selection", "data", allow_duplicate=True),
        Input({"type": "shape-overlay", "shape_id": "ALL"}, "n_clicks"),
        State({"type": "shape-overlay", "shape_id": "ALL"}, "id"),
        prevent_initial_call=True,
    )
    def on_shape_click(n_clicks_list, ids):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger = ctx.triggered[0]
        # Ignore initial zeros
        if trigger["value"] == 0:
            raise PreventUpdate

        shape_id = json.loads(trigger["prop_id"].split(".")[0])["shape_id"]
        shape = get_shape(shape_id)
        if not shape:
            raise PreventUpdate

        return {
            "type": "shape_click",
            "shape_id": shape_id,
            "text": shape.get("full_text", ""),
            "run_indices": [],
            "bbox": None,
        }

    # ─────────────────────────────────────────────────────────
    # Mode 2 & 3: Clientside (Browser) Events Hooks
    # ─────────────────────────────────────────────────────────
    # Text selection inside a shape
    app.clientside_callback(
        """
        function(slideContainerId) {
            if (!document.getElementById('slide-container')) return window.dash_clientside.no_update;

            document.addEventListener('mouseup', function(e) {
                // Ignore clicks on Canvas or UI elements outside slide
                if (e.target.id === 'selection-canvas') return;
                
                const sel = window.getSelection();
                if (!sel || sel.isCollapsed) return;
                
                const range = sel.getRangeAt(0);
                const shapeDiv = range.commonAncestorContainer.parentElement ? 
                                 range.commonAncestorContainer.parentElement.closest('.shape-overlay') : null;
                
                if (!shapeDiv) return;

                const runSpans = shapeDiv.querySelectorAll('[data-run]');
                const hitRuns = [...runSpans]
                    .filter(s => range.intersectsNode(s))
                    .map(s => parseInt(s.dataset.run));

                const storeEl = document.getElementById('store-selection');
                if (storeEl) {
                    window.dash_clientside_store_update = {
                        type: 'text_selection',
                        shape_id: shapeDiv.dataset.shapeId,
                        text: sel.toString().trim(),
                        run_indices: hitRuns,
                        bbox: null
                    };
                    document.dispatchEvent(new CustomEvent('checkmate:selection'));
                }
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output("store-selection", "data"),
        Input("slide-container", "id"),
    )

    # Canvas Drag (Freehand bbox)
    app.clientside_callback(
        """
        function(canvasId) {
            const canvas = document.getElementById('selection-canvas');
            if (!canvas) return window.dash_clientside.no_update;

            let start = null;
            let isDrawing = false;
            let ctx = canvas.getContext('2d');

            function resize() {
                canvas.width = canvas.offsetWidth;
                canvas.height = canvas.offsetHeight;
            }
            window.addEventListener('resize', resize);
            resize();

            // Toggle canvas pointer events via alt/shift key or a UI button.
            // For now, we assume the canvas is always active if nothing else intercepts.
            // The canvas is zIndex:5, shapes are zIndex:10.

            canvas.addEventListener('mousedown', e => {
                const r = canvas.getBoundingClientRect();
                start = { x: (e.clientX-r.left)/r.width, y: (e.clientY-r.top)/r.height, 
                          px: e.clientX-r.left, py: e.clientY-r.top };
                isDrawing = true;
            });

            canvas.addEventListener('mousemove', e => {
                if (!isDrawing) return;
                const r = canvas.getBoundingClientRect();
                const cur = { px: e.clientX-r.left, py: e.clientY-r.top };
                
                ctx.clearRect(0,0, canvas.width, canvas.height);
                ctx.fillStyle = 'rgba(124, 106, 247, 0.2)';
                ctx.strokeStyle = 'rgba(124, 106, 247, 0.8)';
                ctx.lineWidth = 2;
                ctx.fillRect(start.px, start.py, cur.px - start.px, cur.py - start.py);
                ctx.strokeRect(start.px, start.py, cur.px - start.px, cur.py - start.py);
            });

            canvas.addEventListener('mouseup', e => {
                if (!isDrawing || !start) return window.dash_clientside.no_update;
                isDrawing = false;
                ctx.clearRect(0,0, canvas.width, canvas.height); // clear selection rect

                const r = canvas.getBoundingClientRect();
                const end = { x: (e.clientX-r.left)/r.width, y: (e.clientY-r.top)/r.height };
                
                const bbox = { 
                    x1: Math.min(start.x, end.x), 
                    y1: Math.min(start.y, end.y),
                    x2: Math.max(start.x, end.x), 
                    y2: Math.max(start.y, end.y) 
                };

                start = null;
                
                // Only trigger if area is reasonably large (>1%)
                if ((bbox.x2 - bbox.x1) * (bbox.y2 - bbox.y1) > 0.001) {
                    const storeEl = document.getElementById('store-drag');
                    if (storeEl) {
                        window.dash_clientside_drag_update = { bbox: bbox };
                        document.dispatchEvent(new CustomEvent('checkmate:drag'));
                    }
                }
            });

            return window.dash_clientside.no_update;
        }
        """,
        Output("store-drag", "data"),
        Input("selection-canvas", "id"),
    )

    # ─────────────────────────────────────────────────────────
    # Server Hit-test for Canvas Drag
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("store-selection", "data", allow_duplicate=True),
        Input("store-drag", "data"),
        State("store-slide-shapes", "data"),
        prevent_initial_call=True,
    )
    def on_canvas_drag(drag_data, shapes):
        if not drag_data or not drag_data.get("bbox") or not shapes:
            raise PreventUpdate

        bbox = drag_data["bbox"]
        hits = []

        # Hit test logic: shape intersects drag rectangle
        for s in shapes:
            if (s["x_pct"] < bbox["x2"] and s["x_pct"] + s["w_pct"] > bbox["x1"] and
                s["y_pct"] < bbox["y2"] and s["y_pct"] + s["h_pct"] > bbox["y1"]):
                hits.append(s)

        if not hits:
            raise PreventUpdate

        # Take the most prominent hit or pass all downstream for disambiguation
        primary = hits[-1]  # Highest z-order

        return {
            "type": "canvas_drag",
            "shape_id": primary["id"],
            "text": primary.get("full_text", ""),
            "run_indices": [],
            "bbox": bbox,
            "all_hits": [h["id"] for h in hits],
        }

    # ─────────────────────────────────────────────────────────
    # Log Event & Provide Context Pillar
    # ─────────────────────────────────────────────────────────
    @app.callback(
        Output("chat-input", "value", allow_duplicate=True),
        Input("store-selection", "data"),
        State("store-project-id", "data"),
        State("store-current-slide-idx", "data"),
        State("store-slide-ids", "data"),
        prevent_initial_call=True,
    )
    def handle_selection_event(sel_data, project_id, current_idx, slide_ids):
        if not sel_data or not project_id or not slide_ids:
            raise PreventUpdate

        slide_id = slide_ids[current_idx]

        # Log to DB
        insert_selection_event(
            project_id=project_id,
            session_id="",  # we skip session management for now
            selection_type=sel_data["type"],
            slide_id=slide_id,
            shape_id=sel_data.get("shape_id"),
            run_indices=sel_data.get("run_indices"),
            selected_text=sel_data.get("text"),
            bbox_json=json.dumps(sel_data.get("bbox")),
            resolved_shape_ids=sel_data.get("all_hits"),
        )

        # Prefill chat input
        prompt = ""
        if sel_data["type"] == "text_selection" and sel_data.get("text"):
            prompt = f'Find citations for "{sel_data["text"]}"'
        elif sel_data["type"] in ("shape_click", "canvas_drag"):
            prompt = "Scan selected shape for citations"

        return prompt
