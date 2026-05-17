from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_citations():
    return {"message": "Citations endpoint not implemented yet"}
