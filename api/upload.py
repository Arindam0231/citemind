import base64
import hashlib
import io
import json
import logging
import os
import tempfile

from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from pydantic import BaseModel

from db.queries import (
    create_project,
    get_excel_sheets,
    get_cells_for_sheet,
    get_slides_for_pptx,
    insert_cells_bulk,
    insert_excel_sheet,
    insert_pptx_file,
    insert_shapes_bulk,
    insert_slide,
    insert_xlsx_file,
    get_xlsx_file_by_sha256,
    mark_pptx_parsed,
    mark_xlsx_parsed,
)
from parsers.pptx_parser import parse_pptx_file
from parsers.slide_renderer import export_slide_to_png
from parsers.xlsx_parser import parse_workbook
import openpyxl

log = logging.getLogger(__name__)

router = APIRouter()


class InitializeRequest(BaseModel):
    pptx_id: str
    xlsx_id: str


@router.post("/pptx")
async def upload_pptx(file: UploadFile = File(...)):
    print(file)
    if not file.filename.endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Must be a .pptx file")

    try:
        raw_bytes = await file.read()
        b64_content = base64.b64encode(raw_bytes).decode("utf-8")

        parsed = parse_pptx_file(b64_content)
        sha = parsed["sha256"]

        processed_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "processed"))
        os.makedirs(processed_dir, exist_ok=True)
        storage_path = os.path.join(processed_dir, f"{sha}.pptx")
        with open(storage_path, "wb") as f:
            f.write(raw_bytes)

        fid = insert_pptx_file(
            original_name=file.filename,
            storage_path=storage_path,
            slide_count=parsed["slide_count"],
            slide_width_emu=parsed["slide_width_emu"],
            slide_height_emu=parsed["slide_height_emu"],
            sha256=sha,
        )

        slides_response = []
        for slide_index in range(len(parsed["slides"])):
            s = parsed["slides"][slide_index]
            
            # Temporary slide index ID is generated during insert_slide
            # But wait, insert_slide returns a slide ID
            sid = insert_slide(
                pptx_file_id=fid,
                slide_index=s["slide_index"],
                slide_number=s["slide_number"],
                title=s["title"],
                png_path="",  # We will update it or insert with it!
                shape_count=s["shape_count"],
                has_table=s["has_table"],
                has_chart=s["has_chart"],
            )

            # Export slide PNG to processed/slides/{sid}.png
            slides_dir = os.path.join(processed_dir, "slides")
            os.makedirs(slides_dir, exist_ok=True)
            png_path = os.path.join(slides_dir, f"{sid}.png")
            export_slide_to_png(raw_bytes, slide_index, png_path)

            # Update the png_path inside slides table for this slide
            from db.connection import get_db
            with get_db() as db:
                db.execute("UPDATE slides SET png_path=? WHERE id=?", (png_path, sid))

            db_shapes = []
            if s["shapes"]:
                bulk_shapes = []
                for sh in s["shapes"]:
                    sh["slide_id"] = sid
                    bulk_shapes.append(sh)
                shape_ids = insert_shapes_bulk(bulk_shapes)
                
                for sh, shid in zip(s["shapes"], shape_ids):
                    db_shapes.append({
                        "id": shid,
                        "pptx_shape_id": sh["pptx_shape_id"],
                        "shape_name": sh["shape_name"],
                        "shape_type": sh["shape_type"],
                        "x_pct": sh["x_pct"],
                        "y_pct": sh["y_pct"],
                        "w_pct": sh["w_pct"],
                        "h_pct": sh["h_pct"],
                        "full_text": sh["full_text"],
                        "runs_json": json.loads(sh["runs_json"]),
                        "z_order": sh["z_order"]
                    })

            slides_response.append({
                "slide_id": sid,
                "slide_index": s["slide_index"],
                "png_url": f"/api/slides/{sid}/png",
                "shapes": db_shapes
            })

        mark_pptx_parsed(fid)

        return {
            "pptx_file_id": fid,
            "file_id": fid,
            "filename": file.filename,
            "slides": slides_response
        }

    except Exception as e:
        log.error("PPTX error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/xlsx")
async def upload_xlsx(file: UploadFile = File(...)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Must be a .xlsx file")

    try:
        raw_bytes = await file.read()
        sha = hashlib.sha256(raw_bytes).hexdigest()
        search_sha = sha

        try:
            temp_wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True)
            prop_id = temp_wb.properties.identifier
            temp_wb.close()
            if prop_id and str(prop_id).startswith("citemind_"):
                search_sha = str(prop_id).split("citemind_")[1]
        except Exception:
            pass

        existing = get_xlsx_file_by_sha256(search_sha)
        if existing:
            fid = existing["id"]
            return {
                "file_id": fid,
                "filename": file.filename,
                "message": f"Loaded cached version of {file.filename}",
            }

        b64_content = base64.b64encode(raw_bytes).decode("utf-8")
        parsed = parse_workbook(b64_content, file.filename)
        llm_insights = parsed.get("llm_insights", {})
        ingestion_report = parsed.get("ingestion_report", {})

        fid = insert_xlsx_file(
            original_name=file.filename,
            storage_path=parsed.get("processed_path", ""),
            sheet_names=parsed["sheet_names"],
            sha256=parsed["sha256"],
        )

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
                    ingestion_report=json.dumps(ingestion_report.get(sname, {})),
                    llm_insights=json.dumps(llm_insights.get(sname, {})),
                )
                if sdata["cells"]:
                    bulk_cells = []
                    for c in sdata["cells"]:
                        c["sheet_id"] = sid
                        bulk_cells.append(c)
                    insert_cells_bulk(bulk_cells)

        mark_xlsx_parsed(fid)

        return {
            "file_id": fid,
            "filename": file.filename,
            "message": f"Excel file '{file.filename}' ingested.\n{json.dumps(ingestion_report, indent=2)}",
        }

    except Exception as e:
        log.error("XLSX error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize")
async def initialize_project(req: InitializeRequest):
    try:
        pid = create_project("CiteMind Project", req.pptx_id, req.xlsx_id)
        return {"project_id": pid}
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))
