"""管理端操作审计查询与导出（v5 R8）。

- `GET /api/admin/audit-logs`：按操作人 / 被操作用户 / 动作 / 结果 / 时间 / 关键词分页查询。
- `GET /api/admin/audit-logs/actions`：动作枚举与中文名，供前端下拉。
- `GET /api/admin/audit-logs/export`：同筛选导出 CSV，上限 1 万行，落可重复下载链接。

只读能力；审计记录不提供删除/清空接口（v5 R9）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..errors import BizError, ERR_PARAM, ok
from ..services import audit, export_store
from ..services.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/audit-logs", tags=["admin-audit"])


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


def _filters(
    actor_user_id: Optional[int],
    target_user_id: Optional[int],
    action: Optional[str],
    target_type: Optional[str],
    result: Optional[int],
    start: Optional[str],
    end: Optional[str],
    keyword: Optional[str],
) -> dict:
    return {
        "actor_user_id": actor_user_id,
        "target_user_id": target_user_id,
        "action": action,
        "target_type": target_type,
        "result": result,
        "start": _date(start, "start"),
        "end": _date(end, "end"),
        "keyword": keyword,
    }


@router.get("/actions")
async def list_actions(_: dict = Depends(require_admin)):
    """GET /api/admin/audit-logs/actions —— 审计动作枚举（含中文名）。"""
    return ok({"list": audit.actions()})


@router.get("")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    actor_user_id: Optional[int] = Query(None, ge=1, description="操作人"),
    target_user_id: Optional[int] = Query(None, ge=1, description="被操作用户（target_type=user）"),
    action: Optional[str] = Query(None, max_length=64),
    target_type: Optional[str] = Query(None, max_length=32),
    result: Optional[int] = Query(None, ge=0, le=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, max_length=128),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/audit-logs —— 操作审计分页。"""
    total, items = await audit.list_logs(
        page=page,
        size=size,
        **_filters(actor_user_id, target_user_id, action, target_type, result, start, end, keyword),
    )
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/export")
async def export_audit_logs(
    actor_user_id: Optional[int] = Query(None, ge=1),
    target_user_id: Optional[int] = Query(None, ge=1),
    action: Optional[str] = Query(None, max_length=64),
    target_type: Optional[str] = Query(None, max_length=32),
    result: Optional[int] = Query(None, ge=0, le=1),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, max_length=128),
    admin: dict = Depends(require_admin),
):
    """GET /api/admin/audit-logs/export —— 导出 CSV（上限 1 万行）。"""
    filters = _filters(actor_user_id, target_user_id, action, target_type, result, start, end, keyword)
    rows = await audit.list_for_export(**filters)
    if not rows:
        raise BizError(ERR_PARAM, "当前筛选条件没有可导出的审计记录", http_status=400)
    columns = [
        {"key": "created_at", "title": "时间"},
        {"key": "actor_user_id", "title": "操作人ID"},
        {"key": "actor_username", "title": "操作人"},
        {"key": "action", "title": "动作"},
        {"key": "action_label", "title": "动作说明"},
        {"key": "target_type", "title": "对象类型"},
        {"key": "target_id", "title": "对象ID"},
        {"key": "result", "title": "结果"},
        {"key": "detail", "title": "详情"},
    ]
    dict_rows = [
        {**r, "detail": "" if r.get("detail") is None else str(r["detail"]).replace("\n", " ")}
        for r in rows
    ]
    info = await export_store.create_export(admin["user_id"], "audit-logs", columns, dict_rows)
    if not info:
        raise BizError(ERR_PARAM, "导出生成失败，请缩小筛选范围后重试", http_status=500)
    await audit.log_operation(
        admin["user_id"], audit.AUDIT_EXPORT, "audit_log", "all", 1,
        {"filters": {k: v for k, v in filters.items() if v is not None}, "rows": len(rows),
         "capped": len(rows) >= 10000},
    )
    return ok({**info, "capped": len(rows) >= 10000}, "导出已生成")
