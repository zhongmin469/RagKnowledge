"""管理端反馈/评测集查询与导出（v3 / WP5-3）。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..errors import BizError, ok, ERR_PARAM
from ..services import feedback_store, audit
from ..services.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/feedback", tags=["admin-feedback"])


@router.get("")
async def list_feedback(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    rating: Optional[int] = Query(None, ge=-1, le=1),
    user_id: Optional[int] = Query(None, ge=1, description="按提交用户筛选"),
    _: dict = Depends(require_admin),
):
    """GET /api/admin/feedback —— 评测集分页；rating=1 赞 / -1 踩；可按用户筛选。"""
    if rating not in (None, 1, -1):
        raise BizError(ERR_PARAM, "rating 仅支持 1 或 -1", http_status=400)
    total, items = await feedback_store.list_feedback(
        rating=rating, limit=size, offset=(page - 1) * size, user_id=user_id
    )
    return ok({"total": total, "list": items, "page": page, "size": size})


@router.get("/export")
async def export_feedback(admin: dict = Depends(require_admin)):
    """GET /api/admin/feedback/export —— JSONL 评测集，一行一条，便于离线回放。"""
    items = await feedback_store.export_feedback()
    lines = [json.dumps(x, ensure_ascii=False, default=str) for x in items]
    body = "\n".join(lines) + ("\n" if lines else "")
    filename = f"feedback-eval-{datetime.now().strftime('%Y%m%d')}.jsonl"
    await audit.log_operation(
        admin["user_id"], audit.FEEDBACK_EXPORT, "feedback", "all", 1, {"rows": len(items)}
    )
    return Response(
        content=body.encode("utf-8"),
        media_type="application/jsonl; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
