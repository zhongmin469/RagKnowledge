<script setup>
// 管理端操作审计页（v5 R8）：按操作人/被操作用户/动作/结果/时间/关键词查询，支持导出。
// 审计只读：本页与接口层都不提供删除或清空。
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAuditLogs, fetchAuditActions, exportAuditLogs } from '../api/adminAudit'

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = 20
const actions = ref([])
const exporting = ref(false)
const expanded = ref({})

const filters = reactive({
  actor_user_id: '',
  target_user_id: '',
  action: '',
  target_type: '',
  result: '',
  keyword: '',
  range: []
})

function rangeParams() {
  const [start, end] = filters.range || []
  return { start: start || '', end: end || '' }
}

function params(p = 1) {
  return {
    page: p,
    size,
    actor_user_id: filters.actor_user_id === '' ? '' : Number(filters.actor_user_id),
    target_user_id: filters.target_user_id === '' ? '' : Number(filters.target_user_id),
    action: filters.action,
    target_type: filters.target_type,
    result: filters.result === '' ? '' : Number(filters.result),
    keyword: filters.keyword.trim(),
    ...rangeParams()
  }
}

function fmtTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 19)
}

function actionLabel(row) {
  return row.action_label || actions.value.find((a) => a.action === row.action)?.label || row.action
}

function toggleDetail(row) {
  expanded.value = { ...expanded.value, [row.log_id]: !expanded.value[row.log_id] }
}

function detailText(row) {
  if (!row.detail) return '—'
  try {
    return JSON.stringify(row.detail, null, 2)
  } catch {
    return String(row.detail)
  }
}

async function refresh(p = page.value) {
  loading.value = true
  try {
    const data = await listAuditLogs(params(p))
    rows.value = data?.list || []
    total.value = data?.total || 0
    page.value = p
    expanded.value = {}
  } catch (e) {
    ElMessage.error(e?.message || '审计记录加载失败')
  } finally {
    loading.value = false
  }
}

async function onExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    const info = await exportAuditLogs(params(1))
    if (info?.url) {
      window.open(info.url, '_blank')
      ElMessage.success(`已生成 ${info.rows} 行 CSV${info.capped ? '（已达 1 万行上限）' : ''}`)
    }
  } catch {
    // 统一拦截器提示
  } finally {
    exporting.value = false
  }
}

function resetFilters() {
  filters.actor_user_id = ''
  filters.target_user_id = ''
  filters.action = ''
  filters.target_type = ''
  filters.result = ''
  filters.keyword = ''
  filters.range = []
  refresh(1)
}

onMounted(async () => {
  try {
    const data = await fetchAuditActions()
    actions.value = data?.list || []
  } catch {
    actions.value = []
  }
  refresh(1)
})

const actionCount = computed(() => actions.value.length)
</script>

<template>
  <el-card>
    <template #header>
      <div class="page-head">
        <span>操作审计</span>
        <div class="head-ops">
          <el-tag type="info" size="small">共 {{ total }} 条 · {{ actionCount }} 类动作</el-tag>
          <el-button type="primary" size="small" :loading="exporting" @click="onExport">导出 CSV</el-button>
        </div>
      </div>
    </template>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计记录只增不删，覆盖登录、文档操作、导出、账号管理与“管理员查看他人数据”。不记录聊天正文。"
      class="tip"
    />

    <div class="toolbar">
      <el-input v-model="filters.actor_user_id" size="small" clearable placeholder="操作人 ID" class="f-num" />
      <el-input v-model="filters.target_user_id" size="small" clearable placeholder="被操作用户 ID" class="f-num" />
      <el-select v-model="filters.action" size="small" clearable filterable placeholder="全部动作" class="f-select">
        <el-option v-for="a in actions" :key="a.action" :label="a.label" :value="a.action" />
      </el-select>
      <el-select v-model="filters.result" size="small" clearable placeholder="结果" class="f-small">
        <el-option label="成功" :value="1" />
        <el-option label="失败" :value="0" />
      </el-select>
      <el-date-picker
        v-model="filters.range"
        size="small"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        class="f-date"
      />
      <el-input
        v-model="filters.keyword"
        size="small"
        clearable
        placeholder="对象 ID / 详情关键词"
        class="f-input"
        @keyup.enter="refresh(1)"
      />
      <el-button size="small" type="primary" @click="refresh(1)">查询</el-button>
      <el-button size="small" @click="resetFilters">重置</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" size="small" class="table">
      <el-table-column label="时间" width="150">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作人" width="150">
        <template #default="{ row }">
          <span v-if="row.actor_user_id">{{ row.actor_username || '—' }}（{{ row.actor_user_id }}）</span>
          <span v-else class="muted">未识别</span>
        </template>
      </el-table-column>
      <el-table-column label="动作" min-width="150">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ actionLabel(row) }}</el-tag>
          <div class="action-code">{{ row.action }}</div>
        </template>
      </el-table-column>
      <el-table-column label="对象" min-width="150">
        <template #default="{ row }">
          <span class="muted">{{ row.target_type || '—' }}</span>
          <span class="obj-id">{{ row.target_id || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结果" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.result === 1 ? 'success' : 'danger'">
            {{ row.result === 1 ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="详情" width="80">
        <template #default="{ row }">
          <el-button link size="small" :disabled="!row.detail" @click="toggleDetail(row)">
            {{ expanded[row.log_id] ? '收起' : '展开' }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="当前筛选没有审计记录" :image-size="60" />
      </template>
    </el-table>

    <div v-for="row in rows" :key="`d-${row.log_id}`" class="detail-block" v-show="expanded[row.log_id]">
      <div class="detail-head">#{{ row.log_id }} · {{ fmtTime(row.created_at) }} · {{ row.action }}</div>
      <pre class="detail-body">{{ detailText(row) }}</pre>
    </div>

    <div class="pager" v-if="total > size">
      <el-pagination
        size="small"
        layout="prev, pager, next, total"
        :total="total"
        :page-size="size"
        :current-page="page"
        @current-change="refresh"
      />
    </div>
  </el-card>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; }
.head-ops { display: flex; align-items: center; gap: 10px; }
.tip { margin-bottom: 12px; }
.toolbar { display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.f-num { width: 120px; }
.f-select { width: 170px; }
.f-small { width: 100px; }
.f-date { width: 250px; }
.f-input { width: 200px; }
.table { width: 100%; }
.action-code { font-size: 11px; color: var(--text-secondary); }
.obj-id { margin-left: 6px; }
.muted { color: var(--text-secondary); }
.detail-block { margin-top: 8px; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.detail-head { padding: 8px 12px; font-size: 12px; color: var(--text-secondary); background: var(--panel); }
.detail-body {
  margin: 0;
  padding: 10px 12px;
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.pager { display: flex; justify-content: flex-end; margin-top: 12px; }

@media (max-width: 640px) {
  .f-num, .f-select, .f-small, .f-date, .f-input { width: 100%; }
}
</style>
