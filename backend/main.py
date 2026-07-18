import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database.database import SyncSessionLocal, init_db
from backend.core.config import get_settings
from backend.services.cache import cache_service
from backend.routers import admin, analytics, articles, content, mood, community, auth, consult, knowledge, recommendations, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().environment == "development":
        init_db()
    yield

app = FastAPI(
    title=get_settings().app_name,
    description="Mental Health AI Assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(analytics.router)
app.include_router(articles.router)
app.include_router(content.router)
app.include_router(mood.router)
app.include_router(community.router)
app.include_router(auth.router)
app.include_router(consult.router)
app.include_router(users.router)
app.include_router(recommendations.router)
app.include_router(admin.router)
app.include_router(knowledge.router)


@app.get("/api/health", tags=["系统"])
def health_check():
    with SyncSessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "cache": cache_service.backend}


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logging.getLogger("mental_health.api").info(
        "%s %s %s %.1fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request_id,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "detail": exc.detail,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "detail": "请求参数不符合接口要求",
            "errors": exc.errors(),
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger("mental_health.api").exception(
        "Unhandled API error request_id=%s",
        getattr(request.state, "request_id", ""),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "detail": "服务暂时不可用，请稍后重试",
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


uploads_dir = Path(__file__).resolve().parent.parent / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# 静态文件（前端页面）
frontend_root = Path(__file__).resolve().parent.parent / "frontend"
static_dir = frontend_root / "dist" if (frontend_root / "dist").exists() else frontend_root
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
