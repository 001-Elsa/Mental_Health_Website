import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from starlette.responses import Response

from backend.core.config import get_settings
from backend.routers import admin, analytics, articles, auth, community, consult, content, knowledge, mood, recommendations, users
from backend.services.cache import cache_service
from backend.services.ai_client import ai_client
from backend.services.observability import HTTP_DURATION, HTTP_IN_PROGRESS, HTTP_REQUESTS
from database.database import SyncSessionLocal, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().environment == "development":
        init_db()
    await ai_client.start()
    try:
        yield
    finally:
        await ai_client.close()


app = FastAPI(
    title=get_settings().app_name,
    description="高校心理健康支持平台 API",
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
app.add_middleware(GZipMiddleware, minimum_size=1024)

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
    HTTP_IN_PROGRESS.labels(request.method).inc()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration = time.perf_counter() - started
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        HTTP_IN_PROGRESS.labels(request.method).dec()
        HTTP_REQUESTS.labels(request.method, route_path, str(status_code)).inc()
        HTTP_DURATION.labels(request.method, route_path).observe(duration)
        logging.getLogger("mental_health.api").info(
            "%s %s %s %.1fms request_id=%s",
            request.method,
            request.url.path,
            status_code,
            duration * 1000,
            request_id,
        )


@app.get("/metrics", include_in_schema=False)
def metrics():
    if get_settings().environment == "production":
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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

frontend_root = Path(__file__).resolve().parent.parent / "frontend"
static_dir = frontend_root / "dist" if (frontend_root / "dist").exists() else frontend_root
assets_dir = static_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/") and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path in {"/", "/index.html"} and response.status_code == 200:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    requested_path = (static_dir / full_path).resolve()
    try:
        requested_path.relative_to(static_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Not Found")

    if full_path and requested_path.is_file():
        return FileResponse(requested_path)

    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not Found")
