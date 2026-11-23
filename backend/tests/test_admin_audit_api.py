"""v5 R6–R9 离线回归：删除语义、审计查询、用户全景权限与查看留痕去重。

全部用例走 `TestClient` + monkeypatch 仓储层，不依赖真实数据库。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.routers import user_io
from backend.services import account_store, admin_user_view, audit, io_log


def _user(role: str = "admin", user_id: int = 1) -> dict:
    return {
        "user_id": user_id,
        "username": "admin" if role == "admin" else "member",
        "display_name": "系统管理员" if role == "admin" else "普通成员",
        "role": role,
        "status": 1,
    }


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main.app)


def _login_as(monkeypatch, role: str = "admin", user_id: int = 1) -> dict:
    user = _user(role, user_id)

    async def fake_get_active_session(token_hash, renew_ttl_seconds=0):
        return user

    monkeypatch.setattr(account_store, "get_active_session", fake_get_active_session)
    return user


# ---------------------------------------------------------------- R6 删除语义
def test_delete_my_logs_is_soft_and_audited(client: TestClient, monkeypatch):
    """删除本人日志走软删除标记，并写 USER_LOG_DELETE 审计。"""
    user = _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")
    captured: list[dict] = []

    async def fake_delete(uid):
        assert uid == user["user_id"]
        return 7

    async def fake_audit(actor, action, ttype=None, tid=None, result=1, detail=None):
        captured.append({"actor": actor, "action": action, "detail": detail})

    monkeypatch.setattr(io_log, "delete_user_logs", fake_delete)
    monkeypatch.setattr(audit, "log_operation", fake_audit)

    resp = client.delete("/api/me/io-logs")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["removed"] == 7 and data["mode"] == "soft"
    assert captured and captured[-1]["action"] == audit.USER_LOG_DELETE
    assert captured[-1]["detail"]["mode"] == "soft"


def test_soft_deleted_logs_hidden_from_owner(monkeypatch):
    """`get_detail` 默认过滤软删除记录，管理端需显式 include_deleted。"""
    import inspect

    sig = inspect.signature(io_log.get_detail)
    assert sig.parameters["include_deleted"].default is False
    # 用户侧路由不传 include_deleted，等价于“删除后不可见”
    src = inspect.getsource(user_io.get_my_trace)
    assert "get_detail(trace_id)" in src


# ---------------------------------------------------------------- R8 审计查询
def test_audit_list_passes_filters_and_admin_only(client: TestClient, monkeypatch):
    user = _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")
    captured: dict = {}

    async def fake_list(**kwargs):
        captured.update(kwargs)
        return 3, [{"log_id": 1, "action": "DOC_DELETE", "action_label": "删除文档"}]

    monkeypatch.setattr(audit, "list_logs", fake_list)

    resp = client.get(
        "/api/admin/audit-logs?page=2&size=10&actor_user_id=1&target_user_id=2"
        "&action=DOC_DELETE&result=1&start=2026-11-01&end=2026-11-20&keyword=7"
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 3 and body["page"] == 2
    assert captured["actor_user_id"] == user["user_id"] and captured["target_user_id"] == 2
    assert captured["action"] == "DOC_DELETE" and captured["result"] == 1

    _login_as(monkeypatch, role="member")
    resp = client.get("/api/admin/audit-logs")
    assert resp.status_code == 403
    assert resp.json()["code"] == 40303


def test_audit_invalid_date_returns_40001(client: TestClient, monkeypatch):
    _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")
    resp = client.get("/api/admin/audit-logs?start=2026-13-01")
    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


def test_audit_actions_catalog(client: TestClient, monkeypatch):
    _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")
    resp = client.get("/api/admin/audit-logs/actions")
    assert resp.status_code == 200
    actions = {x["action"] for x in resp.json()["data"]["list"]}
    assert {audit.ADMIN_VIEW_USER_DATA, audit.USER_LOG_DELETE, audit.ADMIN_IO_EXPORT} <= actions


# ---------------------------------------------------------------- R7 用户全景
def test_user_overview_not_found(client: TestClient, monkeypatch):
    _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")

    async def none_overview(uid):
        return None

    monkeypatch.setattr(admin_user_view, "overview", none_overview)
    resp = client.get("/api/admin/users/99/overview")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40403

    _login_as(monkeypatch, role="member")
    resp = client.get("/api/admin/users/1/qa")
    assert resp.status_code == 403
    assert resp.json()["code"] == 40303


def test_user_session_messages_not_owned_returns_40402(client: TestClient, monkeypatch):
    _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")

    async def has_user(uid):
        return {"user_id": uid, "username": "u", "role": "member", "status": 1}

    async def not_owned(session_id, user_id):
        return None

    monkeypatch.setattr(account_store, "get_user_by_id", has_user)
    monkeypatch.setattr("backend.services.chat_store.get_session_for_user", not_owned)

    resp = client.get("/api/admin/users/2/sessions/55/messages")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40402


def test_user_qa_reuses_io_filters(client: TestClient, monkeypatch):
    _login_as(monkeypatch)
    client.cookies.set("rag_session", "test-token")
    captured: dict = {}

    async def has_user(uid):
        return {"user_id": uid, "username": "u", "role": "member", "status": 1}

    async def fake_list(**kwargs):
        captured.update(kwargs)
        return 2, []

    monkeypatch.setattr(account_store, "get_user_by_id", has_user)
    monkeypatch.setattr(io_log, "list_logs", fake_list)

    resp = client.get("/api/admin/users/2/qa?page=1&size=20&status=ok&keyword=退款")
    assert resp.status_code == 200
    assert captured["user_id"] == 2 and captured["status"] == "ok"
    assert captured["include_deleted"] is True
    assert resp.json()["data"]["total"] == 2


# ---------------------------------------------------------------- R9 查看留痕
def test_view_log_dedup_window():
    audit._VIEW_DEDUP.clear()
    assert audit.view_dedup_ok(1, "trace", "abc", 60) is True
    assert audit.view_dedup_ok(1, "trace", "abc", 60) is False
    # 不同管理员 / 不同对象互不影响
    assert audit.view_dedup_ok(2, "trace", "abc", 60) is True
    assert audit.view_dedup_ok(1, "trace", "def", 60) is True
    # 窗口为 0 时不去重
    assert audit.view_dedup_ok(1, "trace", "abc", 0) is True
    assert audit.view_dedup_ok(1, "trace", "abc", 0) is True


def test_admin_trace_view_logs_audit(client: TestClient, monkeypatch):
    """管理员查看他人链路写 ADMIN_VIEW_USER_DATA；查看自己的不写。"""
    admin = _login_as(monkeypatch, user_id=1)
    client.cookies.set("rag_session", "test-token")
    logged: list[dict] = []

    async def fake_detail(trace_id, include_deleted=False):
        return {"trace_id": trace_id, "user_id": 2, "query": "q"}

    async def fake_view(admin_user_id, target_user_id, scope, ref=None, detail=None, dedup_seconds=None):
        logged.append({"scope": scope, "ref": ref, "target": target_user_id})

    monkeypatch.setattr(io_log, "get_detail", fake_detail)
    monkeypatch.setattr(audit, "log_view", fake_view)

    resp = client.get("/api/admin/io-logs/trace-abc")
    assert resp.status_code == 200
    assert logged and logged[-1] == {"scope": "trace", "ref": "trace-abc", "target": 2}
    assert admin["user_id"] == 1
