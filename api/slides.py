from fastapi import APIRouter

router = APIRouter()
from db.queries import get_slides_for_pptx


@router.get("/")
async def get_slides(pptx_id: str, slide_index: int):
    slides_data = get_slides_for_pptx(pptx_id)
    if not slides_data:
        return {"message": "No slides found for the specified PPTX file"}
    for slide in slides_data:
        if slide["slide_index"] == slide_index:
            return {"slide": slide}
    return {"message": "Slide not found"}
