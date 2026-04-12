# Parsing Engine (`parsers/`)

This directory contains handlers designed to extract robust schema models safely out of heavy external Microsoft standard files without requiring a native suite backend like LibreOffice or COM.

## Modules
- **`pptx_parser.py`**: Iterates efficiently through underlying `<p:sld>` structures mapping EMU coordinate scaling bounding boxes directly out of `python-pptx` properties. Handles unpacking shape texts and nesting layers robustly to SQL schemas. 
- **`slide_renderer.py`**: Translates internal presentations models into a self-contained web viewport DOM representing slides natively mirroring standard aesthetic boundaries (fonts, sizes, overlays).
- **`xlsx_parser.py`**: Consumes spreadsheet grids translating coordinate addresses (ie A1, B32) alongside row/col context directly into normalized cell vectors resolving header dependencies natively via heuristics.
