from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.upload import router as upload_router
from api.slides import router as slides_router
from api.citations import router as citations_router
from api.chat import router as chat_router

app = FastAPI(
    title="CiteMind API",
    description="FastAPI backend for CiteMind",
    version="0.1.0",
)

# Allow all origins for development (React runs on a different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api/upload", tags=["upload"])
app.include_router(slides_router, prefix="/api/slides", tags=["slides"])
app.include_router(citations_router, prefix="/api/citations", tags=["citations"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
