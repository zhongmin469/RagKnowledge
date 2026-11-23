"""FastAPI 应用入口。

启动方式（在 backend/ 目录下）：
    uvicorn main:app --reload --host 127.0.0.1 --port 8000
在线接口文档：http://127.0.0.1:8000/docs

职责：
- lifespan：启动初始化数据库连接池（失败降级不崩）、关闭时回收；
- CORS：仅放行本地 Vite 开发源；
- 注册全局异常处理器、request_id 中间件、四个路由模块；
- 启动时输出配置警告（缺 Key、维度异常等），不做阻断式强校验（骨架阶段可独立启动）。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import llm as llm_client
from .errors import register_exception_handlers, ok
from .app_logging import register_middlewares
from .db import init_pool, close_pool, is_ready
from .routers import (
    system, docs, session, session_memory, chat, auth, admin, admin_config, admin_io, admin_feedback, admin_prompt, user_io, biz, export, workflow, admin_audit, admin_users_view,
)
from .services import chat_store, export_store, session_memory_store, io_log, feedback_store, prompt_store, quota, workflow as workflow_service, audit

logger = logging.getLogger("rag.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # ---- 启动：中间件在模块级注册；此处只做资源初始化 ----
    for w in settings.safety_check():
        logger.warning("配置提示：%s", w)
    await init_pool()
    await chat_store.ensure_record_schema()
    await session_memory_store.ensure_memory_schema()
    await export_store.ensure_export_schema()
    await export_store.cleanup_expired()
    # v3 / WP3：I/O 运行日志建表 + 异步写入 worker + 保留期清理
    await io_log.ensure_schema()
    # v5 R8：operation_log 审计索引
    await audit.ensure_schema()
    await feedback_store.ensure_schema()
    await prompt_store.ensure_schema()
    await quota.ensure_schema()
    io_log.start_worker()
    # v3 / WP4：工作流任务建表 + 启动恢复（遗留 running → interrupted）
    await workflow_service.ensure_schema()
    await workflow_service.recover_interrupted()
    # N9 延迟：轻任务模型启动预热，避免首轮 query 改写承担百炼冷启动
    try:
        await asyncio.wait_for(asyncio.to_thread(llm_client.warm_small_model), timeout=20)
    except Exception:  # noqa: BLE001 - 预热失败不阻断启动
        logger.warning("轻任务模型预热超时或失败，稍后按需重试", exc_info=True)
    io_cleanup_task = asyncio.create_task(io_log.cleanup_loop())
    cleanup_task = asyncio.create_task(export_store.cleanup_loop())
    logger.info(
        "应用启动：db_ready=%s | LLM=%s | EMBEDDING_DIM=%d | TOP_K=%d",
        is_ready(),
        settings.LLM_MODEL,
        settings.EMBEDDING_DIM,
        settings.TOP_K,
    )
    yield
    # ---- 关闭 ----
    cleanup_task.cancel()
    io_cleanup_task.cancel()
    for task in (cleanup_task, io_cleanup_task):
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - 关闭阶段不报错
            pass
    await io_log.stop_worker()
    # 工作流后台任务先取消：执行器会把未完成状态落为 interrupted，下次启动可 resume
    tasks = [t for t in workflow_service.RUNNING.values() if not t.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await close_pool()
    logger.info("应用已关闭，连接池已回收")


app = FastAPI(
    title="企业文档智能问答 Agent（RAG + LangGraph）",
    version="0.1.0-skeleton",
    description="私有文档知识库 + 多工具 Agent Demo；骨架阶段，接口按里程碑逐步接通。",
    lifespan=lifespan,
)

# CORS（开发期 Vite 代理 / 浏览器直连双兜底；只放行本地源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)
register_middlewares(app)

# 路由注册（前缀已在各 router 内定义为 /api/...）
app.include_router(system.router)
app.include_router(docs.router)
app.include_router(session.router)
app.include_router(session_memory.router)
app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin_config.router)
app.include_router(admin_io.router)
app.include_router(admin_feedback.router)
app.include_router(admin_prompt.router)
app.include_router(admin_audit.router)
app.include_router(admin_users_view.router)
app.include_router(user_io.router)
app.include_router(biz.router)
app.include_router(export.router)
app.include_router(workflow.router)


@app.get("/health", tags=["meta"])
async def health():
    """轻量健康检查，不依赖数据库。"""
    return ok({"status": "up", "db_ready": is_ready(), "stage": "skeleton"})


@app.get("/", tags=["meta"])
async def index():
    return ok({
        "name": "RagKnowledge",
        "docs": "/docs",
        "health": "/health",
        "info": "/api/system/info",
        "stage": "skeleton",
    })

