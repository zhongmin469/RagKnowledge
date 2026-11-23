"""会话管理路由（多用户隔离：仅当前用户可操作本人会话）。

SQL 全部位于 services/chat_store；本层只做编排与统一包络。
越权与不存在统一返回 40402，不区分二者，避免通过错误码探测他人会话是否存在。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..errors import BizError, ok, ERR_SESSION_NOT_FOUND
from ..schemas.chat import (
    SessionCreate, SessionRename, SessionPinUpdate, SessionArchiveUpdate, SessionBatchAction,
)
from ..services import chat_store, app_config, audit
from ..services import io_log
from ..services.auth_deps import get_current_user

router = APIRouter(prefix="/api/chat/session", tags=["session"])


@router.post("")
async def create_session(body: SessionCreate, user: dict = Depends(get_current_user)):
    """POST /api/chat/session —— 新建当前用户私有会话。"""
    item = await chat_store.create_session(user["user_id"], body.session_name)
    return ok(item, "会话已创建")


@router.get("/list")
async def list_sessions(
    page: int = Query(1, ge=1),
    size: Optional[int] = Query(None, ge=1, le=500),
    keyword: Optional[str] = Query(None, max_length=128),
    archived: bool = Query(False, description="true=只看已归档，false=主列表"),
    cursor_last_active_at: Optional[str] = Query(None, description="keyset 游标：上一页最后一条的活跃时间"),
    cursor_session_id: Optional[int] = Query(None, description="keyset 游标：上一页最后一条的会话 ID"),
    cursor_is_pinned: Optional[bool] = Query(None, description="keyset 游标：上一页最后一条是否置顶"),
    user: dict = Depends(get_current_user),
):
    """GET /api/chat/session/list?page=&size=&keyword=&archived= —— 当前用户会话及记录数。

    兼容两种分页：
    - 旧调用：page/size；
    - 新调用：cursor_last_active_at + cursor_session_id + cursor_is_pinned，返回 next_cursor。
    """
    if size is None:
        try:
            size = int(await app_config.get_value("SESSION_LIST_PAGE_SIZE"))
        except Exception:  # noqa: BLE001 - 配置异常回落默认 50
            size = 50
    size = max(1, min(int(size), 500))
    offset = (page - 1) * size
    # 主列表读取前先做一次自动归档，保证 200+ 会话时侧栏只展示近期活跃项
    if not archived:
        try:
            days = int(await app_config.get_value("SESSION_ARCHIVE_DAYS"))
            await chat_store.archive_stale_sessions(user["user_id"], days)
        except Exception:  # noqa: BLE001 - 归档失败不影响列表读取
            pass

    cursor_dt = None
    if cursor_last_active_at:
        try:
            cursor_dt = datetime.fromisoformat(cursor_last_active_at.replace("Z", "+00:00"))
        except ValueError:
            cursor_dt = None
    total, items, archived_total, next_cursor = await chat_store.list_sessions(
        user["user_id"],
        limit=size,
        offset=offset if (cursor_dt is None or archived) else 0,
        keyword=keyword,
        archived=archived,
        cursor_last_active_at=cursor_dt,
        cursor_session_id=cursor_session_id,
        cursor_is_pinned=cursor_is_pinned,
    )
    return ok({
        "total": total,
        "list": items,
        "page": page,
        "size": size,
        "keyword": keyword,
        "archived": archived,
        "archived_total": archived_total,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
    })


@router.post("/batch")
async def batch_sessions(body: SessionBatchAction, user: dict = Depends(get_current_user)):
    """POST /api/chat/session/batch —— 批量置顶/取消置顶/归档/恢复本人会话。

    逐条校验归属：越权/不存在/状态不合法计入 failed，成功项不回滚；不提供删除。
    """
    succeeded: list[int] = []
    failed: list[dict] = []
    for session_id in list(dict.fromkeys(body.session_ids)):
        try:
            if body.action in ("pin", "unpin"):
                await chat_store.set_session_pinned(session_id, user["user_id"], body.action == "pin")
            else:
                await chat_store.set_session_archived(session_id, user["user_id"], body.action == "archive")
            succeeded.append(session_id)
        except BizError as exc:
            failed.append({"session_id": session_id, "code": ERR_SESSION_NOT_FOUND, "msg": exc.msg})
        except Exception:  # noqa: BLE001 - 单条失败不影响其余项
            failed.append({"session_id": session_id, "code": 50001, "msg": "操作失败，请稍后重试"})
    return ok({"action": body.action, "succeeded": succeeded, "failed": failed}, "批量操作已完成")


@router.patch("/{session_id}/pin")
async def pin_session(
    session_id: int,
    body: SessionPinUpdate,
    user: dict = Depends(get_current_user),
):
    """PATCH /api/chat/session/{id}/pin —— 置顶/取消置顶本人活跃会话。"""
    item = await chat_store.set_session_pinned(session_id, user["user_id"], body.pinned)
    return ok(item, "已置顶" if body.pinned else "已取消置顶")


@router.patch("/{session_id}/archive")
async def archive_session(
    session_id: int,
    body: SessionArchiveUpdate,
    user: dict = Depends(get_current_user),
):
    """PATCH /api/chat/session/{id}/archive —— 归档/恢复本人会话。"""
    item = await chat_store.set_session_archived(session_id, user["user_id"], body.archived)
    return ok(item, "会话已归档" if body.archived else "会话已恢复")


@router.patch("/{session_id}")
async def rename_session(
    session_id: int,
    body: SessionRename,
    user: dict = Depends(get_current_user),
):
    """PATCH /api/chat/session/{session_id} —— 重命名本人会话；越权返回 40402。"""
    item = await chat_store.rename_session(session_id, user["user_id"], body.session_name)
    return ok(item, "会话已重命名")


@router.delete("/{session_id}")
async def delete_session(session_id: int, user: dict = Depends(get_current_user)):
    """DELETE /api/chat/session/{session_id} —— 删除本人会话及其记录；越权返回 40402。

    v5 R6：运行日志改为软删除（管理员保留期内仍可审计），删除动作写 `SESSION_DELETE`。
    """
    item = await chat_store.get_session_for_user(session_id, user["user_id"])
    if item is None:
        raise BizError(ERR_SESSION_NOT_FOUND, "会话不存在或已删除", http_status=404)
    records = await chat_store.count_records(session_id)
    await chat_store.delete_session(session_id, user["user_id"])
    soft_deleted = 0
    try:
        soft_deleted = await io_log.delete_session_logs(session_id)
    except Exception:  # noqa: BLE001 - 日志标记失败不影响会话删除
        pass
    await audit.log_operation(
        user["user_id"], audit.SESSION_DELETE, "session", session_id, 1,
        {"session_name": item.get("session_name"), "records": records, "io_logs": soft_deleted},
    )
    return ok({"session_id": session_id}, "会话已删除")
