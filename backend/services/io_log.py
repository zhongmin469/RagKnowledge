"""输入输出运行日志（v3 / WP3）。

定位与边界：
- 这是**运行日志**，不是审计日志；`operation_log` 的"不记录聊天内容"约束不变，本模块单独建表。
- 日志不参与任何业务判断：读写失败只告警、不抛异常，删表也不影响问答。
- 写入走**有界队列 + 后台 worker**，问答主链路只做 `put_nowait`，日志绝不拖慢首字。
- `chat_io_log` 一轮一条（ok/abort/error/timeout/rejected），`llm_call_log` 一次调用一条。
- 保留期默认 90 天，可在配置中心调整；用户可导出/删除自己的日志。
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import re
import time
import uuid
from datetime import date, datetime
from typing import Any, Optional

from ..config import settings
from ..db import get_pool

logger = logging.getLogger("rag.io_log")

# 全链路 trace_id：中间件写入，LLM/工具/异常日志从此读取
_trace_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)
_user_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("log_user_id", default=None)

TURN_QUEUE_MAX = max(10, int(getattr(settings, "IO_LOG_QUEUE_MAX", 1000)))
QUEUE: asyncio.Queue | None = None
WORKER: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None
DROPPED = 0
WRITE_ERRORS = 0
_usage_by_trace: dict[str, dict] = {}

PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
ID_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+)")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    value = _trace_var.get()
    if not value:
        value = new_trace_id()
        _trace_var.set(value)
    return value


def set_trace_id(value: Optional[str]) -> contextvars.Token:
    return _trace_var.set(value)


def reset_trace_id(token: contextvars.Token) -> None:
    try:
        _trace_var.reset(token)
    except Exception:  # noqa: BLE001 - 上下文错配不应影响请求
        pass


def set_user_id(user_id: Optional[int]) -> None:
    """请求内标记当前用户，供 LLM 调用日志归属（导出/删除按用户闭环）。"""
    _user_var.set(user_id)


def get_user_id() -> Optional[int]:
    return _user_var.get()


def mask_text(text: Optional[str]) -> Optional[str]:
    """写入前脱敏手机号/身份证/邮箱；正文其余内容保留（排障必需，按保留期清理）。"""
    if not text:
        return text
    value = PHONE_RE.sub(lambda m: m.group(1)[:3] + "****" + m.group(1)[-4:], text)
    value = ID_RE.sub(lambda m: m.group(1)[:6] + "********" + m.group(1)[-4:], value)
    value = EMAIL_RE.sub(lambda m: m.group(1)[:2] + "***@" + m.group(2), value)
    return value


def mask_ip(ip: Optional[str]) -> Optional[str]:
    """IPv4 掩码为 123.45.*.*；IPv6 仅保留前两段。"""
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    if ":" in ip:
        seg = ip.split(":")
        return ":".join(seg[:2]) + ":****"
    return ip


_ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS chat_io_log (
  log_id            BIGSERIAL PRIMARY KEY,
  trace_id          VARCHAR(32)  NOT NULL,
  user_id           BIGINT       NULL,
  session_id        BIGINT       NULL,
  record_id         BIGINT       NULL,
  turn_index        INT          NULL,
  intent            VARCHAR(32)  NULL,
  answer_mode       VARCHAR(16)  NULL,
  query             TEXT         NOT NULL,
  query_rewritten   TEXT         NULL,
  rewrite_reason    VARCHAR(200) NULL,
  answer            TEXT         NULL,
  status            VARCHAR(16)  NOT NULL,
  error_code        VARCHAR(48)  NULL,
  error_msg         VARCHAR(512) NULL,
  model             VARCHAR(64)  NULL,
  prompt_tokens     INT          NULL,
  completion_tokens INT          NULL,
  total_tokens      INT          NULL,
  first_token_ms    INT          NULL,
  elapsed_ms        INT          NULL,
  frame_count       INT          NULL,
  tool_chain        JSONB        NULL,
  context_usage     JSONB        NULL,
  ua                VARCHAR(256) NULL,
  ip_masked         VARCHAR(64)  NULL,
  user_deleted_at   TIMESTAMP    NULL,
  created_at        TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_io_log_user_time ON chat_io_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_io_log_trace ON chat_io_log (trace_id);
CREATE INDEX IF NOT EXISTS idx_io_log_status ON chat_io_log (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_io_log_session ON chat_io_log (session_id);
ALTER TABLE chat_io_log ADD COLUMN IF NOT EXISTS query_rewritten TEXT NULL;
ALTER TABLE chat_io_log ADD COLUMN IF NOT EXISTS rewrite_reason VARCHAR(200) NULL;
ALTER TABLE chat_io_log ADD COLUMN IF NOT EXISTS user_deleted_at TIMESTAMP NULL;
CREATE INDEX IF NOT EXISTS idx_io_log_user_visible ON chat_io_log (user_id, user_deleted_at, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_call_log (
  call_id           BIGSERIAL PRIMARY KEY,
  trace_id          VARCHAR(32) NOT NULL,
  user_id           BIGINT      NULL,
  purpose           VARCHAR(24) NOT NULL,
  model             VARCHAR(64) NOT NULL,
  temperature       REAL        NULL,
  prompt_tokens     INT         NULL,
  completion_tokens INT         NULL,
  latency_ms        INT         NULL,
  status            VARCHAR(16) NOT NULL,
  error_code        VARCHAR(48) NULL,
  created_at        TIMESTAMP   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_llm_log_trace ON llm_call_log (trace_id);
CREATE INDEX IF NOT EXISTS idx_llm_log_purpose ON llm_call_log (purpose, created_at DESC);
"""


async def ensure_schema() -> None:
    """启动时幂等建表；数据库不可用只告警。"""
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(_ENSURE_SQL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("io 日志建表失败：%s", type(exc).__name__)


def _queue() -> asyncio.Queue:
    # 队列容量在进程启动时取配置快照（运行中改容量需重启，避免替换队列打断 worker）
    global QUEUE
    if QUEUE is None:
        QUEUE = asyncio.Queue(maxsize=TURN_QUEUE_MAX)
    return QUEUE


def _enabled() -> bool:
    """日志总开关（配置中心可在线关闭）；关闭后不写库、不影响问答。"""
    try:
        from . import app_config

        return bool(app_config.get_cached("IO_LOG_ENABLED"))
    except Exception:  # noqa: BLE001
        return bool(getattr(settings, "IO_LOG_ENABLED", True))


def _put(item: tuple[str, dict]) -> None:
    """真正入队；队满丢弃并计数，绝不抛给调用方。"""
    global DROPPED
    try:
        _queue().put_nowait(item)
    except asyncio.QueueFull:
        DROPPED += 1
        if DROPPED == 1 or DROPPED % 100 == 0:
            logger.warning("io 日志队列已满，丢弃 %d 条（不影响问答）", DROPPED)
    except Exception:  # noqa: BLE001
        DROPPED += 1


def _submit(item: tuple[str, dict]) -> None:
    """线程安全投递：llm.chat 在线程里调用，不能直接操作事件循环持有的 Queue。"""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if _loop is not None and running is not _loop:
        try:
            _loop.call_soon_threadsafe(_put, item)
            return
        except RuntimeError:
            pass
    _put(item)


def enqueue_turn(**fields: Any) -> None:
    """把一轮问答投递到队列；队满时丢弃并计数，绝不阻塞调用方。"""
    if not _enabled():
        return
    _submit(("turn", fields))


def enqueue_llm(**fields: Any) -> None:
    if not _enabled():
        return
    _submit(("llm", fields))


def note_llm_usage(trace_id: str, prompt_tokens: int | None, completion_tokens: int | None) -> None:
    """累计同一 trace 的 token 用量，供轮次记录汇总；无 usage 时保持 None。"""
    if prompt_tokens is None and completion_tokens is None:
        return
    item = _usage_by_trace.setdefault(trace_id, {"prompt": 0, "completion": 0, "seen": False})
    if not item["seen"]:
        item["seen"] = True
        item["prompt"] = 0
        item["completion"] = 0
    item["prompt"] += int(prompt_tokens or 0)
    item["completion"] += int(completion_tokens or 0)


def take_usage(trace_id: str) -> tuple[int | None, int | None]:
    item = _usage_by_trace.pop(trace_id, None)
    if not item or not item.get("seen"):
        return None, None
    return int(item["prompt"]), int(item["completion"])


async def _write_turn(conn, fields: dict) -> None:
    prompt_tokens = fields.get("prompt_tokens")
    completion_tokens = fields.get("completion_tokens")
    if prompt_tokens is None and completion_tokens is None:
        prompt_tokens, completion_tokens = take_usage(fields["trace_id"])
    total = None
    if prompt_tokens is not None or completion_tokens is not None:
        total = int(prompt_tokens or 0) + int(completion_tokens or 0)

    tool_chain = fields.get("tool_chain")
    context_usage = fields.get("context_usage")
    await conn.execute(
        """
        INSERT INTO chat_io_log (
            trace_id, user_id, session_id, record_id, turn_index, intent, answer_mode,
            query, query_rewritten, rewrite_reason, answer, status, error_code, error_msg, model,
            prompt_tokens, completion_tokens, total_tokens,
            first_token_ms, elapsed_ms, frame_count, tool_chain, context_usage,
            ua, ip_masked
        ) VALUES (
            %(trace_id)s, %(user_id)s, %(session_id)s, %(record_id)s, %(turn_index)s, %(intent)s, %(answer_mode)s,
            %(query)s, %(query_rewritten)s, %(rewrite_reason)s, %(answer)s, %(status)s, %(error_code)s, %(error_msg)s, %(model)s,
            %(prompt_tokens)s, %(completion_tokens)s, %(total_tokens)s,
            %(first_token_ms)s, %(elapsed_ms)s, %(frame_count)s,
            %(tool_chain)s::jsonb, %(context_usage)s::jsonb,
            %(ua)s, %(ip_masked)s
        )
        """,
        {
            "trace_id": fields["trace_id"],
            "user_id": fields.get("user_id"),
            "session_id": fields.get("session_id"),
            "record_id": fields.get("record_id"),
            "turn_index": fields.get("turn_index"),
            "intent": fields.get("intent"),
            "answer_mode": fields.get("answer_mode"),
            "query": mask_text(fields.get("query") or ""),
            "query_rewritten": fields.get("query_rewritten"),
            "rewrite_reason": (fields.get("rewrite_reason") or None),
            "answer": mask_text(fields.get("answer")),
            "status": fields.get("status") or "ok",
            "error_code": fields.get("error_code"),
            "error_msg": (fields.get("error_msg") or None),
            "model": fields.get("model") or settings.LLM_MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
            "first_token_ms": fields.get("first_token_ms"),
            "elapsed_ms": fields.get("elapsed_ms"),
            "frame_count": fields.get("frame_count"),
            "tool_chain": json.dumps(tool_chain, ensure_ascii=False, default=str) if tool_chain else None,
            "context_usage": json.dumps(context_usage, ensure_ascii=False, default=str) if context_usage else None,
            "ua": (fields.get("ua") or "")[:256] or None,
            "ip_masked": mask_ip(fields.get("ip")),
        },
    )


async def _write_llm(conn, fields: dict) -> None:
    await conn.execute(
        """
        INSERT INTO llm_call_log (
            trace_id, user_id, purpose, model, temperature,
            prompt_tokens, completion_tokens, latency_ms, status, error_code
        ) VALUES (
            %(trace_id)s, %(user_id)s, %(purpose)s, %(model)s, %(temperature)s,
            %(prompt_tokens)s, %(completion_tokens)s, %(latency_ms)s, %(status)s, %(error_code)s
        )
        """,
        {
            "trace_id": fields["trace_id"],
            "user_id": fields.get("user_id") if fields.get("user_id") is not None else get_user_id(),
            "purpose": fields.get("purpose") or "answer",
            "model": fields.get("model") or settings.LLM_MODEL,
            "temperature": fields.get("temperature"),
            "prompt_tokens": fields.get("prompt_tokens"),
            "completion_tokens": fields.get("completion_tokens"),
            "latency_ms": fields.get("latency_ms"),
            "status": fields.get("status") or "ok",
            "error_code": fields.get("error_code"),
        },
    )


async def _writer_loop() -> None:
    """后台批量写库；单条失败只告警，队列继续消费。"""
    global WRITE_ERRORS
    while True:
        kind, fields = await _queue().get()
        batch: list[tuple[str, dict]] = [(kind, fields)]
        # 小批量聚合，降低连接开销；队列空则立即落盘，保证详情能马上查到
        while len(batch) < 20:
            try:
                batch.append(_queue().get_nowait())
            except asyncio.QueueEmpty:
                break
        try:
            pool = get_pool()
            async with pool.connection() as conn:
                for item_kind, item in batch:
                    try:
                        async with conn.transaction():
                            if item_kind == "llm":
                                await _write_llm(conn, item)
                            else:
                                await _write_turn(conn, item)
                    except Exception:  # noqa: BLE001
                        WRITE_ERRORS += 1
                        logger.warning("io 日志写入失败 kind=%s（不影响问答）", item_kind, exc_info=True)
        except Exception:  # noqa: BLE001
            WRITE_ERRORS += len(batch)
            logger.warning("io 日志批次写入失败（不影响问答）", exc_info=True)
        finally:
            for _ in batch:
                _queue().task_done()


def start_worker() -> None:
    global WORKER, _loop
    if WORKER is None or WORKER.done():
        _loop = asyncio.get_running_loop()
        WORKER = asyncio.create_task(_writer_loop())


async def stop_worker() -> None:
    """关闭前尽力清空队列；最多等 2 秒，避免拖住进程退出。"""
    global WORKER
    if WORKER is None:
        return
    try:
        await asyncio.wait_for(_queue().join(), timeout=2.0)
    except Exception:  # noqa: BLE001
        pass
    WORKER.cancel()
    try:
        await WORKER
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
    WORKER = None


def health() -> dict:
    return {
        "enabled": _enabled(),
        "queue_size": _queue().qsize() if QUEUE else 0,
        "dropped": DROPPED,
        "write_errors": WRITE_ERRORS,
    }


# ---------------------------------------------------------------- 查询/导出/清理
def _filters(
    user_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    answer_mode: Optional[str] = None,
    keyword: Optional[str] = None,
    trace_id: Optional[str] = None,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    # v5 R6：用户主动删除只做软删除；用户侧默认不可见，管理端显式 include_deleted 才可见
    if only_deleted:
        clauses.append("user_deleted_at IS NOT NULL")
    elif not include_deleted:
        clauses.append("user_deleted_at IS NULL")
    if user_id is not None:
        clauses.append("user_id = %(user_id)s")
        params["user_id"] = int(user_id)
    if start:
        clauses.append("created_at >= %(start)s::timestamp")
        params["start"] = start
    if end:
        # 传日期时包含当天：转成次日 00:00 之前
        if len(end) == 10:
            clauses.append("created_at < (%(end)s::date + 1)")
        else:
            clauses.append("created_at <= %(end)s::timestamp")
        params["end"] = end
    if status:
        clauses.append("status = %(status)s")
        params["status"] = status
    if intent:
        clauses.append("intent = %(intent)s")
        params["intent"] = intent
    if answer_mode:
        clauses.append("answer_mode = %(answer_mode)s")
        params["answer_mode"] = answer_mode
    if trace_id:
        clauses.append("trace_id = %(trace_id)s")
        params["trace_id"] = trace_id
    if keyword:
        clauses.append("query ILIKE %(keyword)s")
        params["keyword"] = f"%{keyword}%"
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _row_to_dict(row) -> dict:
    keys = [
        "log_id", "trace_id", "user_id", "session_id", "record_id", "turn_index",
        "intent", "answer_mode", "query", "query_rewritten", "rewrite_reason", "answer", "status", "error_code", "error_msg",
        "model", "prompt_tokens", "completion_tokens", "total_tokens", "first_token_ms",
        "elapsed_ms", "frame_count", "tool_chain", "context_usage", "ua", "ip_masked",
        "user_deleted_at", "created_at",
    ]
    item = dict(zip(keys, row))
    for key in ("created_at", "user_deleted_at"):
        if isinstance(item.get(key), (datetime, date)):
            item[key] = item[key].isoformat(sep=" ")
    item["user_deleted"] = item.get("user_deleted_at") is not None
    return item


async def list_logs(
    user_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    intent: Optional[str] = None,
    answer_mode: Optional[str] = None,
    keyword: Optional[str] = None,
    trace_id: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> tuple[int, list[dict]]:
    where, params = _filters(
        user_id, start, end, status, intent, answer_mode, keyword, trace_id,
        include_deleted=include_deleted, only_deleted=only_deleted,
    )
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(f"SELECT count(*) FROM chat_io_log{where}", params)
        total = (await cur.fetchone())[0]
        params.update({"limit": size, "offset": (page - 1) * size})
        cur = await conn.execute(
            f"""
            SELECT log_id, trace_id, user_id, session_id, record_id, turn_index,
                   intent, answer_mode, query, query_rewritten, rewrite_reason, answer, status, error_code, error_msg,
                   model, prompt_tokens, completion_tokens, total_tokens, first_token_ms,
                   elapsed_ms, frame_count, tool_chain, context_usage, ua, ip_masked, user_deleted_at, created_at
            FROM chat_io_log{where}
            ORDER BY log_id DESC LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        rows = await cur.fetchall()
    return int(total), [_row_to_dict(r) for r in rows]


async def get_detail(trace_id: str, include_deleted: bool = False) -> Optional[dict]:
    where = "trace_id = %(trace)s"
    if not include_deleted:
        where += " AND user_deleted_at IS NULL"
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT log_id, trace_id, user_id, session_id, record_id, turn_index,
                   intent, answer_mode, query, query_rewritten, rewrite_reason, answer, status, error_code, error_msg,
                   model, prompt_tokens, completion_tokens, total_tokens, first_token_ms,
                   elapsed_ms, frame_count, tool_chain, context_usage, ua, ip_masked, user_deleted_at, created_at
            FROM chat_io_log WHERE {where} ORDER BY log_id DESC LIMIT 1
            """,
            {"trace": trace_id},
        )
        row = await cur.fetchone()
        if row is None:
            return None
        turn = _row_to_dict(row)
        cur = await conn.execute(
            """
            SELECT call_id, purpose, model, temperature, prompt_tokens, completion_tokens,
                   latency_ms, status, error_code, created_at
            FROM llm_call_log WHERE trace_id = %(trace)s ORDER BY call_id
            """,
            {"trace": trace_id},
        )
        calls = await cur.fetchall()
    turn["llm_calls"] = [
        {
            "call_id": c[0], "purpose": c[1], "model": c[2], "temperature": c[3],
            "prompt_tokens": c[4], "completion_tokens": c[5], "latency_ms": c[6],
            "status": c[7], "error_code": c[8],
            "created_at": c[9].isoformat(sep=" ") if isinstance(c[9], (datetime, date)) else c[9],
        }
        for c in calls
    ]
    return turn


async def stats() -> dict:
    """概览：今日请求数/成功率/P95 首字/token 消耗/各链路占比。"""
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE status = 'ok'),
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY first_token_ms)
                     FILTER (WHERE first_token_ms IS NOT NULL),
                   coalesce(sum(total_tokens), 0)
            FROM chat_io_log WHERE created_at >= date_trunc('day', now())
            """
        )
        total, ok_count, p95, tokens = await cur.fetchone()
        cur = await conn.execute(
            """
            SELECT coalesce(intent, 'unknown'), count(*)
            FROM chat_io_log WHERE created_at >= date_trunc('day', now())
            GROUP BY 1 ORDER BY 2 DESC
            """
        )
        intent_rows = await cur.fetchall()
        cur = await conn.execute(
            """
            SELECT coalesce(answer_mode, 'unknown'), count(*)
            FROM chat_io_log WHERE created_at >= date_trunc('day', now())
            GROUP BY 1 ORDER BY 2 DESC
            """
        )
        mode_rows = await cur.fetchall()
    return {
        "today_total": int(total or 0),
        "today_ok": int(ok_count or 0),
        "success_rate": round((int(ok_count or 0) / total) * 100, 1) if total else 0.0,
        "p95_first_token_ms": int(p95) if p95 is not None else None,
        "today_tokens": int(tokens or 0),
        "intent_share": [{"intent": r[0], "count": int(r[1])} for r in intent_rows],
        "mode_share": [{"answer_mode": r[0], "count": int(r[1])} for r in mode_rows],
    }


async def list_for_export(**filters) -> list[dict]:
    """导出用：同样筛选条件，上限 10000 行。"""
    where, params = _filters(
        filters.get("user_id"), filters.get("start"), filters.get("end"),
        filters.get("status"), filters.get("intent"), filters.get("answer_mode"),
        filters.get("keyword"), filters.get("trace_id"),
        include_deleted=bool(filters.get("include_deleted")),
        only_deleted=bool(filters.get("only_deleted")),
    )
    params["limit"] = 10000
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT created_at, trace_id, user_id, session_id, intent, answer_mode, status,
                   elapsed_ms, first_token_ms, total_tokens, query, answer
            FROM chat_io_log{where}
            ORDER BY log_id DESC LIMIT %(limit)s
            """,
            params,
        )
        return await cur.fetchall()


async def user_export(user_id: int) -> list[dict]:
    _, rows = await list_logs(user_id=user_id, page=1, size=10000)
    return rows


async def delete_user_logs(user_id: int) -> int:
    """v5 R6：标记本人日志为“已从用户视角删除”（软删除），返回新标记条数。

    - 用户侧读取默认过滤 `user_deleted_at IS NULL`，因此删除后本人不可见、不可导出；
    - 管理端仍可在保留期内查看这批记录（审计与排障要求）；
    - 保留期到期由 cleanup_expired 物理清除。
    """
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                """
                UPDATE chat_io_log SET user_deleted_at = now()
                WHERE user_id = %(uid)s AND user_deleted_at IS NULL
                """,
                {"uid": int(user_id)},
            )
            removed = cur.rowcount or 0
    return int(removed)


async def delete_session_logs(session_id: int) -> int:
    """v5 R6：删除会话时同样改为软删除，避免管理端链路断档。"""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                """
                UPDATE chat_io_log SET user_deleted_at = now()
                WHERE session_id = %(sid)s AND user_deleted_at IS NULL
                """,
                {"sid": int(session_id)},
            )
            return int(cur.rowcount or 0)


async def cleanup_expired(retention_days: Optional[int] = None) -> int:
    """按保留期物理删除过期轮次与调用日志；返回删除条数。"""
    days = retention_days
    if days is None:
        try:
            from . import app_config

            days = int(app_config.get_cached("IO_LOG_RETENTION_DAYS"))
        except Exception:  # noqa: BLE001
            days = int(getattr(settings, "IO_LOG_RETENTION_DAYS", 90))
    days = max(1, int(days))
    pool = get_pool()
    try:
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    "DELETE FROM chat_io_log WHERE created_at < now() - (%(days)s || ' days')::interval",
                    {"days": days},
                )
                removed = int(cur.rowcount or 0)
                await conn.execute(
                    "DELETE FROM llm_call_log WHERE created_at < now() - (%(days)s || ' days')::interval",
                    {"days": days},
                )
        if removed:
            logger.info("已清理过期 I/O 日志 %d 条（保留 %d 天）", removed, days)
        return removed
    except Exception as exc:  # noqa: BLE001
        logger.warning("I/O 日志清理失败：%s", type(exc).__name__)
        return 0


CLEANUP_INTERVAL_SECONDS = 24 * 3600


async def cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            await cleanup_expired()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("I/O 日志清理循环异常：%s", type(exc).__name__)
