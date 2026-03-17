"""
CiteMind — Named SQL query functions for all CRUD operations.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from db.connection import get_db


def _now() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid4())


# ── Projects ──────────────────────────────────────────────


def create_project(
    name: str,
    pptx_file_id: str,
    xlsx_file_id: str,
    meta: Optional[dict] = None,
) -> str:
    """Create a new project. Returns project_id."""
    pid = _uuid()
    now = _now()
    with get_db() as db:
        db.execute(
            """INSERT INTO projects
               (id, name, created_at, updated_at, pptx_file_id, xlsx_file_id, status, meta)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
            (pid, name, now, now, pptx_file_id, xlsx_file_id,
             json.dumps(meta) if meta else None),
        )
    return pid


def get_project(project_id: str) -> Optional[dict]:
    with get_db() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None


# ── PPTX Files ────────────────────────────────────────────


def insert_pptx_file(
    original_name: str,
    storage_path: str,
    slide_count: int,
    slide_width_emu: int,
    slide_height_emu: int,
    sha256: str,
) -> str:
    fid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO pptx_files
               (id, original_name, storage_path, slide_count,
                slide_width_emu, slide_height_emu, sha256, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, original_name, storage_path, slide_count,
             slide_width_emu, slide_height_emu, sha256, _now()),
        )
    return fid


def mark_pptx_parsed(file_id: str) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE pptx_files SET parsed_at=? WHERE id=?",
            (_now(), file_id),
        )


# ── XLSX Files ────────────────────────────────────────────


def insert_xlsx_file(
    original_name: str,
    storage_path: str,
    sheet_names: List[str],
    sha256: str,
) -> str:
    fid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO xlsx_files
               (id, original_name, storage_path, sheet_names, sha256, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (fid, original_name, storage_path, json.dumps(sheet_names), sha256, _now()),
        )
    return fid


def mark_xlsx_parsed(file_id: str) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE xlsx_files SET parsed_at=? WHERE id=?",
            (_now(), file_id),
        )


# ── Slides ────────────────────────────────────────────────


def insert_slide(
    pptx_file_id: str,
    slide_index: int,
    slide_number: int,
    title: Optional[str] = None,
    png_path: Optional[str] = None,
    shape_count: int = 0,
    has_table: bool = False,
    has_chart: bool = False,
) -> str:
    sid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO slides
               (id, pptx_file_id, slide_index, slide_number, title,
                png_path, shape_count, has_table, has_chart)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, pptx_file_id, slide_index, slide_number, title,
             png_path, shape_count, int(has_table), int(has_chart)),
        )
    return sid


def get_slides_for_pptx(pptx_file_id: str) -> List[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM slides WHERE pptx_file_id=? ORDER BY slide_index",
            (pptx_file_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_slide(slide_id: str) -> Optional[dict]:
    with get_db() as db:
        row = db.execute("SELECT * FROM slides WHERE id=?", (slide_id,)).fetchone()
        return dict(row) if row else None


# ── Shapes ────────────────────────────────────────────────


def insert_shape(
    slide_id: str,
    pptx_shape_id: int,
    shape_name: str,
    shape_type: str,
    x_pct: float,
    y_pct: float,
    w_pct: float,
    h_pct: float,
    full_text: Optional[str] = None,
    runs_json: Optional[str] = None,
    z_order: int = 0,
) -> str:
    shid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO shapes
               (id, slide_id, pptx_shape_id, shape_name, shape_type,
                x_pct, y_pct, w_pct, h_pct, full_text, runs_json, z_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (shid, slide_id, pptx_shape_id, shape_name, shape_type,
             x_pct, y_pct, w_pct, h_pct, full_text, runs_json, z_order),
        )
    return shid


def insert_shapes_bulk(shapes: List[dict]) -> List[str]:
    """Insert multiple shapes at once. Each dict must have all shape fields."""
    ids = []
    with get_db() as db:
        for s in shapes:
            shid = _uuid()
            ids.append(shid)
            db.execute(
                """INSERT INTO shapes
                   (id, slide_id, pptx_shape_id, shape_name, shape_type,
                    x_pct, y_pct, w_pct, h_pct, full_text, runs_json, z_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (shid, s["slide_id"], s["pptx_shape_id"], s["shape_name"],
                 s["shape_type"], s["x_pct"], s["y_pct"], s["w_pct"], s["h_pct"],
                 s.get("full_text"), s.get("runs_json"), s.get("z_order", 0)),
            )
    return ids


def get_shapes_for_slide(slide_id: str) -> List[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM shapes WHERE slide_id=? ORDER BY z_order",
            (slide_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_shape(shape_id: str) -> Optional[dict]:
    with get_db() as db:
        row = db.execute("SELECT * FROM shapes WHERE id=?", (shape_id,)).fetchone()
        return dict(row) if row else None


# ── Excel Sheets ──────────────────────────────────────────


def insert_excel_sheet(
    xlsx_file_id: str,
    sheet_name: str,
    sheet_index: int,
    row_count: int = 0,
    col_count: int = 0,
    header_row: Optional[int] = None,
    headers_json: Optional[str] = None,
) -> str:
    sid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO excel_sheets
               (id, xlsx_file_id, sheet_name, sheet_index,
                row_count, col_count, header_row, headers_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (sid, xlsx_file_id, sheet_name, sheet_index,
             row_count, col_count, header_row, headers_json),
        )
    return sid


def get_excel_sheets(xlsx_file_id: str) -> List[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM excel_sheets WHERE xlsx_file_id=? ORDER BY sheet_index",
            (xlsx_file_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Excel Cells ───────────────────────────────────────────


def insert_cells_bulk(cells: List[dict]) -> None:
    """Insert multiple cells at once. Each dict must have all cell fields."""
    with get_db() as db:
        for c in cells:
            cid = c.get("id") or _uuid()
            db.execute(
                """INSERT OR IGNORE INTO excel_cells
                   (id, sheet_id, cell_address, row_index, col_index,
                    raw_value, numeric_value, data_type, display_value,
                    row_context, is_header)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cid, c["sheet_id"], c["cell_address"], c["row_index"],
                 c["col_index"], c.get("raw_value"), c.get("numeric_value"),
                 c["data_type"], c.get("display_value"), c.get("row_context"),
                 int(c.get("is_header", False))),
            )


def search_cells_by_value(
    xlsx_file_id: str,
    value: str,
    fuzzy: bool = True,
) -> List[dict]:
    """Search excel_cells for cells matching a value. Returns enriched results."""
    with get_db() as db:
        # Try exact display_value match
        results = []  # type: List[dict]

        # Exact display match
        rows = db.execute(
            """SELECT c.*, s.sheet_name
               FROM excel_cells c
               JOIN excel_sheets s ON c.sheet_id = s.id
               WHERE s.xlsx_file_id = ? AND c.display_value = ?""",
            (xlsx_file_id, value),
        ).fetchall()
        for r in rows:
            d = dict(r)
            d["match_score"] = 1.0
            results.append(d)

        # Exact numeric match
        try:
            import re
            cleaned = re.sub(r'[₹$,% ]', '', value)
            numeric = float(cleaned)
            rows = db.execute(
                """SELECT c.*, s.sheet_name
                   FROM excel_cells c
                   JOIN excel_sheets s ON c.sheet_id = s.id
                   WHERE s.xlsx_file_id = ? AND c.numeric_value = ?
                   AND c.id NOT IN (SELECT id FROM excel_cells WHERE display_value = ?)""",
                (xlsx_file_id, numeric, value),
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["match_score"] = 0.9
                results.append(d)

            # Fuzzy numeric (within 1%)
            if fuzzy:
                margin = abs(numeric * 0.01) or 0.01
                rows = db.execute(
                    """SELECT c.*, s.sheet_name
                       FROM excel_cells c
                       JOIN excel_sheets s ON c.sheet_id = s.id
                       WHERE s.xlsx_file_id = ?
                       AND c.numeric_value BETWEEN ? AND ?
                       AND c.numeric_value != ?
                       AND c.id NOT IN (SELECT id FROM excel_cells WHERE display_value = ?)""",
                    (xlsx_file_id, numeric - margin, numeric + margin, numeric, value),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    d["match_score"] = 0.7
                    results.append(d)
        except (ValueError, TypeError):
            pass

        # Substring match
        if fuzzy and value.strip():
            rows = db.execute(
                """SELECT c.*, s.sheet_name
                   FROM excel_cells c
                   JOIN excel_sheets s ON c.sheet_id = s.id
                   WHERE s.xlsx_file_id = ?
                   AND c.raw_value LIKE ?
                   AND c.id NOT IN ({})""".format(
                    ",".join(["?"] * len(results)) if results else "''"
                ),
                [xlsx_file_id, "%" + value + "%"] +
                [r["id"] for r in results],
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["match_score"] = 0.4
                results.append(d)

        # Sort by score descending
        results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        return results


def get_cells_for_sheet(sheet_id: str) -> List[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM excel_cells WHERE sheet_id=? ORDER BY row_index, col_index",
            (sheet_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Citations ─────────────────────────────────────────────


def insert_citation(
    project_id: str,
    shape_id: str,
    text_snippet: str,
    match_method: str,
    run_indices: Optional[List[int]] = None,
    char_start: Optional[int] = None,
    char_end: Optional[int] = None,
    cell_id: Optional[str] = None,
    cell_ids_json: Optional[str] = None,
    is_calculated: bool = False,
    formula: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    ai_reasoning: Optional[str] = None,
    status: str = "pending",
) -> str:
    cid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO citations
               (id, project_id, shape_id, run_indices, text_snippet,
                char_start, char_end, cell_id, cell_ids_json,
                is_calculated, formula, ai_confidence, ai_reasoning,
                match_method, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, project_id, shape_id,
             json.dumps(run_indices) if run_indices else None,
             text_snippet, char_start, char_end, cell_id, cell_ids_json,
             int(is_calculated), formula, ai_confidence, ai_reasoning,
             match_method, status, _now()),
        )
    return cid


def get_citations_for_project(
    project_id: str,
    status: Optional[str] = None,
) -> List[dict]:
    with get_db() as db:
        if status:
            rows = db.execute(
                "SELECT * FROM citations WHERE project_id=? AND status=? ORDER BY created_at DESC",
                (project_id, status),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM citations WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_citations_for_slide(project_id: str, slide_id: str) -> List[dict]:
    """Get citations for shapes on a specific slide, enriched with cell data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT c.*, s.shape_name, s.full_text as shape_text,
                      ec.cell_address, ec.display_value as cell_display,
                      ec.row_context, es.sheet_name
               FROM citations c
               JOIN shapes s ON c.shape_id = s.id
               LEFT JOIN excel_cells ec ON c.cell_id = ec.id
               LEFT JOIN excel_sheets es ON ec.sheet_id = es.id
               WHERE c.project_id = ? AND s.slide_id = ?
               ORDER BY c.created_at DESC""",
            (project_id, slide_id),
        ).fetchall()
        return [dict(r) for r in rows]


def update_citation_status(
    citation_id: str,
    new_status: str,
    actor: str = "human",
    note: Optional[str] = None,
) -> None:
    with get_db() as db:
        # Get current status
        row = db.execute(
            "SELECT status FROM citations WHERE id=?", (citation_id,)
        ).fetchone()
        if not row:
            return
        old_status = row["status"]

        # Update citation
        db.execute(
            """UPDATE citations
               SET status=?, reviewed_by=?, reviewed_at=?, human_note=?
               WHERE id=?""",
            (new_status, actor, _now(), note, citation_id),
        )

        # Insert history
        db.execute(
            """INSERT INTO citation_history
               (citation_id, from_status, to_status, actor, note, changed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (citation_id, old_status, new_status, actor, note, _now()),
        )


def get_citation(citation_id: str) -> Optional[dict]:
    with get_db() as db:
        row = db.execute("SELECT * FROM citations WHERE id=?", (citation_id,)).fetchone()
        return dict(row) if row else None


# ── Sessions ──────────────────────────────────────────────


def create_session(project_id: str) -> str:
    sid = _uuid()
    now = _now()
    with get_db() as db:
        db.execute(
            """INSERT INTO sessions
               (id, project_id, current_slide, started_at, last_active_at)
               VALUES (?, ?, 0, ?, ?)""",
            (sid, project_id, now, now),
        )
    return sid


def update_session_slide(session_id: str, slide_index: int) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE sessions SET current_slide=?, last_active_at=? WHERE id=?",
            (slide_index, _now(), session_id),
        )


# ── Chat ──────────────────────────────────────────────────


def create_chat_thread(
    session_id: str,
    project_id: str,
    title: Optional[str] = None,
) -> str:
    tid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO chat_threads
               (id, session_id, project_id, title, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (tid, session_id, project_id, title, _now()),
        )
    return tid


def save_chat_message(
    thread_id: str,
    role: str,
    content: str,
    selection_event_id: Optional[str] = None,
    citation_ids: Optional[List[str]] = None,
    tool_calls: Optional[str] = None,
    model: Optional[str] = None,
    tokens_used: Optional[int] = None,
) -> str:
    mid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO chat_messages
               (id, thread_id, role, content, selection_event_id,
                citation_ids, tool_calls, model, tokens_used, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mid, thread_id, role, content, selection_event_id,
             json.dumps(citation_ids) if citation_ids else None,
             tool_calls, model, tokens_used, _now()),
        )
    return mid


def get_chat_messages(thread_id: str) -> List[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM chat_messages WHERE thread_id=? ORDER BY created_at",
            (thread_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Selection Events ──────────────────────────────────────


def insert_selection_event(
    project_id: str,
    session_id: str,
    selection_type: str,
    slide_id: Optional[str] = None,
    shape_id: Optional[str] = None,
    run_indices: Optional[List[int]] = None,
    selected_text: Optional[str] = None,
    bbox_json: Optional[str] = None,
    resolved_shape_ids: Optional[List[str]] = None,
) -> str:
    eid = _uuid()
    with get_db() as db:
        db.execute(
            """INSERT INTO selection_events
               (id, project_id, session_id, selection_type, slide_id,
                shape_id, run_indices, selected_text, bbox_json,
                resolved_shape_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, project_id, session_id, selection_type, slide_id,
             shape_id,
             json.dumps(run_indices) if run_indices else None,
             selected_text, bbox_json,
             json.dumps(resolved_shape_ids) if resolved_shape_ids else None,
             _now()),
        )
    return eid


# ── Stats ─────────────────────────────────────────────────


def get_project_stats(project_id: str) -> dict:
    """Get citation counts by status for a project."""
    with get_db() as db:
        rows = db.execute(
            """SELECT status, COUNT(*) as cnt
               FROM citations WHERE project_id=?
               GROUP BY status""",
            (project_id,),
        ).fetchall()
        stats = {"confirmed": 0, "pending": 0, "rejected": 0, "needs_review": 0, "total": 0}
        for r in rows:
            stats[r["status"]] = r["cnt"]
            stats["total"] += r["cnt"]
        return stats
