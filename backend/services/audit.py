"""管理类与权限类操作审计。

只记录管理类与权限类操作，**不记录聊天问答内容**。
审计写入失败绝不影响主流程：统一降级为 warning 日志。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Optional

from ..db import get_pool

logger = logging.getLogger("rag.audit")

# 审计动作常量
AUTH_LOGIN = "AUTH_LOGIN"
AUTH_PASSWORD = "AUTH_PASSWORD"
AUTH_PROFILE = "AUTH_PROFILE"
DOC_UPLOAD = "DOC_UPLOAD"
DOC_DELETE = "DOC_DELETE"
DOC_DOWNLOAD = "DOC_DOWNLOAD"
REPARSE = "REPARSE"
REINDEX = "REINDEX"
USER_MANAGE = "USER_MANAGE"
CONFIG_UPDATE = "CONFIG_UPDATE"
BIZ_QUERY = "BIZ_QUERY"
BIZ_EXPORT = "BIZ_EXPORT"
# v5 R6/R8/R9：用户数据权利与管理员查看留痕
USER_LOG_EXPORT = "USER_LOG_EXPORT"
USER_LOG_DELETE = "USER_LOG_DELETE"
SESSION_DELETE = "SESSION_DELETE"
SESSION_DELETE_BATCH = "SESSION_DELETE_BATCH"
ADMIN_VIEW_USER_DATA = "ADMIN_VIEW_USER_DATA"
ADMIN_IO_EXPORT = "ADMIN_IO_EXPORT"
AUDIT_EXPORT = "AUDIT_EXPORT"
FEEDBACK_EXPORT = "FEEDBACK_EXPORT"

# 动作中文名（管理端审计页下拉与列表展示共用）
ACTION_LABELS: dict[str, str] = {
    AUTH_LOGIN: "登录",
    AUTH_PASSWORD: "修改密码",
    AUTH_PROFILE: "修改昵称",
    DOC_UPLOAD: "上传文档",
    DOC_DELETE: "删除文档",
    DOC_DOWNLOAD: "下载文档",
    REPARSE: "重解析文档",
    REINDEX: "重建索引",
    USER_MANAGE: "用户管理",
    CONFIG_UPDATE: "配置变更",
    BIZ_QUERY: "业务库查询",
    BIZ_EXPORT: "业务数据导出",
    USER_LOG_EXPORT: "导出本人日志",
    USER_LOG_DELETE: "删除本人日志",
    SESSION_DELETE: "删除会话",
    SESSION_DELETE_BATCH: "批量删除会话",
    ADMIN_VIEW_USER_DATA: "查看他人数据",
    ADMIN_IO_EXPORT: "导出运行日志",
    AUDIT_EXPORT: "导出审计日志",
    FEEDBACK_EXPORT: "导出反馈评测集",
}


async def log_operation(
    actor_user_id: Optional[int],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    result: int = 1,
    detail: Optional[dict] = None,
) -> None:
    """写一条审计记录；任何异常都被吞掉并记 warning，不阻断业务。"""
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO operation_log
                            (actor_user_id, action, target_type, target_id, result, detail)
                        VALUES (%(actor)s, %(action)s, %(ttype)s, %(tid)s, %(result)s, %(detail)s::jsonb)
                        """,
                        {
                            "actor": actor_user_id,
                            "action": action,
                            "ttype": target_type,
                            "tid": str(target_id) if target_id is not None else None,
                            "result": int(result),
                            "detail": json.dumps(detail, ensure_ascii=False, default=str) if detail else None,
                        },
                    )
    except Exception:  # noqa: BLE001 - 审计失败不得影响业务
        logger.warning("审计写入失败 action=%s actor=%s（不影响主流程）", action, actor_user_id, exc_info=True)


_ENSURE_SQL = """
CREATE INDEX IF NOT EXISTS idx_operation_log_target ON operation_log (target_type, target_id, created_at DESC);
"""


async def ensure_schema() -> None:
    """启动时幂等补索引（operation_log 由 init_db/account_store 建表）。"""
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            await conn.execute(_ENSURE_SQL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("审计索引创建失败：%s", type(exc).__name__)


# ---------------------------------------------------------------- 查看留痕去重（v5 R9）
_VIEW_DEDUP: dict[tuple[int, str, str], float] = {}
_VIEW_LOCK = threading.Lock()


def view_dedup_ok(admin_user_id: int, scope: str, ref: str, seconds: int = 60) -> bool:
    """同一管理员对同一 scope+ref 在窗口内只留一条审计，防止误触点开刷屏。"""
    if seconds <= 0:
        return True
    key = (int(admin_user_id), scope, ref or "")
    now = time.monotonic()
    with _VIEW_LOCK:
        last = _VIEW_DEDUP.get(key)
        if last is not None and now - last < seconds:
            return False
        _VIEW_DEDUP[key] = now
        # 轻量清理，避免长期驻留；表规模上限约等于日活 × 查看对象数
        if len(_VIEW_DEDUP) > 5000:
            expired = [k for k, t in _VIEW_DEDUP.items() if now - t > seconds * 2]
            for k in expired:
                _VIEW_DEDUP.pop(k, None)
    return True


async def log_view(
    admin_user_id: int,
    target_user_id: int,
    scope: str,
    ref: Optional[str] = None,
    detail: Optional[dict] = None,
    dedup_seconds: Optional[int] = None,
) -> None:
    """管理员查看他人数据留痕；只读操作，失败不影响业务。"""
    if dedup_seconds is None:
        try:
            from ..config import settings

            dedup_seconds = int(settings.ADMIN_VIEW_LOG_DEDUP_SECONDS)
        except Exception:  # noqa: BLE001 - 配置异常回落 60 秒
            dedup_seconds = 60
    if not view_dedup_ok(admin_user_id, scope, ref or "", dedup_seconds):
        return
    payload = {"scope": scope}
    if ref:
        payload["ref"] = ref
    if detail:
        payload.update(detail)
    await log_operation(
        admin_user_id, ADMIN_VIEW_USER_DATA, "user", target_user_id, 1, payload
    )


# ---------------------------------------------------------------- 查询/导出（v5 R8）
def _ts(value: Any) -> Any:
    return value.isoformat(sep=" ") if isinstance(value, (datetime, date)) else value


def _where(
    actor_user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    result: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    keyword: Optional[str] = None,
) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if actor_user_id is not None:
        clauses.append("l.actor_user_id = %(actor)s")
        params["actor"] = int(actor_user_id)
    if target_user_id is not None:
        clauses.append("l.target_type = 'user' AND l.target_id = %(tuid)s")
        params["tuid"] = str(int(target_user_id))
    if action:
        clauses.append("l.action = %(action)s")
        params["action"] = action
    if target_type:
        clauses.append("l.target_type = %(ttype)s")
        params["ttype"] = target_type
    if result is not None:
        clauses.append("l.result = %(result)s")
        params["result"] = int(result)
    if start:
        clauses.append("l.created_at >= %(start)s::timestamp")
        params["start"] = start
    if end:
        if len(end) == 10:
            clauses.append("l.created_at < (%(end)s::date + 1)")
        else:
            clauses.append("l.created_at <= %(end)s::timestamp")
        params["end"] = end
    if keyword:
        clauses.append("(l.target_id ILIKE %(kw)s OR l.detail::text ILIKE %(kw)s)")
        params["kw"] = f"%{keyword}%"
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _row(row) -> dict:
    return {
        "log_id": int(row[0]),
        "created_at": _ts(row[1]),
        "actor_user_id": row[2],
        "actor_username": row[3] or "",
        "action": row[4],
        "action_label": ACTION_LABELS.get(row[4], row[4]),
        "target_type": row[5],
        "target_id": row[6],
        "result": int(row[7] or 0),
        "detail": row[8],
    }


_SELECT = """
SELECT l.log_id, l.created_at, l.actor_user_id, u.username,
       l.action, l.target_type, l.target_id, l.result, l.detail
FROM operation_log l
LEFT JOIN app_user u ON u.user_id = l.actor_user_id
"""


async def list_logs(
    page: int = 1,
    size: int = 20,
    actor_user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    result: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    keyword: Optional[str] = None,
) -> tuple[int, list[dict]]:
    where, params = _where(actor_user_id, target_user_id, action, target_type, result, start, end, keyword)
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(f"SELECT count(*) FROM operation_log l{where}", params)
        total = (await cur.fetchone())[0]
        params.update({"limit": size, "offset": (page - 1) * size})
        cur = await conn.execute(
            f"{_SELECT}{where} ORDER BY l.log_id DESC LIMIT %(limit)s OFFSET %(offset)s",
            params,
        )
        rows = await cur.fetchall()
    return int(total), [_row(r) for r in rows]


async def list_for_export(**filters) -> list[dict]:
    where, params = _where(
        filters.get("actor_user_id"), filters.get("target_user_id"), filters.get("action"),
        filters.get("target_type"), filters.get("result"), filters.get("start"),
        filters.get("end"), filters.get("keyword"),
    )
    params["limit"] = 10000
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"{_SELECT}{where} ORDER BY l.log_id DESC LIMIT %(limit)s", params
        )
        rows = await cur.fetchall()
    return [_row(r) for r in rows]


def actions() -> list[dict]:
    return [{"action": k, "label": v} for k, v in ACTION_LABELS.items()]

