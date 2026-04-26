# Checkmate

A dark-mode Plotly Dash app for linking PowerPoint slide values to their Excel source data — no LibreOffice required.

---

## What it does

Upload a `.pptx` and an `.xlsx`. Checkmate renders each slide in the browser using pure HTML/CSS (via **python-pptx**), overlays clickable shape regions on top, and lets you map individual numeric runs on the slide to cells in the spreadsheet. An AI agent (Claude via LangGraph) can auto-suggest citations and let you confirm, reject, or edit them in the citation panel.

---

## Architecture

> **Note**: Every subdirectory within `checkmate/` contains its own dedicated `readme.md` elaborating deeply on its contents. Check `/agent/readme.md` for a comprehensive breakdown of the LangGraph AI loop!

```
checkmate/
├── app.py                  # Dash app + layout entry point
├── layout.py               # Full layout builder
│
├── parsers/
│   ├── pptx_parser.py      # Extracts shapes, runs, coordinates from PPTX
│   ├── slide_renderer.py   # Renders a slide to HTML/CSS (no LibreOffice)
│   └── xlsx_parser.py      # Parses workbook cells and headers
│
├── components/
│   ├── slide_panel.py      # Left panel: slide iframe + nav
│   ├── citation_panel.py   # Middle panel: citation cards
│   ├── chat_panel.py       # Right panel: AI chat
│   └── excel_strip.py      # Bottom strip: mini spreadsheet view
│
├── callbacks/
│   ├── slide_callbacks.py      # Upload, navigation, slide rendering
│   ├── citation_callbacks.py   # Confirm / reject / edit citations
│   ├── chat_callbacks.py       # AI chat interaction
│   └── selection_callbacks.py  # Drag-select + shape click logic
│
├── agent/
│   ├── graph.py            # LangGraph citation agent graph
│   ├── nodes.py            # Agent node implementations
│   └── prompts.py          # Prompt templates
│
├── db/
│   ├── connection.py       # SQLite connection helper
│   ├── queries.py          # All DB read/write operations
│   └── schema.sql          # Table definitions
│
└── assets/
    └── style.css           # Full dark-mode theme
```

---

## Slide rendering

Slides are rendered entirely in the browser — **no LibreOffice, no Ghostscript, no image conversion**:

1. `pptx_parser.py` walks every shape in the slide and stores EMU coordinates, text runs, font attributes, and fill data in SQLite.
2. `slide_renderer.py` re-opens the raw PPTX bytes with python-pptx and emits a self-contained HTML string where each shape is an absolutely-positioned `<div>` (percentages of the slide canvas).
3. The HTML is injected into an `<iframe srcDoc="...">` in the slide panel, isolating slide CSS from the app theme.
4. Transparent `.shape-overlay` divs sit on top at the same percentage coordinates for click and drag-select interaction.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py          # opens at http://localhost:8080
```

**Requirements:** Python 3.10+. No system dependencies (LibreOffice not needed).

---

## Dependencies

| Package | Purpose |
|---|---|
| `dash >= 2.17` | UI framework |
| `python-pptx >= 0.6.23` | PPTX parsing + slide rendering |
| `openpyxl >= 3.1` | Excel parsing |
| `pandas >= 2.2` | DataFrame operations |
| `anthropic >= 0.28` | Claude API client |
| `langgraph >= 0.2` | Citation agent orchestration |
| `langchain-anthropic` | LangChain ↔ Anthropic adapter |

---

## Database

SQLite (`checkmate.db`) with the following main tables:

- **`pptx_files`** / **`slides`** / **`shapes`** — parsed presentation data
- **`xlsx_files`** / **`excel_sheets`** / **`excel_cells`** — parsed spreadsheet data
- **`projects`** — ties a PPTX + XLSX pair together
- **`citations`** — shape-to-cell links with status (`pending` / `confirmed` / `rejected`)
