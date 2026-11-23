<script setup>
// 管理员用户全景抽屉（v5 R7 / R9）：概览、问答、会话、文档、反馈、活动流全部只读。
// 打开他人链路时复用 TraceDrawer 的管理员只读模式（带审计横幅）。
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchUserOverview,
  fetchUserQa,
  fetchUserSessions,
  fetchUserMessages,
  fetchUserDocuments,
  fetchUserFeedback,
  fetchUserActivity
} from '../api/adminUsers'
import TraceDrawer from './TraceDrawer.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  userId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue'])

const tab = ref('overview')
const overview = ref(null)
const overviewLoading = ref(false)
const overviewError = ref('')

const qa = ref({ list: [], total: 0, page: 1, size: 20, loading: false })
const qaFilter = ref({ keyword: '', status: '', start: '', end: '' })

const sessions = ref({ list: [], total: 0, page: 1, size: 20, loading: false })
const docs = ref({ list: [], total: 0, page: 1, size: 20, loading: false })
const feedback = ref({ list: [], total: 0, page: 1, size: 20, loading: false })
const activity = ref({ list: [], total: 0, page: 1, size: 20, loading: false })
const activityType = ref('')

const traceOpen = ref(false)
const traceId = ref('')

const msgOpen = ref(false)
const msgLoading = ref(false)
const msgSession = ref(null)
const msgData = ref({ list: [], total: 0 })

const ownerLabel = computed(() => {
  const o = overview.value
  return o ? `${o.display_name || o.username}（${o.username}）` : ''
})

function fmtTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 19)
}

function fmtMs(ms) {
  if (ms === null || ms === undefined || ms === '') return '—'
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  return n < 1000 ? `${n} ms` : `${(n / 1000).toFixed(2)} s`
}

function statusLabel(status) {
  return { ok: '成功', error: '失败', abort: '已中断', timeout: '超时', rejected: '已拦截' }[status] || status || '—'
}

function statusType(status) {
  return { ok: 'success', error: 'danger', abort: 'warning', timeout: 'warning', rejected: 'info' }[status] || 'info'
}

function modeLabel(mode) {
  return { kb: '知识库', general: '通用', web: '联网', biz: '业务库', workflow: '任务编排' }[mode] || mode || '—'
}

const ACT_TYPE_LABEL = { qa: '问答', login: '登录', doc: '文档', export: '导出', admin: '管理', other: '其他' }

async function loadOverview() {
  if (!props.userId) return
  overviewLoading.value = true
  overviewError.value = ''
  try {
    overview.value = await fetchUserOverview(props.userId)
  } catch (e) {
    overviewError.value = e?.message || '概览加载失败'
    overview.value = null
  } finally {
    overviewLoading.value = false
  }
}

async function loadQa(page = qa.value.page) {
  if (!props.userId) return
  qa.value.loading = true
  try {
    const data = await fetchUserQa(props.userId, { page, size: qa.value.size, ...qaFilter.value })
    qa.value.list = data?.list || []
    qa.value.total = data?.total || 0
    qa.value.page = page
  } catch (e) {
    ElMessage.error(e?.message || '问答记录加载失败')
  } finally {
    qa.value.loading = false
  }
}

async function loadSessions(page = sessions.value.page) {
  if (!props.userId) return
  sessions.value.loading = true
  try {
    const data = await fetchUserSessions(props.userId, { page, size: sessions.value.size })
    sessions.value.list = data?.list || []
    sessions.value.total = data?.total || 0
    sessions.value.page = page
  } catch (e) {
    ElMessage.error(e?.message || '会话加载失败')
  } finally {
    sessions.value.loading = false
  }
}

async function loadDocs(page = docs.value.page) {
  if (!props.userId) return
  docs.value.loading = true
  try {
    const data = await fetchUserDocuments(props.userId, { page, size: docs.value.size })
    docs.value.list = data?.list || []
    docs.value.total = data?.total || 0
    docs.value.page = page
  } catch (e) {
    ElMessage.error(e?.message || '文档记录加载失败')
  } finally {
    docs.value.loading = false
  }
}

async function loadFeedback(page = feedback.value.page) {
  if (!props.userId) return
  feedback.value.loading = true
  try {
    const data = await fetchUserFeedback(props.userId, { page, size: feedback.value.size })
    feedback.value.list = data?.list || []
    feedback.value.total = data?.total || 0
    feedback.value.page = page
  } catch (e) {
    ElMessage.error(e?.message || '反馈加载失败')
  } finally {
    feedback.value.loading = false
  }
}

async function loadActivity(page = activity.value.page) {
  if (!props.userId) return
  activity.value.loading = true
  try {
    const data = await fetchUserActivity(props.userId, {
      page, size: activity.value.size, type: activityType.value
    })
    activity.value.list = data?.list || []
    activity.value.total = data?.total || 0
    activity.value.page = page
  } catch (e) {
    ElMessage.error(e?.message || '活动流加载失败')
  } finally {
    activity.value.loading = false
  }
}

function loadTab(name) {
  if (name === 'qa' && !qa.value.list.length) loadQa(1)
  if (name === 'sessions' && !sessions.value.list.length) loadSessions(1)
  if (name === 'docs' && !docs.value.list.length) loadDocs(1)
  if (name === 'feedback' && !feedback.value.list.length) loadFeedback(1)
  if (name === 'activity' && !activity.value.list.length) loadActivity(1)
}

function onTabChange(name) {
  tab.value = name
  loadTab(name)
}

function openTrace(row) {
  if (!row?.trace_id) {
    ElMessage.warning('该轮没有 trace_id')
    return
  }
  traceId.value = row.trace_id
  traceOpen.value = true
}

async function openMessages(row) {
  msgSession.value = row
  msgData.value = { list: [], total: 0 }
  msgOpen.value = true
  msgLoading.value = true
  try {
    const data = await fetchUserMessages(props.userId, row.session_id, { page: 1, size: 50 })
    msgData.value = { list: data?.list || [], total: data?.total || 0 }
  } catch (e) {
    ElMessage.error(e?.message || '消息加载失败')
  } finally {
    msgLoading.value = false
  }
}

function close() {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    tab.value = 'overview'
    qa.value.list = []
    sessions.value.list = []
    docs.value.list = []
    feedback.value.list = []
    activity.value.list = []
    traceOpen.value = false
    msgOpen.value = false
    loadOverview()
  }
)

watch(
  () => props.userId,
  () => {
    if (props.modelValue) loadOverview()
  }
)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :with-header="false"
    size="min(1080px, 100vw)"
    append-to-body
    class="aud-user-drawer"
    @close="close"
  >
    <div class="aud-shell">
      <header class="aud-head">
        <div class="aud-head-main">
          <div class="aud-kicker">用户全景（只读）</div>
          <h2>{{ overview?.display_name || overview?.username || `用户 #${userId}` }}</h2>
          <div class="aud-tags">
            <el-tag size="small" effect="plain">{{ overview?.username || '—' }}</el-tag>
            <el-tag size="small" :type="overview?.role === 'admin' ? 'warning' : 'info'" effect="plain">
              {{ overview?.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
            <el-tag size="small" :type="overview?.status === 1 ? 'success' : 'danger'" effect="dark">
              {{ overview?.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </div>
        </div>
        <el-button link @click="close">关闭</el-button>
      </header>

      <div class="aud-banner">
        正在查看用户「{{ ownerLabel || `#${userId}` }}」的数据，本次查看已记录审计日志
      </div>

      <el-skeleton v-if="overviewLoading" :rows="5" animated />

      <el-alert
        v-else-if="overviewError"
        type="error"
        :closable="false"
        show-icon
        :title="overviewError"
      />

      <el-tabs v-else :model-value="tab" class="aud-tabs" @tab-change="onTabChange">
        <el-tab-pane label="概览" name="overview">
          <div class="aud-grid">
            <div class="aud-cell"><label>用户 ID</label><b>{{ overview?.user_id ?? '—' }}</b></div>
            <div class="aud-cell"><label>注册时间</label><b>{{ fmtTime(overview?.created_at) }}</b></div>
            <div class="aud-cell"><label>最近登录</label><b>{{ fmtTime(overview?.last_login_at) }}</b></div>
            <div class="aud-cell"><label>最近问答</label><b>{{ fmtTime(overview?.last_qa_at) }}</b></div>
            <div class="aud-cell"><label>会话数</label><b>{{ overview?.session_total ?? 0 }}</b></div>
            <div class="aud-cell"><label>问答轮次</label><b>{{ overview?.qa_total ?? 0 }}</b></div>
            <div class="aud-cell"><label>近 7 天问答</label><b>{{ overview?.qa_7d ?? 0 }}</b></div>
            <div class="aud-cell"><label>近 30 天问答</label><b>{{ overview?.qa_30d ?? 0 }}</b></div>
            <div class="aud-cell"><label>累计 token</label><b>{{ (overview?.total_tokens ?? 0).toLocaleString('zh-CN') }}</b></div>
            <div class="aud-cell"><label>上传文档</label><b>{{ overview?.document_total ?? 0 }}</b></div>
            <div class="aud-cell"><label>反馈条数</label><b>{{ overview?.feedback_total ?? 0 }}</b></div>
            <div class="aud-cell"><label>操作审计</label><b>{{ overview?.audit_total ?? 0 }}</b></div>
            <div class="aud-cell aud-warn"><label>本人已删除日志</label><b>{{ overview?.qa_deleted ?? 0 }}</b></div>
            <div class="aud-cell aud-warn"><label>被管理员查看次数</label><b>{{ overview?.viewed_by_admin ?? 0 }}</b></div>
          </div>
          <p class="aud-note">
            说明：用户可在「个人设置」删除本人运行日志，删除后仅本人不可见；管理员在保留期内仍可审计查看。
            知识库为共享库，文档归属按操作审计反推。
          </p>
        </el-tab-pane>

        <el-tab-pane label="问答记录" name="qa">
          <div class="aud-filter">
            <el-input
              v-model="qaFilter.keyword"
              size="small"
              clearable
              placeholder="问题关键词"
              class="f-input"
              @keyup.enter="loadQa(1)"
            />
            <el-select v-model="qaFilter.status" size="small" clearable placeholder="状态" class="f-select">
              <el-option label="成功" value="ok" />
              <el-option label="失败" value="error" />
              <el-option label="已中断" value="abort" />
              <el-option label="超时" value="timeout" />
              <el-option label="已拦截" value="rejected" />
            </el-select>
            <el-button size="small" type="primary" @click="loadQa(1)">查询</el-button>
            <span class="f-total">共 {{ qa.total }} 轮</span>
          </div>

          <el-table :data="qa.list" v-loading="qa.loading" size="small" class="aud-table">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="问题" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.query || '—' }}</span>
                <el-tag v-if="row.user_deleted" size="small" type="info" class="del-tag">用户已删除</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="回答摘要" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">{{ row.answer || '—' }}</template>
            </el-table-column>
            <el-table-column label="链路" width="90">
              <template #default="{ row }">{{ modeLabel(row.answer_mode) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="90">
              <template #default="{ row }">{{ fmtMs(row.elapsed_ms) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="70" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" type="primary" @click="openTrace(row)">链路</el-button>
              </template>
            </el-table-column>
            <template #empty><el-empty description="暂无问答记录" :image-size="60" /></template>
          </el-table>

          <div class="aud-pager" v-if="qa.total > qa.size">
            <el-pagination
              size="small"
              layout="prev, pager, next, total"
              :total="qa.total"
              :page-size="qa.size"
              :current-page="qa.page"
              @current-change="loadQa"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="会话" name="sessions">
          <el-table :data="sessions.list" v-loading="sessions.loading" size="small" class="aud-table">
            <el-table-column prop="session_id" label="ID" width="80" />
            <el-table-column label="会话名称" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <el-button link type="primary" @click="openMessages(row)">{{ row.session_name || '未命名' }}</el-button>
                <el-tag v-if="row.archived_at" size="small" type="info">已归档</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="record_count" label="消息数" width="90" />
            <el-table-column label="创建时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.create_time) }}</template>
            </el-table-column>
            <el-table-column label="最近活跃" width="150">
              <template #default="{ row }">{{ fmtTime(row.last_active_at) }}</template>
            </el-table-column>
            <template #empty><el-empty description="暂无会话" :image-size="60" /></template>
          </el-table>
          <div class="aud-pager" v-if="sessions.total > sessions.size">
            <el-pagination
              size="small"
              layout="prev, pager, next, total"
              :total="sessions.total"
              :page-size="sessions.size"
              :current-page="sessions.page"
              @current-change="loadSessions"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="文档" name="docs">
          <p class="aud-note">知识库为共享库，下表按该用户的文档操作审计反推。</p>
          <el-table :data="docs.list" v-loading="docs.loading" size="small" class="aud-table">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="动作" width="120">
              <template #default="{ row }">
                {{ { DOC_UPLOAD: '上传', DOC_DELETE: '删除', DOC_DOWNLOAD: '下载', REPARSE: '重解析' }[row.action] || row.action }}
              </template>
            </el-table-column>
            <el-table-column prop="target_id" label="文档 ID" width="110" />
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.result === 1 ? 'success' : 'danger'">
                  {{ row.result === 1 ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="详情" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.detail ? JSON.stringify(row.detail) : '—' }}</template>
            </el-table-column>
            <template #empty><el-empty description="暂无文档操作" :image-size="60" /></template>
          </el-table>
          <div class="aud-pager" v-if="docs.total > docs.size">
            <el-pagination
              size="small"
              layout="prev, pager, next, total"
              :total="docs.total"
              :page-size="docs.size"
              :current-page="docs.page"
              @current-change="loadDocs"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="反馈" name="feedback">
          <el-table :data="feedback.list" v-loading="feedback.loading" size="small" class="aud-table">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="评价" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.rating === 1 ? 'success' : 'danger'">
                  {{ row.rating === 1 ? '赞' : '踩' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="原因" width="120">
              <template #default="{ row }">{{ row.reason_text || row.reason_code || '—' }}</template>
            </el-table-column>
            <el-table-column label="问题" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.query_snapshot || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="70" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" type="primary" :disabled="!row.trace_id" @click="openTrace(row)">
                  链路
                </el-button>
              </template>
            </el-table-column>
            <template #empty><el-empty description="暂无反馈" :image-size="60" /></template>
          </el-table>
          <div class="aud-pager" v-if="feedback.total > feedback.size">
            <el-pagination
              size="small"
              layout="prev, pager, next, total"
              :total="feedback.total"
              :page-size="feedback.size"
              :current-page="feedback.page"
              @current-change="loadFeedback"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="活动流" name="activity">
          <div class="aud-filter">
            <el-select v-model="activityType" size="small" clearable placeholder="全部类型" class="f-select">
              <el-option label="问答" value="qa" />
              <el-option label="登录" value="login" />
              <el-option label="文档" value="doc" />
              <el-option label="导出" value="export" />
              <el-option label="管理" value="admin" />
              <el-option label="其他" value="other" />
            </el-select>
            <el-button size="small" type="primary" @click="loadActivity(1)">查询</el-button>
            <span class="f-total">共 {{ activity.total }} 条</span>
          </div>
          <el-timeline v-loading="activity.loading" class="aud-timeline">
            <el-timeline-item
              v-for="(item, idx) in activity.list"
              :key="idx"
              :timestamp="fmtTime(item.ts)"
              placement="top"
            >
              <div class="tl-row">
                <el-tag size="small" effect="plain">{{ ACT_TYPE_LABEL[item.type] || item.type }}</el-tag>
                <span class="tl-title">{{ item.title || '—' }}</span>
                <el-tag v-if="item.result && item.result !== 'ok'" size="small" type="danger">
                  {{ statusLabel(item.result) }}
                </el-tag>
              </div>
              <div v-if="item.detail" class="tl-detail">{{ item.detail }}</div>
            </el-timeline-item>
            <el-empty v-if="!activity.loading && !activity.list.length" description="暂无活动" :image-size="60" />
          </el-timeline>
          <div class="aud-pager" v-if="activity.total > activity.size">
            <el-pagination
              size="small"
              layout="prev, pager, next, total"
              :total="activity.total"
              :page-size="activity.size"
              :current-page="activity.page"
              @current-change="loadActivity"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <TraceDrawer
      v-model="traceOpen"
      :trace-id="traceId"
      admin-view
      :owner-label="ownerLabel"
    />

    <el-dialog
      v-model="msgOpen"
      :title="`会话「${msgSession?.session_name || '未命名'}」消息（只读）`"
      width="min(820px, 95vw)"
      append-to-body
    >
      <div class="aud-msg-banner">
        正在查看用户「{{ ownerLabel || `#${userId}` }}」的会话，本次查看已记录审计日志
      </div>
      <el-skeleton v-if="msgLoading" :rows="6" animated />
      <el-scrollbar v-else max-height="60vh">
        <div v-for="m in msgData.list" :key="m.record_id" class="msg-item">
          <div class="msg-meta">{{ fmtTime(m.create_time) }} · {{ modeLabel(m.answer_mode) }}</div>
          <div class="msg-q">问：{{ m.query || '—' }}</div>
          <div class="msg-a">答：{{ m.answer || '—' }}</div>
        </div>
        <el-empty v-if="!msgData.list.length" description="暂无消息" :image-size="60" />
      </el-scrollbar>
      <template #footer>
        <span class="msg-total">共 {{ msgData.total }} 条</span>
        <el-button @click="msgOpen = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.aud-shell { padding: 18px 22px 28px; }
.aud-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.aud-kicker { font-size: 12px; color: var(--text-secondary); }
.aud-head h2 { margin: 4px 0 8px; font-size: 20px; }
.aud-tags { display: flex; gap: 8px; flex-wrap: wrap; }
.aud-banner {
  margin: 14px 0 6px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #e6a23c;
  background: rgba(230, 162, 60, 0.1);
  color: #b88230;
  font-size: 12px;
  line-height: 1.5;
}
.aud-tabs { margin-top: 10px; }
.aud-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.aud-cell {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--panel);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.aud-cell label { font-size: 12px; color: var(--text-secondary); }
.aud-cell b { font-size: 15px; font-weight: 600; }
.aud-cell.aud-warn b { color: #b88230; }
.aud-note { margin: 12px 0 0; font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.aud-filter { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.f-input { width: 220px; }
.f-select { width: 130px; }
.f-total { font-size: 12px; color: var(--text-secondary); }
.aud-table { width: 100%; }
.del-tag { margin-left: 8px; }
.aud-pager { display: flex; justify-content: flex-end; margin-top: 10px; }
.aud-timeline { padding-top: 6px; }
.tl-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tl-title { font-size: 13px; }
.tl-detail { margin-top: 4px; font-size: 12px; color: var(--text-secondary); word-break: break-all; }
.aud-msg-banner {
  margin-bottom: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid #e6a23c;
  background: rgba(230, 162, 60, 0.1);
  color: #b88230;
  font-size: 12px;
}
.msg-item { padding: 10px 0; border-bottom: 1px solid var(--border); }
.msg-meta { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.msg-q { font-size: 13px; font-weight: 600; margin-bottom: 4px; word-break: break-word; }
.msg-a { font-size: 13px; white-space: pre-wrap; word-break: break-word; color: var(--text-secondary); }
.msg-total { float: left; font-size: 12px; color: var(--text-secondary); line-height: 32px; }

@media (max-width: 640px) {
  .aud-shell { padding: 14px 14px 22px; }
  .aud-head h2 { font-size: 17px; }
  .f-input, .f-select { width: 100%; }
}
</style>
