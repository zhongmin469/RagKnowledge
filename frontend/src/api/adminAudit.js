// 管理员操作审计接口（v5 R8）
import http from './http'

function clean(params = {}) {
  const out = {}
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) out[k] = v
  })
  return out
}

// GET /api/admin/audit-logs —— 分页查询
export function listAuditLogs(params) {
  return http.get('/admin/audit-logs', { params: clean(params) })
}

// GET /api/admin/audit-logs/actions —— 动作枚举
export function fetchAuditActions() {
  return http.get('/admin/audit-logs/actions')
}

// GET /api/admin/audit-logs/export —— 导出 CSV（返回可下载链接信息）
export function exportAuditLogs(params) {
  return http.get('/admin/audit-logs/export', { params: clean(params) })
}
