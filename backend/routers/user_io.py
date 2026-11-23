"""用户侧运行日志权利接口（v3 / WP3 §5.6；v5 R6 调整删除语义）。

- `GET /api/me/io-logs/export`：导出本人对话记录（JSON 附件）。
- `DELETE /api/me/io-logs`：从本人视角删除全部运行日志（软删除，管理员保留期内仍可审计查看）。
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..errors import BizError, ERR_TRACE_NOT_FOUND, ok
from ..services import audit, io_log
from ..services.auth_deps import get_current_user

router = APIRouter(prefix="/api/me/io-logs", tags=["me-io"])


@router.get("/export")
async def export_my_logs(user: dict = Depends(get_current_user)):
    """导出本人全部问答 I/O 记录为 JSON 文本（受保留期约束）。"""
    rows = await io_log.user_export(user["user_id"])
    payload = {
        "exported_at": datetime.now().isoformat(sep=" "),
        "user_id": user["user_id"],
        "count": len(rows),
        "records": rows,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    filename = f"chat-io-logs-{user['user_id']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    await audit.log_operation(
        user["user_id"], audit.USER_LOG_EXPORT, "io_log", user["user_id"], 1, {"count": len(rows)}
    )
    return Response(
        content=body.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("")
async def delete_my_logs(user: dict = Depends(get_current_user)):
    """从本人视角删除全部运行日志（v5 R6：软删除，管理员保留期内仍可查）。"""
    removed = await io_log.delete_user_logs(user["user_id"])
    await audit.log_operation(
        user["user_id"], audit.USER_LOG_DELETE, "io_log", user["user_id"], 1,
        {"removed": removed, "mode": "soft"},
    )
    return ok({"removed": removed, "mode": "soft"}, "已从你的视角删除本人运行日志")


@router.get("/{trace_id}")
async def get_my_trace(trace_id: str, user: dict = Depends(get_current_user)):
    """GET /api/me/io-logs/{trace_id} —— 本人单轮链路详情（消息「链路」抽屉数据源）。

    只允许查本人日志；他人 trace 统一返回“不存在”，不暴露是否存在。
    """
    item = await io_log.get_detail(trace_id)
    if item is None or int(item.get("user_id") or 0) != int(user["user_id"]):
        raise BizError(ERR_TRACE_NOT_FOUND, "未找到该轮的运行日志", http_status=404)
    return ok(item)

