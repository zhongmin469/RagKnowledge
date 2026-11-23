"""管理员用户全景只读接口（v5 R7 / R9）。

- 全部接口 `require_admin`；目标账号不存在统一 40403；
- 目标会话不属于该用户统一 40402，不泄露会话存在性；
- 打开他人消息/概览/链路详情写 `ADMIN_VIEW_USER_DATA`（60 秒去重），列表类查询不逐条写。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..errors import BizError, ERR_PARAM, ERR_SESSION_NOT_FOUND, ERR_USER_NOT_FOUND, ok
from ..services import account_store, admin_user_view, audit
from ..services.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/users", tags=["admin-users-view"])


def _date(value: Optional[str], field: str) -> Optional[str]:
    if value is None or value == "":
        return None
    text = value.strip()
    if len(text) not in (10, 19):
        raise BizError(ERR_PARAM, f"{field} 需为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS", http_status=400)
    fmt = "%Y-%m-%d" if len(text) == 10 else "%Y-%m-%d %H:%M:%S"
    try:
        datetime.strptime(text, fmt)
    except ValueError as exc:
        raise BizError(ERR_PARAM, f"{field} 不是合法日期：{text}", http_status=400) from exc
    return text


async def _ensure_user(user_id: int) -> dict:
    user = await account_store.get_user_by_id(int(user_id))
    if user is None:
        raise BizError(ERR_USER_NOT_FOUND, "账号不存在", http_status=404)
    return user


@router.get("/{user_id}/overview")
async def user_overview(user_id: int, admin: dict = Depends(require_admin)):
    """GET /api/admin/users/{id}/overview —— 账号概览与使用汇总。"""
    data = await admin_user_view.overview(user_id)
    if data is None:
        raise BizError(ERR_USER_NOT_FOUND, "账号不存在", http_status=404)
    await audit.log_view(admin["user_id"], user_id, "overview", str(user_id))
    return ok(data)


@router.get("/{user_id}/qa")
async def user_qa(
    user_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(ok|abort|error|timeout|rejected)$"),
    intent: Optional[str] = Query(None, max_length=32),
    keyword: Optional[str] = Query(None, max_length=128),
    include_deleted: bool = Query(True, description="是否包含用户已删除的记录（管理员默认可见）"),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/users/{id}/qa —— 该用户问答轮次（含链路 trace_id）。"""
    await _ensure_user(user_id)
    total, items = await admin_user_view.qa(
        user_id, page=page, size=size, start=_date(start, "start"), end=_date(end, "end"),
        status=status, intent=intent, keyword=keyword, include_deleted=include_deleted,
    )
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/{user_id}/sessions")
async def user_sessions(
    user_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, max_length=128),
    archived: Optional[bool] = Query(None, description="不传=含归档"),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/users/{id}/sessions —— 该用户全部会话（只读）。"""
    await _ensure_user(user_id)
    total, items = await admin_user_view.sessions(
        user_id, page=page, size=size, keyword=keyword, archived=archived
    )
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/{user_id}/sessions/{session_id}/messages")
async def user_session_messages(
    user_id: int,
    session_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    admin: dict = Depends(require_admin),
):
    """GET /api/admin/users/{id}/sessions/{sid}/messages —— 只读消息列表。"""
    await _ensure_user(user_id)
    data = await admin_user_view.messages(user_id, session_id, page=page, size=size)
    if data is None:
        raise BizError(ERR_SESSION_NOT_FOUND, "会话不存在或不属于该用户", http_status=404)
    total, items = data
    await audit.log_view(admin["user_id"], user_id, "message", f"{user_id}:{session_id}")
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/{user_id}/documents")
async def user_documents(
    user_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, max_length=32),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/users/{id}/documents —— 该用户发起的文档动作（按审计反查）。"""
    await _ensure_user(user_id)
    total, items = await admin_user_view.documents(
        user_id, page=page, size=size, action=action,
        start=_date(start, "start"), end=_date(end, "end"),
    )
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/{user_id}/feedback")
async def user_feedback(
    user_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    rating: Optional[int] = Query(None, ge=-1, le=1),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/users/{id}/feedback —— 该用户点赞/点踩记录。"""
    await _ensure_user(user_id)
    total, items = await admin_user_view.feedback(user_id, page=page, size=size, rating=rating)
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/{user_id}/activity")
async def user_activity(
    user_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    type: Optional[str] = Query(None, pattern="^(qa|login|doc|export|admin|other)$"),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/users/{id}/activity —— 问答 + 操作审计的统一时间线。"""
    await _ensure_user(user_id)
    total, items = await admin_user_view.activity(
        user_id, page=page, size=size, start=_date(start, "start"), end=_date(end, "end"), type_=type
    )
    return ok({"total": total, "list": items, "page": page, "size": size})
