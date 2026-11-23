"""管理员按用户维度的只读查询（v5 R7）。

所有函数都以 `user_id` 为目标账号，**不做写操作**；权限校验在路由层 `require_admin`。
说明：
- 问答与链路复用 `chat_io_log`（`io_log.list_logs`），默认包含用户已软删除的记录；
- 知识库为共享库，`document` 表没有上传者字段，故“某用户的文档”按 `operation_log` 的
  `DOC_*` 动作反查，口径在 UI 上注明“按审计反推”。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from ..db import get_pool
from . import chat_store, io_log

DOC_ACTIONS = ("DOC_UPLOAD", "DOC_DELETE", "DOC_DOWNLOAD", "REPARSE")


def _ts(value: Any) -> Any:
    return value.isoformat(sep=" ") if isinstance(value, (datetime, date)) else value


async def _fetch(conn, sql: str, params: dict) -> list[dict]:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in await cur.fetchall()]


async def _count(conn, sql: str, params: dict) -> int:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        return int((await cur.fetchone())[0])


async def overview(user_id: int) -> dict | None:
    """账号概览：账号信息 + 会话/问答/文档/反馈/token 汇总。"""
    pool = get_pool()
    async with pool.connection() as conn:
        users = await _fetch(
            conn,
            """
            SELECT user_id, username, display_name, role, status, created_at, last_login_at
            FROM app_user WHERE user_id = %(uid)s
            """,
            {"uid": int(user_id)},
        )
        if not users:
            return None
        base = users[0]
        sessions = await _count(
            conn, "SELECT count(*) FROM chat_session WHERE user_id = %(uid)s", {"uid": int(user_id)}
        )
        qa_row = await _fetch(
            conn,
            """
            SELECT count(*) AS qa_total,
                   count(*) FILTER (WHERE user_deleted_at IS NOT NULL) AS deleted_total,
                   count(*) FILTER (WHERE created_at >= now() - interval '7 days') AS qa_7d,
                   count(*) FILTER (WHERE created_at >= now() - interval '30 days') AS qa_30d,
                   coalesce(sum(total_tokens), 0) AS tokens,
                   max(created_at) AS last_qa_at
            FROM chat_io_log WHERE user_id = %(uid)s
            """,
            {"uid": int(user_id)},
        )
        qa = qa_row[0]
        feedback_total = await _count(
            conn, "SELECT count(*) FROM chat_feedback WHERE user_id = %(uid)s", {"uid": int(user_id)}
        )
        docs = await _fetch(
            conn,
            """
            SELECT count(DISTINCT target_id) AS doc_total
            FROM operation_log
            WHERE actor_user_id = %(uid)s AND action = 'DOC_UPLOAD' AND result = 1
              AND target_id IS NOT NULL
            """,
            {"uid": int(user_id)},
        )
        audits = await _count(
            conn, "SELECT count(*) FROM operation_log WHERE actor_user_id = %(uid)s", {"uid": int(user_id)}
        )
        viewed_by = await _count(
            conn,
            """
            SELECT count(*) FROM operation_log
            WHERE action = 'ADMIN_VIEW_USER_DATA' AND target_type = 'user' AND target_id = %(tid)s
            """,
            {"tid": str(int(user_id))},
        )
    return {
        "user_id": int(base["user_id"]),
        "username": base["username"],
        "display_name": base["display_name"],
        "role": base["role"],
        "status": base["status"],
        "created_at": _ts(base["created_at"]),
        "last_login_at": _ts(base["last_login_at"]),
        "session_total": sessions,
        "qa_total": int(qa["qa_total"] or 0),
        "qa_7d": int(qa["qa_7d"] or 0),
        "qa_30d": int(qa["qa_30d"] or 0),
        "qa_deleted": int(qa["deleted_total"] or 0),
        "total_tokens": int(qa["tokens"] or 0),
        "last_qa_at": _ts(qa["last_qa_at"]),
        "document_total": int((docs[0]["doc_total"] if docs else 0) or 0),
        "feedback_total": feedback_total,
        "audit_total": audits,
        "viewed_by_admin": viewed_by,
    }


async def qa(
    user_id: int,
    page: int = 1,
    size: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    keyword: Optional[str] = None,
    include_deleted: bool = True,
) -> tuple[int, list[dict]]:
    """该用户的问答轮次（含用户已删除记录，由前端标注）。"""
    return await io_log.list_logs(
        user_id=int(user_id),
        start=start,
        end=end,
        status=status,
        intent=intent,
        keyword=keyword,
        page=page,
        size=size,
        include_deleted=include_deleted,
    )


async def sessions(
    user_id: int,
    page: int = 1,
    size: int = 20,
    keyword: Optional[str] = None,
    archived: Optional[bool] = None,
) -> tuple[int, list[dict]]:
    """该用户全部会话（archived=None 表示含归档）。"""
    params: dict = {"uid": int(user_id), "lim": size, "off": (page - 1) * size}
    clauses = ["s.user_id = %(uid)s"]
    if archived is True:
        clauses.append("s.archived_at IS NOT NULL")
    elif archived is False:
        clauses.append("s.archived_at IS NULL")
    if keyword:
        clauses.append("s.session_name ILIKE %(kw)s")
        params["kw"] = f"%{keyword}%"
    where = " AND ".join(clauses)
    pool = get_pool()
    async with pool.connection() as conn:
        total = await _count(conn, f"SELECT count(*) FROM chat_session s WHERE {where}", params)
        rows = await _fetch(
            conn,
            f"""
            SELECT s.session_id, s.session_name, s.create_time, s.last_active_at,
                   s.is_pinned, s.archived_at,
                   (SELECT count(*) FROM chat_record r WHERE r.session_id = s.session_id) AS record_count
            FROM chat_session s
            WHERE {where}
            ORDER BY COALESCE(s.last_active_at, s.create_time) DESC, s.session_id DESC
            LIMIT %(lim)s OFFSET %(off)s
            """,
            params,
        )
    for r in rows:
        r["session_id"] = int(r["session_id"])
        r["record_count"] = int(r["record_count"] or 0)
        r["is_pinned"] = bool(r["is_pinned"])
        for key in ("create_time", "last_active_at", "archived_at"):
            r[key] = _ts(r.get(key))
    return total, rows


async def messages(user_id: int, session_id: int, page: int = 1, size: int = 30) -> tuple[int, list[dict]] | None:
    """该用户某会话的只读消息；会话不属于该用户返回 None。"""
    owned = await chat_store.get_session_for_user(int(session_id), int(user_id))
    if owned is None:
        return None
    return await chat_store.list_records(int(session_id), limit=size, offset=(page - 1) * size)


async def documents(
    user_id: int,
    page: int = 1,
    size: int = 20,
    action: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> tuple[int, list[dict]]:
    """该用户发起的文档动作（上传/删除/下载/重解析），知识库无 owner 字段故按审计反查。"""
    params: dict = {"uid": int(user_id), "lim": size, "off": (page - 1) * size}
    clauses = ["actor_user_id = %(uid)s", "action = ANY(%(actions)s)"]
    params["actions"] = list(DOC_ACTIONS)
    if action:
        clauses = ["actor_user_id = %(uid)s", "action = %(action)s"]
        params["action"] = action
    if start:
        clauses.append("created_at >= %(start)s::timestamp")
        params["start"] = start
    if end:
        if len(end) == 10:
            clauses.append("created_at < (%(end)s::date + 1)")
        else:
            clauses.append("created_at <= %(end)s::timestamp")
        params["end"] = end
    where = " AND ".join(clauses)
    pool = get_pool()
    async with pool.connection() as conn:
        total = await _count(conn, f"SELECT count(*) FROM operation_log WHERE {where}", params)
        rows = await _fetch(
            conn,
            f"""
            SELECT log_id, created_at, action, target_id, result, detail
            FROM operation_log
            WHERE {where}
            ORDER BY log_id DESC LIMIT %(lim)s OFFSET %(off)s
            """,
            params,
        )
    for r in rows:
        r["created_at"] = _ts(r.get("created_at"))
    return total, rows


async def feedback(
    user_id: int,
    page: int = 1,
    size: int = 20,
    rating: Optional[int] = None,
) -> tuple[int, list[dict]]:
    params: dict = {"uid": int(user_id), "lim": size, "off": (page - 1) * size}
    clauses = ["user_id = %(uid)s"]
    if rating in (1, -1):
        clauses.append("rating = %(rating)s")
        params["rating"] = int(rating)
    where = " AND ".join(clauses)
    pool = get_pool()
    async with pool.connection() as conn:
        total = await _count(conn, f"SELECT count(*) FROM chat_feedback WHERE {where}", params)
        rows = await _fetch(
            conn,
            f"""
            SELECT feedback_id, record_id, session_id, trace_id, rating, reason_code, reason_text,
                   query_snapshot, answer_snapshot, intent, answer_mode, created_at
            FROM chat_feedback
            WHERE {where}
            ORDER BY feedback_id DESC LIMIT %(lim)s OFFSET %(off)s
            """,
            params,
        )
    for r in rows:
        r["created_at"] = _ts(r.get("created_at"))
    return total, rows


async def activity(
    user_id: int,
    page: int = 1,
    size: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    type_: Optional[str] = None,
) -> tuple[int, list[dict]]:
    """统一时间流：问答轮次 + 操作审计（登录/文档/导出/管理动作等）。

    type_: qa / login / doc / export / admin / other，为空表示全部。
    """
    conds: list[str] = []
    ts_conds: list[str] = []
    if start:
        ts_conds.append("created_at >= %(start)s::timestamp")
    if end:
        ts_conds.append("created_at < (%(end)s::date + 1)" if len(end) == 10
                        else "created_at <= %(end)s::timestamp")
    qa_enabled = type_ is None or type_ == "qa"
    audit_enabled = type_ != "qa"
    audit_clause = ""
    if audit_enabled and type_ in {"login", "doc", "export", "admin"}:
        if type_ == "login":
            audit_clause = " AND action = 'AUTH_LOGIN'"
        elif type_ == "doc":
            audit_clause = " AND action = ANY('{%s}'::text[])" % ",".join(DOC_ACTIONS)
        elif type_ == "export":
            audit_clause = " AND action IN ('BIZ_EXPORT', 'USER_LOG_EXPORT', 'ADMIN_IO_EXPORT', 'AUDIT_EXPORT', 'FEEDBACK_EXPORT')"
        else:
            audit_clause = " AND action IN ('USER_MANAGE', 'CONFIG_UPDATE', 'SESSION_DELETE', 'SESSION_DELETE_BATCH', 'USER_LOG_DELETE', 'ADMIN_VIEW_USER_DATA')"

    parts: list[str] = []
    params: dict = {"uid": int(user_id)}
    if qa_enabled:
        extra = "".join(f" AND {c}" for c in ts_conds)
        parts.append(
            "SELECT created_at AS ts, 'qa' AS type, coalesce(intent, '') AS title, "
            "coalesce(query, '') AS detail, trace_id AS ref_id, status AS result "
            "FROM chat_io_log WHERE user_id = %(uid)s" + extra
        )
    if audit_enabled:
        extra = "".join(f" AND {c}" for c in ts_conds)
        parts.append(
            "SELECT created_at AS ts, CASE "
            "WHEN action = 'AUTH_LOGIN' THEN 'login' "
            "WHEN action IN ('DOC_UPLOAD','DOC_DELETE','DOC_DOWNLOAD','REPARSE') THEN 'doc' "
            "WHEN action LIKE '%%EXPORT%%' OR action = 'BIZ_EXPORT' THEN 'export' "
            "WHEN action IN ('USER_MANAGE','CONFIG_UPDATE','SESSION_DELETE','SESSION_DELETE_BATCH',"
            "'USER_LOG_DELETE','ADMIN_VIEW_USER_DATA') THEN 'admin' ELSE 'other' END AS type, "
            "action AS title, coalesce(target_id, '') AS detail, NULL AS ref_id, "
            "CASE WHEN result = 1 THEN 'ok' ELSE 'error' END AS result "
            "FROM operation_log WHERE actor_user_id = %(uid)s" + extra + audit_clause
        )
    if not parts:
        return 0, []
    union_sql = " UNION ALL ".join(parts)
    pool = get_pool()
    async with pool.connection() as conn:
        total = await _count(conn, f"SELECT count(*) FROM ({union_sql}) t", params)
        params.update({"lim": size, "off": (page - 1) * size})
        rows = await _fetch(
            conn,
            f"""
            SELECT ts, type, title, detail, ref_id, result
            FROM ({union_sql}) t
            ORDER BY ts DESC
            LIMIT %(lim)s OFFSET %(off)s
            """,
            params,
        )
    for r in rows:
        r["ts"] = _ts(r.get("ts"))
    return total, rows
