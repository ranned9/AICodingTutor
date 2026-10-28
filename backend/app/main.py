import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.ai_router import router as ai_router
from app.api.case_router import router as case_router
from app.api.debug_router import router as debug_router
from app.api.response import ErrorCode, error_response
from app.api.snapshot_router import router as snapshot_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("调试实训平台后端服务启动")
    yield
    logger.info("调试实训平台后端服务关闭")


app = FastAPI(title="C语言内存时序可视化调试实训平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("未处理异常: %s", exc)
    return JSONResponse(status_code=200, content=error_response(ErrorCode.UNKNOWN_ERROR))


app.include_router(case_router)
app.include_router(debug_router)
app.include_router(snapshot_router)
app.include_router(ai_router)


@app.get("/api/health")
async def health_check():
    return error_response(ErrorCode.SUCCESS, "服务正常", {"status": "ok"})


frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")