-- CiteMind Database Schema
-- All tables use TEXT primary keys (uuid4) except citation_history (INTEGER rowid).

-- pptx_files
CREATE TABLE IF NOT EXISTS pptx_files (
    id               TEXT PRIMARY KEY,
    original_name    TEXT NOT NULL,
    storage_path     TEXT NOT NULL,
    slide_count      INTEGER NOT NULL,
    slide_width_emu  INTEGER NOT NULL,
    slide_height_emu INTEGER NOT NULL,
    sha256           TEXT NOT NULL,
    uploaded_at      TEXT NOT NULL,
    parsed_at        TEXT
);

-- xlsx_files
CREATE TABLE IF NOT EXISTS xlsx_files (
    id            TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    storage_path  TEXT NOT NULL,
    sheet_names   TEXT NOT NULL,  -- JSON array
    sha256        TEXT NOT NULL,
    uploaded_at   TEXT NOT NULL,
    parsed_at     TEXT
);

-- projects: one workspace = one pptx + one xlsx
CREATE TABLE IF NOT EXISTS projects (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    pptx_file_id TEXT NOT NULL REFERENCES pptx_files(id),
    xlsx_file_id TEXT NOT NULL REFERENCES xlsx_files(id),
    status       TEXT NOT NULL DEFAULT 'active',
    meta         TEXT  -- JSON
);

-- slides
CREATE TABLE IF NOT EXISTS slides (
    id             TEXT PRIMARY KEY,
    pptx_file_id   TEXT NOT NULL REFERENCES pptx_files(id),
    slide_index    INTEGER NOT NULL,
    slide_number   INTEGER NOT NULL,
    title          TEXT,
    png_path       TEXT,
    shape_count    INTEGER NOT NULL DEFAULT 0,
    has_table      INTEGER NOT NULL DEFAULT 0,
    has_chart      INTEGER NOT NULL DEFAULT 0,
    citation_count INTEGER NOT NULL DEFAULT 0,
    uncited_count  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(pptx_file_id, slide_index)
);
CREATE INDEX IF NOT EXISTS idx_slides_pptx ON slides(pptx_file_id, slide_index);

-- shapes: every shape on every slide
CREATE TABLE IF NOT EXISTS shapes (
    id            TEXT PRIMARY KEY,
    slide_id      TEXT NOT NULL REFERENCES slides(id),
    pptx_shape_id INTEGER NOT NULL,
    shape_name    TEXT NOT NULL,
    shape_type    TEXT NOT NULL,
    x_pct         REAL NOT NULL,
    y_pct         REAL NOT NULL,
    w_pct         REAL NOT NULL,
    h_pct         REAL NOT NULL,
    full_text     TEXT,
    runs_json     TEXT,   -- JSON array of {index, text, bold, size, color, is_numeric}
    z_order       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_shapes_slide ON shapes(slide_id);

-- excel_sheets
CREATE TABLE IF NOT EXISTS excel_sheets (
    id           TEXT PRIMARY KEY,
    xlsx_file_id TEXT NOT NULL REFERENCES xlsx_files(id),
    sheet_name   TEXT NOT NULL,
    sheet_index  INTEGER NOT NULL,
    row_count    INTEGER NOT NULL DEFAULT 0,
    col_count    INTEGER NOT NULL DEFAULT 0,
    header_row   INTEGER,
    headers_json TEXT  -- JSON array
);

-- excel_cells: atomic unit of Excel data
CREATE TABLE IF NOT EXISTS excel_cells (
    id            TEXT PRIMARY KEY,
    sheet_id      TEXT NOT NULL REFERENCES excel_sheets(id),
    cell_address  TEXT NOT NULL,
    row_index     INTEGER NOT NULL,
    col_index     INTEGER NOT NULL,
    raw_value     TEXT,
    numeric_value REAL,
    data_type     TEXT NOT NULL,
    display_value TEXT,
    row_context   TEXT,  -- JSON: {header: value} for this row
    is_header     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(sheet_id, cell_address)
);
CREATE INDEX IF NOT EXISTS idx_cells_sheet   ON excel_cells(sheet_id);
CREATE INDEX IF NOT EXISTS idx_cells_numeric ON excel_cells(sheet_id, numeric_value);

-- citations: the core junction table
CREATE TABLE IF NOT EXISTS citations (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL REFERENCES projects(id),
    shape_id         TEXT NOT NULL REFERENCES shapes(id),
    run_indices      TEXT,   -- JSON int array e.g. [1] or [1,2]
    text_snippet     TEXT NOT NULL,
    char_start       INTEGER,
    char_end         INTEGER,
    cell_id          TEXT REFERENCES excel_cells(id),
    cell_ids_json    TEXT,   -- JSON array for calculated/multi-cell
    is_calculated    INTEGER NOT NULL DEFAULT 0,
    formula          TEXT,
    ai_confidence    REAL,
    ai_reasoning     TEXT,
    match_method     TEXT NOT NULL,  -- exact_value|fuzzy_value|semantic|manual|calculated
    status           TEXT NOT NULL DEFAULT 'pending',
    reviewed_by      TEXT,
    human_note       TEXT,
    reviewed_at      TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_project_status ON citations(project_id, status);
CREATE INDEX IF NOT EXISTS idx_citations_shape          ON citations(shape_id);
CREATE INDEX IF NOT EXISTS idx_citations_cell           ON citations(cell_id);

-- citation_history: full audit trail
CREATE TABLE IF NOT EXISTS citation_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    citation_id TEXT NOT NULL REFERENCES citations(id),
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    actor       TEXT NOT NULL,  -- human|ai_agent|import
    note        TEXT,
    changed_at  TEXT NOT NULL
);

-- sessions
CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    current_slide  INTEGER NOT NULL DEFAULT 0,
    started_at     TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

-- chat_threads
CREATE TABLE IF NOT EXISTS chat_threads (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    title      TEXT,
    created_at TEXT NOT NULL
);

-- chat_messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id                 TEXT PRIMARY KEY,
    thread_id          TEXT NOT NULL REFERENCES chat_threads(id),
    role               TEXT NOT NULL,  -- user|assistant|system
    content            TEXT NOT NULL,
    selection_event_id TEXT,
    citation_ids       TEXT,   -- JSON array
    tool_calls         TEXT,   -- JSON LangGraph tool invocations
    model              TEXT,
    tokens_used        INTEGER,
    created_at         TEXT NOT NULL
);

-- selection_events: JS → Python bridge log
CREATE TABLE IF NOT EXISTS selection_events (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id),
    session_id          TEXT NOT NULL REFERENCES sessions(id),
    selection_type      TEXT NOT NULL,  -- shape_click|text_selection|canvas_drag|run_click
    slide_id            TEXT REFERENCES slides(id),
    shape_id            TEXT REFERENCES shapes(id),
    run_indices         TEXT,   -- JSON
    selected_text       TEXT,
    bbox_json           TEXT,   -- JSON {x1,y1,x2,y2} fractions for canvas drag
    resolved_shape_ids  TEXT,   -- JSON array after hit-test
    created_at          TEXT NOT NULL
);
