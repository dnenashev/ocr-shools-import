from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from backend.database.mongodb import connect_to_mongo, close_mongo_connection
from backend.routes import upload, admin
from backend.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events для подключения/отключения от MongoDB"""
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="OCR CRM",
    description="Система для распознавания данных учеников с фотографий и отправки в AMO CRM",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
# Для production укажите конкретные домены вместо ["*"]
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роуты
app.include_router(upload.router, prefix="/api", tags=["Upload"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

# Статические файлы для изображений
if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Статические файлы для frontend
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница - редирект на страницу загрузки"""
    if os.path.exists("frontend/upload.html"):
        return FileResponse("frontend/upload.html")
    return HTMLResponse(content="""
    <html>
        <head><title>OCR CRM</title></head>
        <body>
            <h1>OCR CRM System</h1>
            <p>API is running. <a href="/docs">API Documentation</a></p>
            <p><a href="/admin">Admin Panel</a></p>
        </body>
    </html>
    """)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    """Админ-панель"""
    if os.path.exists("frontend/admin.html"):
        return FileResponse("frontend/admin.html")
    return HTMLResponse(content="<h1>Admin panel not found</h1>")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "OCR CRM"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )

