// 管理员用户全景只读接口（v5 R7）
import http from './http'

function clean(params = {}) {
  const out = {}
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) out[k] = v
  })
  return out
}

// GET /api/admin/users/{id}/overview —— 账号概览与使用汇总
export function fetchUserOverview(userId) {
  return http.get(`/admin/users/${userId}/overview`)
}

// GET /api/admin/users/{id}/qa —— 该用户问答轮次（含 trace_id）
export function fetchUserQa(userId, params) {
  return http.get(`/admin/users/${userId}/qa`, { params: clean(params) })
}

// GET /api/admin/users/{id}/sessions —— 该用户全部会话
export function fetchUserSessions(userId, params) {
  return http.get(`/admin/users/${userId}/sessions`, { params: clean(params) })
}

// GET /api/admin/users/{id}/sessions/{sid}/messages —— 只读消息
export function fetchUserMessages(userId, sessionId, params) {
  return http.get(`/admin/users/${userId}/sessions/${sessionId}/messages`, { params: clean(params) })
}

// GET /api/admin/users/{id}/documents —— 文档动作（按审计反查）
export function fetchUserDocuments(userId, params) {
  return http.get(`/admin/users/${userId}/documents`, { params: clean(params) })
}

// GET /api/admin/users/{id}/feedback —— 点赞/点踩记录
export function fetchUserFeedback(userId, params) {
  return http.get(`/admin/users/${userId}/feedback`, { params: clean(params) })
}

// GET /api/admin/users/{id}/activity —— 问答 + 审计的统一时间线
export function fetchUserActivity(userId, params) {
  return http.get(`/admin/users/${userId}/activity`, { params: clean(params) })
}
