<script setup>
// 根组件：未登录显示登录页；登录后按角色展示聊天与管理员入口
// 前端隐藏普通用户不可见菜单；最终权限仍由后端强制校验
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import DocsView from './views/DocsView.vue'
import UsersView from './views/UsersView.vue'
import ConfigView from './views/ConfigView.vue'
import IoLogView from './views/IoLogView.vue'
import AuditLogView from './views/AuditLogView.vue'
import WorkflowView from './views/WorkflowView.vue'
import ChatView from './views/ChatView.vue'
import LoginView from './views/LoginView.vue'
import StatusDots from './components/StatusDots.vue'
import UserMenu from './components/UserMenu.vue'
import ChangePasswordDialog from './components/ChangePasswordDialog.vue'
import { fetchMe, logout as logoutApi } from './api/auth'
import { fetchSystemStatus } from './api/status'
import { setErrorHandler } from './api/http'
import { AGENT_NAME, AGENT_TAGLINE } from './config/brand.js'
import { useTheme } from './composables/useTheme.js'
import { clearDraftsStorage } from './composables/draftStore'

const user = ref(null)
const checking = ref(true)
const current = ref('chat')
const pwdVisible = ref(false)
const pwdButtonRef = ref(null)
const AUTH_CHECK_TIMEOUT_MS = 8000
const { theme, toggleTheme, initTheme } = useTheme()

// 部署环境徽标：开发构建显示 DEV，生产构建显示 PROD
const envLabel = import.meta.env.PROD ? 'PROD' : 'DEV'

// 窄屏（<992px）导航收进「更多」下拉，保证顶栏严格单行
const isNarrow = ref(false)
const narrowQuery = typeof window !== 'undefined' ? window.matchMedia('(max-width: 992px)') : null
function syncNarrow(event) {
  isNarrow.value = event ? event.matches : !!narrowQuery?.matches
}

// 超窄屏（<600px，手机）：连「更多」都放不下，整个导航改成气泡菜单按钮
const isTiny = ref(false)
const tinyQuery = typeof window !== 'undefined' ? window.matchMedia('(max-width: 600px)') : null
function syncTiny(event) {
  isTiny.value = event ? event.matches : !!tinyQuery?.matches
}

// 能力状态（知识库 / 联网 / 业务库），60 秒刷新一次，改完配置能自然反映到灯上
const status = ref(null)
const statusLoading = ref(false)
let statusTimer = null

const menus = computed(() => {
  const list = [{ key: 'chat', label: '智能对话' }, { key: 'workflow', label: '任务中心' }]
  if (user.value && user.value.role === 'admin') {
    list.push({ key: 'docs', label: '知识库管理' })
    list.push({ key: 'users', label: '用户管理' })
    list.push({ key: 'config', label: '配置中心' })
    list.push({ key: 'io-logs', label: '运行日志' })
    list.push({ key: 'audit-logs', label: '操作审计' })
  }
  return list
})
const visibleMenus = computed(() => (isNarrow.value ? menus.value.slice(0, 2) : menus.value))
const hiddenMenus = computed(() => (isNarrow.value ? menus.value.slice(2) : []))
// 当前页若被收进「更多」，让「更多」保持高亮，避免导航看不出当前位置
const navActive = computed(() =>
  hiddenMenus.value.some((m) => m.key === current.value) ? 'more' : current.value
)

function bindErrorHandler() {
  setErrorHandler((err) => {
    const unauthorized = err.bizCode === 40101 || err.httpStatus === 401
    if (unauthorized) {
      // 仅在“已登录但登录态失效”时提示并回登录页；登录页自身的错误由 LoginView 提示
      if (user.value) {
        user.value = null
        current.value = 'chat'
        pwdVisible.value = false
        clearDraftsStorage()
        ElMessage.warning('登录已过期，请重新登录')
      }
      return
    }
    const forbidden = err.bizCode === 40303 || err.httpStatus === 403
    ElMessage.error(forbidden ? '没有操作权限（仅管理员可执行）' : err.message || '请求失败')
  })
}

async function loadStatus() {
  if (!user.value) return
  statusLoading.value = true
  try {
    status.value = await fetchSystemStatus()
  } catch {
    // 能力状态只是顶栏提示，读不到不影响主流程，保持上一次结果
  } finally {
    statusLoading.value = false
  }
}

function startStatusPolling() {
  stopStatusPolling()
  statusTimer = setInterval(loadStatus, 60 * 1000)
}

function stopStatusPolling() {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
}

onMounted(async () => {
  // 主题/错误处理属于非关键初始化，即使异常也不能阻断登录态校验，
  // 否则 checking 会永远为 true，界面停留在“正在校验登录状态…”
  try {
    initTheme()
  } catch (e) {
    console.error('主题初始化失败', e)
  }
  syncNarrow()
  syncTiny()
  narrowQuery?.addEventListener?.('change', syncNarrow)
  tinyQuery?.addEventListener?.('change', syncTiny)
  bindErrorHandler()
  await reloadMe()
})

onBeforeUnmount(() => {
  narrowQuery?.removeEventListener?.('change', syncNarrow)
  tinyQuery?.removeEventListener?.('change', syncTiny)
  stopStatusPolling()
})

async function reloadMe() {
  checking.value = true
  const mePromise = fetchMe()
  mePromise.catch(() => {})
  try {
    user.value = await Promise.race([
      mePromise,
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error('AUTH_CHECK_TIMEOUT')), AUTH_CHECK_TIMEOUT_MS)
      })
    ])
    if (user.value) {
      await loadStatus()
      startStatusPolling()
    }
  } catch {
    // 登录态校验失败、超时或网络不可用时回登录页，避免一直停留在校验遮罩
    user.value = null
  } finally {
    checking.value = false
  }
}

async function onLoggedIn(profile) {
  user.value = profile
  current.value = 'chat'
  await loadStatus()
  startStatusPolling()
}

// 个人设置里改完昵称：后端已返回最新 profile，直接替换本地状态，顶栏/气泡即时刷新
function onProfileUpdated(profile) {
  if (profile && profile.user_id) user.value = profile
}

async function onLogout() {
  try {
    await logoutApi()
  } catch {
    // 本地状态仍需清理，避免停留在已登录界面
  }
  user.value = null
  current.value = 'chat'
  pwdVisible.value = false
  status.value = null
  stopStatusPolling()
  clearDraftsStorage()
}

function onSelect(key) {
  if (!key || key === 'more') return
  current.value = key
}

function openPasswordDialog() {
  pwdButtonRef.value = document.activeElement
  pwdVisible.value = true
}

async function onPasswordDialogClosed() {
  await nextTick()
  pwdButtonRef.value?.focus?.()
}
</script>

<template>
  <div v-if="checking" class="checking-tip">正在校验登录状态…</div>
  <LoginView v-else-if="!user" @success="onLoggedIn" />

  <el-container v-else class="app-shell" direction="vertical">
    <el-header class="app-header" height="60px">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">知</div>
        <div class="brand-text">
          <span class="brand-name">{{ AGENT_NAME }}</span>
          <span class="brand-tagline">{{ AGENT_TAGLINE }}</span>
        </div>
        <span class="env-badge" :title="envLabel === 'DEV' ? '开发环境' : '生产环境'">{{ envLabel }}</span>
      </div>

      <el-menu
        v-if="!isTiny"
        :default-active="navActive"
        mode="horizontal"
        class="nav"
        @select="onSelect"
      >
        <el-menu-item v-for="m in visibleMenus" :key="m.key" :index="m.key">
          {{ m.label }}
        </el-menu-item>
        <el-menu-item v-if="hiddenMenus.length" index="more" class="more-item">
          <el-dropdown trigger="click" placement="bottom-end" @command="onSelect">
            <span class="more-trigger">更多</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="m in hiddenMenus" :key="m.key" :command="m.key">
                  {{ m.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-menu-item>
      </el-menu>

      <div class="actions">
        <!-- 手机端导航：整组菜单收进一个气泡菜单按钮 -->
        <el-dropdown v-if="isTiny" trigger="click" placement="bottom-start" @command="onSelect">
          <button type="button" class="icon-btn" aria-label="打开导航菜单">
            <svg viewBox="0 0 24 24" class="icon" aria-hidden="true">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              />
            </svg>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="m in menus"
                :key="m.key"
                :command="m.key"
                :class="{ 'is-current': current === m.key }"
              >
                {{ m.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <StatusDots :status="status" :loading="statusLoading" />

        <span class="action-divider" aria-hidden="true"></span>

        <el-tooltip
          :content="theme === 'dark' ? '切换到浅色主题' : '切换到暗色主题'"
          placement="bottom"
          :show-after="200"
        >
          <button
            type="button"
            class="icon-btn"
            :aria-label="theme === 'dark' ? '切换到浅色主题' : '切换到暗色主题'"
            @click="toggleTheme"
          >
            <svg v-if="theme === 'dark'" viewBox="0 0 24 24" class="icon" aria-hidden="true">
              <circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="1.8" />
              <path
                d="M12 3v2M12 19v2M3 12h2M19 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              />
            </svg>
            <svg v-else viewBox="0 0 24 24" class="icon" aria-hidden="true">
              <path
                d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              />
            </svg>
          </button>
        </el-tooltip>

        <UserMenu
          :user="user"
          @password="openPasswordDialog"
          @logout="onLogout"
          @profile-updated="onProfileUpdated"
        />
      </div>
    </el-header>

    <el-alert
      type="info"
      :closable="false"
      title="企业文档智能问答（RAG + Agent）：知识库全局共享；会话按用户隔离；文档维护、索引重建与账号管理仅限管理员。"
      class="stage-tip"
    />

    <el-main :class="['app-main', { 'chat-mode': current === 'chat' }]">
      <UsersView v-if="current === 'users' && user.role === 'admin'" :current-user-id="user.user_id" />
      <ConfigView v-else-if="current === 'config' && user.role === 'admin'" />
      <IoLogView v-else-if="current === 'io-logs' && user.role === 'admin'" />
      <AuditLogView v-else-if="current === 'audit-logs' && user.role === 'admin'" />
      <WorkflowView v-else-if="current === 'workflow'" />
      <DocsView v-else-if="current === 'docs' && user.role === 'admin'" />
      <ChatView v-else :current-user="user" />
    </el-main>

    <ChangePasswordDialog v-model:visible="pwdVisible" :username="user.username" @closed="onPasswordDialogClosed" />
  </el-container>
</template>

<style scoped>
/* 整页固定高度：对话页内部自己滚动，输入框永远贴在首屏底部。
   dvh 兼容移动端浏览器地址栏收起/展开；不支持时退回 100vh。 */
.app-shell {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.app-header {
  display: flex;
  align-items: center;
  flex: 0 0 60px;
  gap: 20px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  /* 明确单行：任何子元素都不允许把顶栏撑高 */
  min-width: 0;
  overflow: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 0 1 auto;
}

.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--brand, #2f6fed);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.15;
}

.brand-name {
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.brand-tagline {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.env-badge {
  flex: 0 0 auto;
  font-size: 10px;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

.nav {
  flex: 1 1 auto;
  min-width: 0;
  border-bottom: none;
  height: 60px;
}

.more-trigger {
  display: inline-block;
  padding: 0 2px;
  cursor: pointer;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
  margin-left: auto;
}

.action-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
}

/* 顶栏图标按钮统一 32×32、圆角 8 */
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.icon-btn:hover {
  border-color: var(--border);
  background: var(--hover-bg, rgba(127, 127, 127, 0.08));
}

.icon {
  width: 18px;
  height: 18px;
}

.stage-tip {
  margin: 8px 16px 0;
  flex: 0 0 auto;
}

.app-main {
  flex: 1 1 auto;
  min-height: 0;
  padding: 12px 16px;
  background: var(--bg);
  overflow: auto;
}

/* 对话页：主体不滚动，把剩余高度整体交给对话布局，输入框因此钉在底部 */
.app-main.chat-mode {
  overflow: hidden;
}

.checking-tip {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

@media (max-width: 992px) {
  .app-header {
    gap: 10px;
    padding: 0 12px;
  }

  .brand-tagline {
    display: none;
  }

  .brand-name {
    font-size: 13px;
  }

  .nav {
    flex: 1 1 auto;
  }

  /* 窄屏隐藏公告条，把高度留给对话区（输入框必须留在首屏） */
  .stage-tip {
    display: none;
  }

  .actions {
    gap: 8px;
  }

  .action-divider {
    display: none;
  }

  .app-main {
    padding: 8px;
  }
}
</style>
