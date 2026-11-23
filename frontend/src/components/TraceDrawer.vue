<script setup>
// 本轮链路抽屉（v3 / WP5-1）：用户本人 trace 的时间线、模型调用、工具链与上下文注入。
// v5 R9：adminView=true 时改走管理端接口，并显示“已记录审计”的只读横幅。
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMyTrace, fetchIoDetail } from '../api/ioLogs'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  traceId: { type: String, default: '' },
  fallback: { type: Object, default: null },
  adminView: { type: Boolean, default: false },
  ownerLabel: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const detail = ref(null)
const error = ref('')

const PURPOSE_META = {
  answer: '知识库作答',
  intent: '意图识别',
  title: '标题提炼',
  summary: '滚动摘要',
  memory_extract: '会话事实抽取',
  query_rewrite: '多轮 query 改写',
  workflow_plan: '任务规划',
  workflow_step: '任务步骤',
  workflow_summary: '任务报告',
  workflow_reflect: '任务反思'
}

function fmtMs(ms) {
  if (ms === null || ms === undefined || ms === '') return '—'
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  if (n < 1000) return `${n} ms`
  return `${(n / 1000).toFixed(n < 10000 ? 2 : 1)} s`
}

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(String(ts).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { hour12: false })
}

function fmtNum(n) {
  return n === null || n === undefined ? '—' : Number(n).toLocaleString('zh-CN')
}

const turn = computed(() => detail.value || props.fallback || {})
const calls = computed(() => detail.value?.llm_calls || [])
const toolSteps = computed(() => {
  const chain = detail.value?.tool_chain
  if (!Array.isArray(chain)) return []
  return chain.map((t, i) => ({
    key: `${i}-${t.name || 'tool'}`,
    label: t.label || t.name || '工具',
    status: t.status || 'done',
    round: t.round
  }))
})

const timeline = computed(() => {
  const d = detail.value
  if (!d) return []
  const items = []
  let acc = 0
  let order = 10
  for (const c of calls.value) {
    const latency = Number(c.latency_ms || 0)
    items.push({
      key: `llm-${c.call_id}`,
      kind: c.status === 'error' ? 'danger' : 'primary',
      title: PURPOSE_META[c.purpose] || c.purpose || '模型调用',
      chip: c.model || '',
      ms: latency,
      at: acc,
      order,
      detail: `${c.model || '—'} · prompt ${fmtNum(c.prompt_tokens)} / completion ${fmtNum(c.completion_tokens)} · ${c.status}`,
      error: c.error_code || ''
    })
    acc += latency
    order += 10
  }
  if (toolSteps.value.length) {
    items.push({
      key: 'tools',
      kind: 'info',
      title: `工具与检索 · ${toolSteps.value.length} 步`,
      chip: '',
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
      kind: 'success',
      title: '首字到达用户',
      chip: '',
      ms: d.first_token_ms,
      at: d.first_token_ms,
      order: 30,
      detail: '流式输出的第一个 token，前端开始打字机播放',
      error: ''
    })
  }
  items.push({
    key: 'total',
    kind: d.status === 'ok' ? 'success' : 'danger',
    title: '本轮结束',
    chip: '',
    ms: d.elapsed_ms,
    at: d.elapsed_ms,
    order: 40,
    detail: `${d.frame_count ?? '—'} 帧 · ${modeLabel(d.answer_mode)}`,
    error: d.error_code || ''
  })
  return items.sort((a, b) => a.order - b.order)
})

const budgetRows = computed(() => {
  const ctx = detail.value?.context_usage || props.fallback?.contextUsage
  if (!ctx || typeof ctx !== 'object') return []
  const fields = [
    ['system_tokens', '系统约束', 'system'],
    ['facts_tokens', '会话事实', 'facts'],
    ['summary_tokens', '滚动摘要', 'summary'],
    ['history_tokens', '原文窗口', 'history'],
    ['retrieval_tokens', '检索资料', 'retrieval'],
    ['query_tokens', '本轮问题', 'query']
  ]
  const rows = fields
    .map(([key, label, kind]) => ({ key, label, kind, tokens: Number(ctx[key] || 0) }))
    .filter((x) => x.tokens > 0)
  if (!rows.length) return []
  const total = Number(ctx.prompt_tokens_total || rows.reduce((s, x) => s + x.tokens, 0))
  return rows.map((x) => ({ ...x, pct: total ? Math.max(1, Math.round((x.tokens / total) * 100)) : 0 }))
})
const budgetTotal = computed(() => {
  const ctx = detail.value?.context_usage || props.fallback?.contextUsage
  if (!ctx) return 0
  return Number(ctx.prompt_tokens_total || budgetRows.value.reduce((s, x) => s + x.tokens, 0))
})
const budgetLimit = computed(() => {
  const ctx = detail.value?.context_usage || props.fallback?.contextUsage
  return Number(ctx?.budget_tokens || 0)
})
const budgetPct = computed(() => {
  const ctx = detail.value?.context_usage || props.fallback?.contextUsage
  return Number(ctx?.budget_utilization_pct || 0)
})

const contextItems = computed(() => {
  const ctx = detail.value?.context_usage
  if (!ctx || typeof ctx !== 'object') return []
  const hidden = new Set([
    'system_tokens', 'facts_tokens', 'summary_tokens', 'history_tokens',
    'retrieval_tokens', 'query_tokens', 'memory_tokens', 'prompt_tokens_total',
    'budget_tokens', 'budget_utilization_pct', 'retrieval_chunks'
  ])
  return Object.entries(ctx)
    .filter(([k]) => !hidden.has(k))
    .map(([k, v]) => ({
      key: k,
      label: CONTEXT_META[k] || k,
      value: typeof v === 'object' ? JSON.stringify(v) : String(v)
    }))
})

const CONTEXT_META = {
  history_rounds: '历史轮数',
  history_chars: '历史字数',
  summary_chars: '摘要字数',
  total_tokens: '记忆合计 token',
  memory_items: '长期记忆条数',
  sources: '知识库引用',
  tool_steps: '工具步骤',
  workflow_steps: '任务步骤',
  memory_enabled: '会话记忆',
  facts_count: '事实条数',
  dropped_rounds: '被裁剪轮数',
  window_rounds: '窗口轮数上限',
  answer_chars: '回答字数',
  digest_chars: '摘要截取字数',
  token_estimator: '估算口径'
}

function modeLabel(mode) {
  return { kb: '知识库', general: '通用回答', web: '联网', biz: '业务库', workflow: '任务编排' }[mode] || mode || '—'
}

const statusTag = computed(() => {
  const s = turn.value?.status
  if (s === 'ok') return { type: 'success', text: '成功' }
  if (s === 'error') return { type: 'danger', text: '失败' }
  if (s === 'abort') return { type: 'warning', text: '已中断' }
  return { type: 'info', text: s || '—' }
})

async function load() {
  if (!props.traceId) {
    error.value = '本轮没有 trace_id'
    return
  }
  loading.value = true
  error.value = ''
  detail.value = null
  try {
    detail.value = props.adminView ? await fetchIoDetail(props.traceId) : await fetchMyTrace(props.traceId)
  } catch (e) {
    error.value = e?.message || '链路加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load()
  }
)

async function copyTrace() {
  try {
    await navigator.clipboard.writeText(props.traceId || '')
    ElMessage.success('trace_id 已复制')
  } catch {
    ElMessage.warning('当前浏览器不支持自动复制')
  }
}

async function copyDiagnostics() {
  const d = turn.value
  const text = [
    `trace_id: ${props.traceId || d.trace_id || '—'}`,
    `时间: ${fmtTime(d.created_at)}`,
    `状态: ${d.status || '—'}${d.error_code ? ` (${d.error_code})` : ''}`,
    `意图/链路: ${d.intent || '—'} / ${d.answer_mode || '—'}`,
    `耗时/首字: ${fmtMs(d.elapsed_ms)} / ${fmtMs(d.first_token_ms)}`,
    `token: ${fmtNum(d.prompt_tokens)} / ${fmtNum(d.completion_tokens)}`,
    `问题: ${d.query || '—'}`
  ].join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('排障信息已复制')
  } catch {
    ElMessage.warning('当前浏览器不支持自动复制')
  }
}

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    class="trace-drawer"
    size="min(560px, 100vw)"
    :with-header="false"
    append-to-body
    @close="close"
  >
    <div class="td-shell">
      <header class="td-head">
        <div>
          <div class="td-kicker">本轮链路</div>
          <h2>这条回答是怎么生成的</h2>
        </div>
        <div class="td-head-actions">
          <el-button link size="small" @click="copyDiagnostics">复制排障信息</el-button>
          <el-button class="td-close" link @click="close">关闭</el-button>
        </div>
      </header>

      <div v-if="adminView" class="td-audit-banner">
        正在查看用户「{{ ownerLabel || detail?.user_id || '—' }}」的记录，本次查看已记录审计日志
      </div>

      <div v-if="traceId" class="td-trace">
        <span class="td-trace-label">trace_id</span>
        <code>{{ traceId }}</code>
        <el-button link size="small" @click="copyTrace">复制</el-button>
      </div>

      <el-skeleton v-if="loading" :rows="6" animated class="td-skeleton" />

      <el-empty
        v-else-if="error"
        :description="error"
        :image-size="72"
        class="td-empty"
      >
        <el-button size="small" @click="load">重试</el-button>
      </el-empty>

      <template v-else-if="detail">
        <section class="td-overview">
          <div class="td-status">
            <el-tag :type="statusTag.type" effect="light" round>{{ statusTag.text }}</el-tag>
            <span class="td-time">{{ fmtTime(detail.created_at) }}</span>
          </div>
          <div class="td-metrics">
            <div class="td-metric">
              <span>总耗时</span><b>{{ fmtMs(detail.elapsed_ms) }}</b>
            </div>
            <div class="td-metric">
              <span>首字延迟</span><b>{{ fmtMs(detail.first_token_ms) }}</b>
            </div>
            <div class="td-metric">
              <span>Token</span><b>{{ fmtNum(detail.total_tokens) }}</b>
            </div>
            <div class="td-metric">
              <span>流式帧</span><b>{{ fmtNum(detail.frame_count) }}</b>
            </div>
          </div>
          <div class="td-facts">
            <div><span>意图</span><b>{{ detail.intent || '—' }}</b></div>
            <div><span>链路</span><b>{{ modeLabel(detail.answer_mode) }}</b></div>
            <div><span>轮次</span><b>第 {{ detail.turn_index ?? '—' }} 轮</b></div>
          </div>
        </section>

        <section v-if="detail.query_rewritten" class="td-section td-rewrite">
          <div class="td-section-title">多轮 query 改写</div>
          <div class="td-rewrite-flow">
            <div><span>原句</span><b>{{ detail.query || '—' }}</b></div>
            <div><span>检索句</span><b>{{ detail.query_rewritten }}</b></div>
            <div v-if="detail.rewrite_reason" class="td-rewrite-reason">{{ detail.rewrite_reason }}</div>
          </div>
        </section>

        <section v-if="timeline.length" class="td-section">
          <div class="td-section-title">阶段时间线</div>
          <el-timeline class="td-timeline">
            <el-timeline-item
              v-for="item in timeline"
              :key="item.key"
              :timestamp="`+${fmtMs(item.ms)}`"
              :type="item.kind"
              size="normal"
            >
              <div class="td-tl-title">
                {{ item.title }}
                <el-tag v-if="item.chip" size="small" effect="plain" class="td-model">{{ item.chip }}</el-tag>
              </div>
              <div class="td-tl-detail">{{ item.detail }}</div>
              <div v-if="item.error" class="td-tl-error">{{ item.error }}</div>
            </el-timeline-item>
          </el-timeline>
        </section>

        <section v-if="toolSteps.length" class="td-section">
          <div class="td-section-title">工具与检索</div>
          <div class="td-tools">
            <span v-for="t in toolSteps" :key="t.key" class="td-tool">
              <em>{{ t.label }}</em>
              <small>{{ t.status }}</small>
            </span>
          </div>
        </section>

        <section v-if="budgetRows.length" class="td-section">
          <div class="td-section-head">
            <div class="td-section-title">上下文预算</div>
            <span class="td-budget-total">提示词合计 {{ fmtNum(budgetTotal) }} token</span>
          </div>
          <div class="td-budget-bar" role="img" :aria-label="`上下文 token 构成，合计 ${budgetTotal}`">
            <span
              v-for="r in budgetRows"
              :key="r.key"
              class="td-budget-seg"
              :class="`seg-${r.kind}`"
              :style="{ width: `${r.pct}%` }"
              :title="`${r.label} ${fmtNum(r.tokens)} token / ${r.pct}%`"
            ></span>
          </div>
          <div class="td-budget-rows">
            <div v-for="r in budgetRows" :key="r.key" class="td-budget-row">
              <span class="td-budget-label"><i :class="`seg-${r.kind}`"></i>{{ r.label }}</span>
              <span class="td-budget-value">{{ fmtNum(r.tokens) }} token · {{ r.pct }}%</span>
            </div>
          </div>
          <div v-if="budgetLimit" class="td-budget-foot">
            记忆预算 {{ fmtNum(budgetLimit) }} token，当前占用 {{ budgetPct }}%（事实 + 摘要 + 原文窗口）
          </div>
        </section>

        <section v-if="contextItems.length" class="td-section">
          <div class="td-section-title">上下文注入</div>
          <div class="td-context">
            <div v-for="c in contextItems" :key="c.key" class="td-context-row">
              <span>{{ c.label }}</span><b>{{ c.value }}</b>
            </div>
          </div>
        </section>

        <section class="td-section">
          <div class="td-section-title">本轮问题</div>
          <div class="td-query">{{ detail.query || '—' }}</div>
        </section>
      </template>

      <div class="td-foot">
        <span>仅展示你本人的运行日志；日志超过保留期会被自动清理。</span>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.trace-drawer :deep(.el-drawer__body) {
  padding: 0;
}

.td-shell {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--panel);
}

.td-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 22px 14px;
  border-bottom: 1px solid var(--border);
}

.td-kicker {
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--primary);
  font-weight: 600;
}

.td-head h2 {
  margin: 6px 0 0;
  font-size: 19px;
  line-height: 1.35;
  color: var(--text);
}

.td-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.td-close {
  color: var(--text-secondary);
}

.td-trace {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  background: var(--surface-muted);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.td-trace-label {
  color: var(--text-secondary);
}

.td-trace code {
  font-family: var(--font-mono, ui-monospace, Menlo, monospace);
  font-size: 12px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
}

.td-skeleton {
  padding: 20px 22px;
}

.td-empty {
  padding: 24px;
}

.td-overview {
  padding: 18px 22px 4px;
}

.td-status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.td-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.td-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.td-metric {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-muted);
}

.td-metric span {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
}

.td-metric b {
  display: block;
  margin-top: 4px;
  font-size: 15px;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

.td-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin-top: 12px;
  font-size: 12px;
}

.td-facts span {
  color: var(--text-secondary);
}

.td-facts b {
  color: var(--text);
  font-weight: 500;
}

.td-section {
  padding: 14px 22px 4px;
}

.td-section-title {
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}

.td-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.td-section-head .td-section-title {
  margin-bottom: 12px;
}

.td-rewrite-flow {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2, #f8fafc);
  font-size: 12px;
}

.td-rewrite-flow div {
  display: flex;
  gap: 10px;
  line-height: 1.6;
}

.td-rewrite-flow span {
  flex: 0 0 48px;
  color: var(--text-muted);
}

.td-rewrite-flow b {
  color: var(--text);
  font-weight: 500;
  word-break: break-all;
}

.td-rewrite-reason {
  color: var(--text-secondary);
  font-size: 11px;
}

.td-budget-total {
  font-size: 11px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.td-budget-bar {
  display: flex;
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--surface-muted);
  border: 1px solid var(--border);
}

.td-budget-seg {
  display: block;
  height: 100%;
  min-width: 2px;
}

.seg-system { background: #64748b; }
.seg-facts { background: #0f766e; }
.seg-summary { background: #b45309; }
.seg-history { background: #2563eb; }
.seg-retrieval { background: #7c3aed; }
.seg-query { background: #be123c; }

/* 分类色只用于预算条与图例，不改变产品主色体系 */
.td-budget-rows {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 18px;
  margin-top: 10px;
}

.td-budget-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.td-budget-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
}

.td-budget-label i {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 2px;
  font-style: normal;
}

.td-budget-value {
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.td-budget-foot {
  margin-top: 10px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.td-timeline {
  padding-left: 2px;
}

.td-tl-title {
  font-size: 13px;
  color: var(--text);
}

.td-model {
  margin-left: 6px;
}

.td-tl-detail {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-word;
}

.td-tl-error {
  margin-top: 3px;
  font-size: 12px;
  color: var(--danger);
}

.td-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.td-tool {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface-muted);
}

.td-tool em {
  font-style: normal;
  font-size: 12px;
  color: var(--text);
}

.td-tool small {
  font-size: 11px;
  color: var(--text-secondary);
}

.td-context {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.td-context-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 12px;
  font-size: 12px;
}

.td-context-row + .td-context-row {
  border-top: 1px solid var(--border);
}

.td-context-row span {
  color: var(--text-secondary);
}

.td-context-row b {
  font-weight: 500;
  color: var(--text);
  text-align: right;
  word-break: break-word;
}

.td-query {
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  border: 1px solid var(--border);
  font-size: 13px;
  line-height: 1.65;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.td-foot {
  margin-top: auto;
  padding: 18px 22px 24px;
  font-size: 11px;
  color: var(--text-secondary);
}

@media (max-width: 480px) {
  .td-head {
    padding: 18px 16px 12px;
    flex-direction: column;
  }

  .td-trace,
  .td-overview,
  .td-section {
    padding-left: 16px;
    padding-right: 16px;
  }

  .td-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .td-budget-rows {
    grid-template-columns: 1fr;
  }

  .td-head-actions {
    width: 100%;
    justify-content: space-between;
  }
}

.td-audit-banner {
  margin: 12px 22px 0;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #e6a23c;
  background: rgba(230, 162, 60, 0.1);
  color: #b88230;
  font-size: 12px;
  line-height: 1.5;
}
</style>
