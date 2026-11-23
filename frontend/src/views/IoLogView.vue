<script setup>
// 管理端运行日志中心（v3 / WP3 §5.5）：4 个指标卡 + 筛选栏 + 表格 + 详情抽屉时间线。
// trace_id 搜索是排障主入口；导出复用现有出口令牌，可重复下载且默认不过期。
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listIoLogs, fetchIoStats, fetchIoDetail, exportIoLogs } from '../api/ioLogs'

const loading = ref(false)
const statsLoading = ref(false)
const stats = ref(null)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)

const filters = reactive({
  range: [],
  status: '',
  intent: '',
  answer_mode: '',
  keyword: '',
  trace_id: '',
  deleted: 'all' // v5 R6：all=含已删除 / visible=不含 / deleted=只看
})

const STATUS_META = {
  ok: { label: '成功', type: 'success' },
  abort: { label: '已中断', type: 'warning' },
  error: { label: '失败', type: 'danger' },
  timeout: { label: '超时', type: 'danger' },
  rejected: { label: '已拒绝', type: 'info' }
}
const INTENT_META = {
  knowledge: '知识库',
  general: '通用',
  biz_query: '业务库',
  calculator: '计算器',
  doc_stats: '文档统计',
  workflow: '工作流',
  chat: '寒暄'
}
const MODE_META = {
  knowledge: '知识库',
  web: '联网',
  general: '通用',
  biz_query: '业务库',
  tool: '工具',
  chat: '寒暄',
  fallback_guide: '引导',
  fallback_contact: '转人工',
  rejected: '拒绝'
}
const PURPOSE_META = {
  plan: '意图决策',
  answer: '答案生成',
  replan: '重规划',
  intent: '业务意图',
  title: '标题',
  summary: '摘要',
  memory_extract: '事实抽取',
  workflow_plan: '工作流规划',
  workflow_reflect: '工作流反思'
}

function intentLabel(v) {
  if (!v || v === 'unknown') return '未判定'
  return INTENT_META[v] || v
}
function modeLabel(v) {
  if (!v || v === 'unknown') return '未产生'
  return MODE_META[v] || v
}

function rangeParams() {
  const [start, end] = filters.range || []
  return { start: start || '', end: end || '' }
}

async function load() {
  loading.value = true
  try {
    const data = await listIoLogs({
      page: page.value,
      size: size.value,
      status: filters.status,
      intent: filters.intent,
      answer_mode: filters.answer_mode,
      keyword: filters.keyword,
      trace_id: filters.trace_id,
      include_deleted: filters.deleted !== 'visible',
      only_deleted: filters.deleted === 'deleted',
      ...rangeParams()
    })
    rows.value = data?.list || []
    total.value = data?.total || 0
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await fetchIoStats()
  } catch {
    stats.value = null
  } finally {
    statsLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([load(), loadStats()])
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  Object.assign(filters, { range: [], status: '', intent: '', answer_mode: '', keyword: '', trace_id: '', deleted: 'all' })
  search()
}

function onPageChange(p) {
  page.value = p
  load()
}

function fmtTime(v) {
  return v ? String(v).replace('T', ' ').slice(0, 19) : '—'
}

function fmtMs(v) {
  if (v === null || v === undefined) return '—'
  return v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`
}

const statCards = computed(() => {
  const s = stats.value || {}
  return [
    { key: 'total', label: '今日请求', value: s.today_total ?? '—', sub: `成功 ${s.today_ok ?? '—'} 次` },
    { key: 'rate', label: '成功率', value: `${s.success_rate ?? '—'}%`, sub: '按今日全部轮次（含拒绝/中断）' },
    { key: 'p95', label: 'P95 首字延迟', value: fmtMs(s.p95_first_token_ms), sub: '仅统计有首字的轮次' },
    { key: 'tokens', label: '今日 token', value: (s.today_tokens ?? 0).toLocaleString(), sub: 'prompt + completion' }
  ]
})

const intentShare = computed(() =>
  (stats.value?.intent_share || []).map((x) => ({
    ...x,
    label: intentLabel(x.intent),
    pct: stats.value?.today_total ? Math.round((x.count / stats.value.today_total) * 100) : 0
  }))
)
const modeShare = computed(() =>
  (stats.value?.mode_share || []).map((x) => ({
    ...x,
    label: modeLabel(x.answer_mode),
    pct: stats.value?.today_total ? Math.round((x.count / stats.value.today_total) * 100) : 0
  }))
)

// ---- 详情抽屉 ----
const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

async function openDetail(row) {
  drawerVisible.value = true
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await fetchIoDetail(row.trace_id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

const toolSteps = computed(() => {
  const chain = detail.value?.tool_chain
  if (!Array.isArray(chain)) return []
  return chain.map((t, i) => ({
    key: `${i}-${t.name || 'tool'}`,
    name: t.name || '工具',
    label: t.label || t.name || '工具',
    status: t.status || 'done',
    round: t.round ?? ''
  }))
})

const timeline = computed(() => {
  const d = detail.value
  if (!d) return []
  const items = []
  const calls = d.llm_calls || []
  let acc = 0
  let order = 10
  for (const c of calls) {
    const latency = c.latency_ms || 0
    items.push({
      key: `llm-${c.call_id}`,
      kind: 'llm',
      title: PURPOSE_META[c.purpose] || c.purpose,
      status: c.status,
      ms: latency,
      at: acc,
      order,
      detail: `${c.model || ''} · prompt ${c.prompt_tokens ?? '—'} / completion ${c.completion_tokens ?? '—'}`,
      error: c.error_code || ''
    })
    acc += latency
    order += 10
  }
  // 工具链没有独立耗时，按「决策之后、作答之前」展示
  if (toolSteps.value.length) {
    items.push({
      key: 'tools',
      kind: 'tool',
      title: `工具检索 · ${toolSteps.value.length} 步`,
      status: 'ok',
      ms: null,
      at: acc,
      order: 15,
      detail: toolSteps.value.map((t) => t.label).join(' → '),
      error: ''
    })
  }
  if (d.first_token_ms !== null && d.first_token_ms !== undefined) {
    items.push({
      key: 'first-token',
      kind: 'first',
      title: '首字输出',
      status: 'ok',
      ms: d.first_token_ms,
      at: d.first_token_ms,
      order: 30,
      detail: '用户可见的第一个 token',
      error: ''
    })
    order = 30
  }
  items.push({
    key: 'total',
    kind: 'total',
    title: '本轮结束',
    status: d.status,
    ms: d.elapsed_ms,
    at: d.elapsed_ms,
    order: 40,
    detail: `${d.frame_count ?? '—'} 帧 · ${modeLabel(d.answer_mode)}`,
    error: d.error_code || ''
  })
  return items.sort((a, b) => a.order - b.order)
})

async function copyTrace(traceId) {
  if (!traceId) return
  try {
    await navigator.clipboard.writeText(traceId)
    ElMessage.success('trace_id 已复制')
  } catch {
    ElMessage.warning('当前浏览器不支持自动复制')
  }
}

function copyDiagnostics() {
  const d = detail.value
  if (!d) return
  const text = [
    `trace_id: ${d.trace_id}`,
    `时间: ${fmtTime(d.created_at)}`,
    `用户: ${d.user_id ?? '—'} / 会话: ${d.session_id ?? '—'}`,
    `状态: ${d.status}${d.error_code ? ` (${d.error_code})` : ''}`,
    `耗时: ${fmtMs(d.elapsed_ms)} / 首字: ${fmtMs(d.first_token_ms)}`,
    `问题: ${d.query}`
  ].join('\n')
  navigator.clipboard?.writeText(text).then(
    () => ElMessage.success('排障信息已复制'),
    () => ElMessage.warning('当前浏览器不支持自动复制')
  )
}

const exporting = ref(false)
async function onExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    const info = await exportIoLogs({
      status: filters.status,
      intent: filters.intent,
      answer_mode: filters.answer_mode,
      keyword: filters.keyword,
      trace_id: filters.trace_id,
      ...rangeParams()
    })
    if (info?.url) {
      window.open(info.url, '_blank')
      ElMessage.success(`已生成 ${info.rows} 行 CSV${info.capped ? '（已达 1 万行上限）' : ''}`)
    }
  } catch {
    // 统一拦截器提示（空结果会返回 40001 的友好提示）
  } finally {
    exporting.value = false
  }
}

onMounted(refreshAll)
</script>

<template>
  <div class="io-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">运行日志</h2>
        <p class="page-desc">
          记录每轮问答的输入输出、链路与耗时，用于排障与质量分析；不参与业务判断，按保留期自动清理。
          按 <code>trace_id</code> 搜索可还原一整轮（含 LLM 调用时间线）。
        </p>
      </div>
      <div class="head-actions">
        <el-button :loading="loading || statsLoading" @click="refreshAll">刷新</el-button>
        <el-button type="primary" plain :loading="exporting" @click="onExport">导出 CSV</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div v-for="c in statCards" :key="c.key" class="stat-card">
        <div class="stat-label">{{ c.label }}</div>
        <div class="stat-value">{{ c.value }}</div>
        <div class="stat-sub">{{ c.sub }}</div>
      </div>
    </div>

    <div v-if="intentShare.length || modeShare.length" class="share-row">
      <div class="share-block">
        <div class="share-title">今日链路占比 · 意图</div>
        <div v-for="x in intentShare" :key="`i-${x.intent}`" class="share-line">
          <span class="share-name">{{ x.label }}</span>
          <div class="share-bar"><i :style="{ width: x.pct + '%' }"></i></div>
          <span class="share-count">{{ x.count }}</span>
        </div>
      </div>
      <div class="share-block">
        <div class="share-title">今日链路占比 · 回答模式</div>
        <div v-for="x in modeShare" :key="`m-${x.answer_mode}`" class="share-line">
          <span class="share-name">{{ x.label }}</span>
          <div class="share-bar"><i :style="{ width: x.pct + '%' }"></i></div>
          <span class="share-count">{{ x.count }}</span>
        </div>
      </div>
    </div>

    <div class="filter-card">
      <el-date-picker
        v-model="filters.range"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        unlink-panels
        class="f-range"
      />
      <el-select v-model="filters.status" placeholder="状态" clearable class="f-sm">
        <el-option v-for="(m, k) in STATUS_META" :key="k" :label="m.label" :value="k" />
      </el-select>
      <el-select v-model="filters.intent" placeholder="意图" clearable class="f-sm">
        <el-option v-for="(label, k) in INTENT_META" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.answer_mode" placeholder="链路" clearable class="f-sm">
        <el-option v-for="(label, k) in MODE_META" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.deleted" class="f-sm" aria-label="删除状态筛选">
        <el-option label="含用户已删除" value="all" />
        <el-option label="不含已删除" value="visible" />
        <el-option label="只看已删除" value="deleted" />
      </el-select>
      <el-input v-model="filters.keyword" placeholder="问题关键词" clearable class="f-md" @keyup.enter="search" />
      <el-input
        v-model="filters.trace_id"
        placeholder="trace_id（排障主入口）"
        clearable
        class="f-md"
        @keyup.enter="search"
      />
      <div class="filter-actions">
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="rows" class="log-table" size="small" row-key="log_id" empty-text="暂无运行日志">
      <el-table-column label="时间" width="158">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="用户" width="72" prop="user_id" />
      <el-table-column label="删除状态" width="96">
        <template #default="{ row }">
          <el-tag v-if="row.user_deleted" size="small" type="info">用户已删除</el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="意图" width="90">
        <template #default="{ row }">
          <span class="pill">{{ intentLabel(row.intent) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="链路" width="82">
        <template #default="{ row }">
          <span class="pill muted">{{ modeLabel(row.answer_mode) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="86">
        <template #default="{ row }">
          <el-tag :type="STATUS_META[row.status]?.type || 'info'" size="small" effect="plain">
            {{ STATUS_META[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="76">
        <template #default="{ row }">{{ fmtMs(row.elapsed_ms) }}</template>
      </el-table-column>
      <el-table-column label="首字" width="76">
        <template #default="{ row }">{{ fmtMs(row.first_token_ms) }}</template>
      </el-table-column>
      <el-table-column label="token" width="72">
        <template #default="{ row }">{{ row.total_tokens ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="问题摘要" min-width="200">
        <template #default="{ row }">
          <span class="query-text" :title="row.query">{{ row.query }}</span>
          <div v-if="row.error_code" class="err-text">{{ row.error_code }}{{ row.error_msg ? ` · ${row.error_msg}` : '' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="92" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        :current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="onPageChange"
      />
    </div>

    <el-drawer v-model="drawerVisible" title="运行日志详情" size="min(720px, 96vw)" append-to-body>
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="detail">
          <div class="detail-head">
            <div class="trace-line">
              <span class="trace-label">trace_id</span>
              <code class="trace-code">{{ detail.trace_id }}</code>
              <el-button link type="primary" size="small" @click="copyTrace(detail.trace_id)">复制</el-button>
            </div>
            <div class="detail-actions">
              <el-button size="small" @click="copyDiagnostics">复制排障信息</el-button>
            </div>
          </div>

          <div class="kv-grid">
            <div class="kv"><span>时间</span><b>{{ fmtTime(detail.created_at) }}</b></div>
            <div class="kv"><span>状态</span><b>{{ STATUS_META[detail.status]?.label || detail.status }} {{ detail.error_code || '' }}</b></div>
            <div class="kv"><span>用户 / 会话</span><b>{{ detail.user_id ?? '—' }} / {{ detail.session_id ?? '—' }}</b></div>
            <div class="kv"><span>记录 / 轮次</span><b>{{ detail.record_id ?? '—' }} / {{ detail.turn_index ?? '—' }}</b></div>
            <div class="kv"><span>意图 / 链路</span><b>{{ intentLabel(detail.intent) }} / {{ modeLabel(detail.answer_mode) }}</b></div>
            <div class="kv"><span>耗时 / 首字</span><b>{{ fmtMs(detail.elapsed_ms) }} / {{ fmtMs(detail.first_token_ms) }}</b></div>
            <div class="kv"><span>token</span><b>{{ detail.prompt_tokens ?? '—' }} + {{ detail.completion_tokens ?? '—' }} = {{ detail.total_tokens ?? '—' }}</b></div>
            <div class="kv"><span>帧数</span><b>{{ detail.frame_count ?? '—' }}</b></div>
            <div class="kv"><span>模型</span><b>{{ detail.model || '—' }}</b></div>
            <div class="kv"><span>IP / UA</span><b class="ellipsis" :title="detail.ua || ''">{{ detail.ip_masked || '—' }} · {{ (detail.ua || '—').slice(0, 40) }}</b></div>
          </div>

          <div class="section-title">调用时间线</div>
          <el-timeline class="timeline">
            <el-timeline-item
              v-for="item in timeline"
              :key="item.key"
              :timestamp="fmtMs(item.at)"
              :type="item.kind === 'total' ? 'primary' : item.kind === 'first' ? 'success' : 'info'"
              size="normal"
            >
              <div class="tl-title">{{ item.title }} <span class="tl-ms">+{{ fmtMs(item.ms) }}</span></div>
              <div class="tl-detail">{{ item.detail }}</div>
              <div v-if="item.error" class="tl-error">{{ item.error }}</div>
            </el-timeline-item>
          </el-timeline>

          <div v-if="toolSteps.length" class="section-title">工具链</div>
          <div v-if="toolSteps.length" class="tool-chain">
            <el-tag v-for="t in toolSteps" :key="t.key" size="small" effect="plain">
              {{ t.label }} · {{ t.status }}
            </el-tag>
          </div>

          <div class="section-title">问题</div>
          <pre class="text-box">{{ detail.query }}</pre>
          <div class="section-title">回答</div>
          <pre class="text-box answer">{{ detail.answer || '（本轮未产生回答）' }}</pre>
        </template>
        <div v-else-if="!detailLoading" class="empty-tip">日志不存在或已被删除</div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.io-page {
  max-width: 1320px;
  margin: 0 auto;
  padding: 4px 4px 24px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.page-desc {
  margin: 6px 0 0;
  max-width: 720px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.head-actions {
  display: flex;
  gap: 8px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.stat-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.stat-value {
  margin-top: 6px;
  font-size: 26px;
  font-weight: 650;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.stat-sub {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
}

.share-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.share-block {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
}

.share-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.share-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
  font-size: 12px;
}

.share-name {
  width: 64px;
  flex: none;
  color: var(--text-secondary);
}

.share-bar {
  flex: 1;
  height: 6px;
  border-radius: 4px;
  background: var(--surface-muted);
  overflow: hidden;
}

.share-bar i {
  display: block;
  height: 100%;
  background: var(--brand, #2f6fed);
  opacity: 0.7;
}

.share-count {
  width: 36px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.filter-card {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
  padding: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.f-range { width: 240px; }
.f-sm { width: 116px; }
.f-md { width: 180px; }
.filter-actions { margin-left: auto; display: flex; gap: 8px; }

.log-table {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.pill {
  font-size: 12px;
  color: var(--text);
}

.pill.muted { color: var(--text-secondary); }

.query-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.err-text {
  font-size: 11px;
  color: var(--danger, #f56c6c);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.detail-body { padding: 0 4px 24px; }

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.trace-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.trace-label { font-size: 12px; color: var(--text-secondary); }

.trace-code {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--surface-muted);
  overflow: hidden;
  text-overflow: ellipsis;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 16px;
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
}

.kv {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  min-width: 0;
}

.kv span { color: var(--text-secondary); flex: none; }
.kv b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.section-title {
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 600;
}

.timeline { padding-left: 2px; }

.tl-title { font-size: 13px; }
.tl-ms { margin-left: 6px; font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.tl-detail { font-size: 12px; color: var(--text-secondary); }
.tl-error { font-size: 12px; color: var(--danger, #f56c6c); }

.tool-chain { display: flex; gap: 6px; flex-wrap: wrap; }

.text-box {
  margin: 0;
  padding: 10px 12px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.text-box.answer { max-height: 320px; }

.empty-tip {
  margin-top: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .share-row { grid-template-columns: 1fr; }
  .f-range, .f-md, .f-sm { width: 100%; }
  .filter-actions { margin-left: 0; width: 100%; }
}

.muted { color: var(--text-secondary); }
</style>
