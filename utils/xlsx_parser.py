"""
XLSX Parser — extracts all sheets into structured dicts.
"""

import base64
import io
from openpyxl import load_workbook
import pandas as pd


def parse_xlsx(contents_b64: str) -> dict:
    """
    Decode a base64-encoded XLSX file (from Dash Upload),
    read every sheet, and return a dict:
        {
            "Sheet1": [["Header1", "Header2"], ["val1", "val2"], ...],
            "Sheet2": [...],
        }
    Cell values are converted to strings. None cells become "".
    """
    if "," in contents_b64:
        contents_b64 = contents_b64.split(",", 1)[1]

    raw = base64.b64decode(contents_b64)
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)

    sheets: dict[str, list[list[str]]] = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            str_row = [str(cell) if cell is not None else "" for cell in row]
            # Skip fully empty rows
            if any(c.strip() for c in str_row):
                rows.append(str_row)
        sheets[sheet_name] = rows

    wb.close()
    return sheets


def format_sheets_for_prompt(sheets: dict) -> str:
    """
    Format parsed Excel sheets into a readable string for LLM context.
    Includes sheet name headers, column letters, and row numbers.
    """
    if not sheets:
        return "(No Excel data loaded)"

    for sheet_name, sheet_details in sheets.items():
        columns = {}
        for cell in sheet_details["cells"]:
            if not cell["is_header"]:
                columns[cell["col_index"]] = columns.get(cell["col_index"], [])
                columns[cell["col_index"]].append(cell["display_value"])
        for c_in, c_val in columns.items():
            print(c_in, len(c_val))
        for c_in, c_name in enumerate(sheet_details["headers"]):
            print(c_in, len(columns.get(c_in, [])), c_name)
        dataFrame = pd.DataFrame(
            {
                c_name: columns.get(c_in, [])
                for c_in, c_name in enumerate(sheet_details["headers"])
            }
        )

        print(dataFrame.to_string())
    lines = []
    for sheet_name, rows in sheets.items():
        lines.append(f'=== Sheet: "{sheet_name}" ===')
        if not rows:
            lines.append("(empty sheet)")
            lines.append("")
            continue

        # First row = headers
        headers = rows[0]
        num_cols = len(headers)
        col_letters = [_col_letter(i) for i in range(num_cols)]

        # Header row with column letters
        header_line = "     " + " | ".join(
            f"Col {cl}: {h}" for cl, h in zip(col_letters, headers)
        )
        lines.append(header_line)
        lines.append("     " + "-" * 60)

        # Data rows (1-indexed from row 2 in spreadsheet, but row 1 in our list is header)
        for row_idx, row in enumerate(rows[1:], start=2):
            cells = " | ".join(str(v) for v in row)
            lines.append(f"Row {row_idx:>3}: {cells}")

        lines.append("")

    return "\n".join(lines)


def _col_letter(index: int) -> str:
    """Convert 0-based column index to Excel-style letter (A, B, ... Z, AA, AB, ...)."""
    result = ""
    idx = index
    while True:
        result = chr(65 + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result
