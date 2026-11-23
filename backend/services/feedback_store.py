"""用户反馈与评测集存储（v3 / WP5-3）。

一条回答最多一条有效反馈：同一用户对同一 record 再次提交时做覆盖更新，
既允许用户改判，也保证评测集不会出现重复样本。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from ..db import get_pool

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chat_feedback (
  feedback_id       BIGSERIAL PRIMARY KEY,
  record_id         BIGINT       NOT NULL,
  session_id        BIGINT       NOT NULL,
  user_id           BIGINT       NOT NULL,
  trace_id          VARCHAR(32)  NULL,
  rating            SMALLINT     NOT NULL,
  reason_code       VARCHAR(32)  NULL,
  reason_text       VARCHAR(500) NULL,
  query_snapshot    TEXT         NULL,
  answer_snapshot   TEXT         NULL,
  intent            VARCHAR(32)  NULL,
  answer_mode       VARCHAR(16)  NULL,
  sources_json      JSONB        NULL,
  context_json      JSONB        NULL,
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE (record_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_rating_time ON chat_feedback (rating, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_user_time ON chat_feedback (user_id, created_at DESC);
"""


async def ensure_schema() -> None:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(_SCHEMA_SQL)


async def upsert_feedback(
    record_id: int,
    session_id: int,
    user_id: int,
    rating: int,
    reason_code: Optional[str],
    reason_text: Optional[str],
    trace_id: Optional[str],
    query_snapshot: Optional[str],
    answer_snapshot: Optional[str],
    intent: Optional[str],
    answer_mode: Optional[str],
    sources: Any,
    context_usage: Any,
) -> dict:
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO chat_feedback (
                    record_id, session_id, user_id, trace_id, rating,
                    reason_code, reason_text, query_snapshot, answer_snapshot,
                    intent, answer_mode, sources_json, context_json
                ) VALUES (
                    %(record_id)s, %(session_id)s, %(user_id)s, %(trace_id)s, %(rating)s,
                    %(reason_code)s, %(reason_text)s, %(query_snapshot)s, %(answer_snapshot)s,
                    %(intent)s, %(answer_mode)s, %(sources)s::jsonb, %(context)s::jsonb
                )
                ON CONFLICT (record_id, user_id) DO UPDATE SET
                    rating = EXCLUDED.rating,
                    reason_code = EXCLUDED.reason_code,
                    reason_text = EXCLUDED.reason_text,
                    trace_id = EXCLUDED.trace_id,
                    query_snapshot = EXCLUDED.query_snapshot,
                    answer_snapshot = EXCLUDED.answer_snapshot,
                    intent = EXCLUDED.intent,
                    answer_mode = EXCLUDED.answer_mode,
                    sources_json = EXCLUDED.sources_json,
                    context_json = EXCLUDED.context_json,
                    updated_at = now()
                RETURNING feedback_id, rating, reason_code, reason_text, updated_at
                """,
                {
                    "record_id": int(record_id),
                    "session_id": int(session_id),
                    "user_id": int(user_id),
                    "trace_id": trace_id,
                    "rating": int(rating),
                    "reason_code": reason_code,
                    "reason_text": (reason_text or "")[:500] or None,
                    "query_snapshot": query_snapshot,
                    "answer_snapshot": answer_snapshot,
                    "intent": intent,
                    "answer_mode": answer_mode,
                    "sources": json.dumps(sources, ensure_ascii=False) if sources is not None else "null",
                    "context": json.dumps(context_usage, ensure_ascii=False) if context_usage is not None else "null",
                },
            )
            row = await cur.fetchone()
            return {
                "feedback_id": int(row[0]),
                "rating": int(row[1]),
                "reason_code": row[2],
                "reason_text": row[3],
                "updated_at": row[4],
            }


async def list_feedback(
    rating: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
    user_id: Optional[int] = None,
) -> tuple[int, list[dict]]:
    pool = get_pool()
    clauses = []
    if rating is not None:
        clauses.append("rating = %(rating)s")
    # v5 R7：管理端按用户定位其反馈
    if user_id is not None:
        clauses.append("user_id = %(user_id)s")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params = {"rating": rating, "user_id": user_id, "lim": int(limit), "off": int(offset)}
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"SELECT count(*) FROM chat_feedback {where}", params)
            total = int((await cur.fetchone())[0])
            await cur.execute(
                f"""
                SELECT feedback_id, record_id, session_id, user_id, trace_id, rating,
                       reason_code, reason_text, query_snapshot, answer_snapshot,
                       intent, answer_mode, sources_json, context_json, created_at
                FROM chat_feedback {where}
                ORDER BY feedback_id DESC
                LIMIT %(lim)s OFFSET %(off)s
                """,
                params,
            )
            rows = await cur.fetchall()
            items = [
                {
                    "feedback_id": int(r[0]),
                    "record_id": int(r[1]),
                    "session_id": int(r[2]),
                    "user_id": int(r[3]),
                    "trace_id": r[4],
                    "rating": int(r[5]),
                    "reason_code": r[6],
                    "reason_text": r[7],
                    "query": r[8],
                    "answer": r[9],
                    "intent": r[10],
                    "answer_mode": r[11],
                    "sources": r[12] or [],
                    "context_usage": r[13] or {},
                    "created_at": r[14].isoformat() if isinstance(r[14], datetime) else r[14],
                }
                for r in rows
            ]
            return total, items


async def export_feedback() -> list[dict]:
    """导出全部反馈为可训练/可回放评测集；按 id 正序，便于增量消费。"""
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT feedback_id, record_id, session_id, user_id, trace_id, rating,
                       reason_code, reason_text, query_snapshot, answer_snapshot,
                       intent, answer_mode, sources_json, context_json, created_at
                FROM chat_feedback
                ORDER BY feedback_id ASC
                """
            )
            rows = await cur.fetchall()
            return [
                {
                    "feedback_id": int(r[0]),
                    "record_id": int(r[1]),
                    "session_id": int(r[2]),
                    "user_id": int(r[3]),
                    "trace_id": r[4],
                    "rating": int(r[5]),
                    "reason_code": r[6],
                    "reason_text": r[7],
                    "query": r[8],
                    "answer": r[9],
                    "intent": r[10],
                    "answer_mode": r[11],
                    "sources": r[12] or [],
                    "context_usage": r[13] or {},
                    "created_at": r[14].isoformat() if isinstance(r[14], datetime) else r[14],
                }
                for r in rows
            ]
