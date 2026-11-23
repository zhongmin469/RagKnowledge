<script setup>
// 顶栏用户区：头像 + 昵称 + 下拉（个人设置 / 修改密码 / 退出登录）。
// 个人设置：身份卡 + 昵称可编辑 + 账号信息表 + 权限说明。
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { updateProfile } from '../api/auth'
import { exportMyLogs, deleteMyLogs } from '../api/ioLogs'

const props = defineProps({
  user: { type: Object, required: true }
})

const emit = defineEmits(['password', 'logout', 'profile-updated'])

const profileVisible = ref(false)
const savingNickname = ref(false)
const nicknameError = ref('')

const displayName = computed(() => props.user.display_name || props.user.username || '未命名')
const roleLabel = computed(() => (props.user.role === 'admin' ? '管理员' : '普通用户'))
const initial = computed(() => (displayName.value || '?').trim().slice(0, 1).toUpperCase())

const roleHint = computed(() =>
  props.user.role === 'admin'
    ? '可管理知识库文档与账号、修改系统参数、查询全部业务库意图。'
    : '可进行知识库问答与本人范围内的业务库查询，文档维护与参数配置仅管理员可用。'
)

const infoRows = computed(() => [
  { label: '登录账号', value: props.user.username || '—' },
  { label: '角色', value: roleLabel.value },
  { label: '账号 ID', value: props.user.user_id != null ? String(props.user.user_id) : '—' }
])

const nickname = ref(displayName.value)
watch(displayName, (v) => {
  nickname.value = v
})

const nicknameDirty = computed(() => nickname.value.trim() !== displayName.value)
const nicknameInvalid = computed(() => {
  const v = nickname.value.trim()
  return v.length === 0 || v.length > 32
})

function onCommand(command) {
  if (command === 'password') {
    emit('password')
    return
  }
  if (command === 'logout') {
    emit('logout')
    return
  }
  if (command === 'profile') {
    nickname.value = displayName.value
    nicknameError.value = ''
    profileVisible.value = true
  }
}

async function saveNickname() {
  const v = nickname.value.trim()
  if (!v) {
    nicknameError.value = '昵称不能为空'
    return
  }
  if (v.length > 32) {
    nicknameError.value = '昵称最多 32 个字符'
    return
  }
  nicknameError.value = ''
  savingNickname.value = true
  try {
    const data = await updateProfile({ display_name: v })
    nickname.value = data.display_name || v
    emit('profile-updated', data)
    ElMessage.success('昵称已更新')
  } catch (err) {
    nicknameError.value = err?.message || '昵称更新失败，请重试'
  } finally {
    savingNickname.value = false
  }
}

function openPasswordFromProfile() {
  profileVisible.value = false
  emit('password')
}

// ---- 数据与隐私（v3 / WP3 §5.6）：导出/删除本人运行日志 ----
const exportingLogs = ref(false)
const deletingLogs = ref(false)

async function onExportLogs() {
  if (exportingLogs.value) return
  exportingLogs.value = true
  try {
    await exportMyLogs()
    ElMessage.success('已开始下载对话记录 JSON')
  } catch {
    // 统一拦截器提示
  } finally {
    exportingLogs.value = false
  }
}

async function onDeleteLogs() {
  if (deletingLogs.value) return
  try {
    await ElMessageBox.confirm(
      '删除后，你本人将无法再查看或导出这些问答记录，且无法恢复；为满足审计与排障要求，管理员在日志保留期内（当前 90 天）仍可查看这批记录。确认继续？',
      '删除我的运行日志',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  deletingLogs.value = true
  try {
    const data = await deleteMyLogs()
    ElMessage.success(`已从你的视角删除 ${data?.removed ?? 0} 条运行日志`)
  } catch {
    // 统一拦截器提示
  } finally {
    deletingLogs.value = false
  }
}
</script>

<template>
  <el-dropdown trigger="click" placement="bottom-end" @command="onCommand">
    <button type="button" class="user-trigger" aria-label="账号菜单">
      <el-avatar :size="26" class="avatar">{{ initial }}</el-avatar>
      <span class="user-name">{{ displayName }}</span>
      <svg class="chevron" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M2 4.5L6 8.5L10 4.5" fill="none" stroke="currentColor" stroke-width="1.4" />
      </svg>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <div class="dropdown-head">
          <div class="head-name">{{ displayName }}</div>
          <div class="head-role">{{ roleLabel }}</div>
        </div>
        <el-dropdown-item command="profile">个人设置</el-dropdown-item>
        <el-dropdown-item command="password" divided>修改密码</el-dropdown-item>
        <el-dropdown-item command="logout">退出登录</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <el-dialog
    v-model="profileVisible"
    title="个人设置"
    width="min(460px, 92vw)"
    align-center
  >
    <div class="profile-id">
      <el-avatar :size="52" class="id-avatar">{{ initial }}</el-avatar>
      <div class="id-text">
        <div class="id-name">{{ displayName }}</div>
        <div class="id-sub">{{ props.user.username }} · {{ roleLabel }}</div>
      </div>
      <el-tag :type="props.user.role === 'admin' ? 'warning' : 'info'" effect="plain" size="small">
        {{ props.user.role === 'admin' ? '超级用户' : '普通用户' }}
      </el-tag>
    </div>

    <div class="field-block">
      <div class="field-head">
        <span class="field-label">昵称</span>
        <span class="field-tip">显示在顶栏与消息气泡上，最长 32 个字符</span>
      </div>
      <div class="field-line">
        <el-input
          v-model="nickname"
          maxlength="32"
          show-word-limit
          placeholder="请输入昵称"
          aria-label="昵称"
          :disabled="savingNickname"
          @keyup.enter="nicknameDirty && !nicknameInvalid && saveNickname()"
        />
        <el-button
          type="primary"
          :loading="savingNickname"
          :disabled="!nicknameDirty || nicknameInvalid"
          @click="saveNickname"
        >保存</el-button>
      </div>
      <div v-if="nicknameError" class="field-error">{{ nicknameError }}</div>
    </div>

    <div class="info-table">
      <div v-for="row in infoRows" :key="row.label" class="info-row">
        <span class="info-label">{{ row.label }}</span>
        <span class="info-value">{{ row.value }}</span>
      </div>
    </div>

    <div class="data-block">
      <div class="field-head">
        <span class="field-label">数据与隐私</span>
        <span class="field-tip">运行日志仅用于排障，默认保留 90 天</span>
      </div>
      <div class="data-actions">
        <el-button size="small" :loading="exportingLogs" @click="onExportLogs">导出我的对话记录（JSON）</el-button>
        <el-button size="small" type="danger" plain :loading="deletingLogs" @click="onDeleteLogs">
          删除我的全部日志
        </el-button>
      </div>
      <div class="data-note">
        管理员具备审计查看权：删除仅让你本人不可见，管理员在保留期内仍可查看这批记录；管理员每次查看他人数据都会写入审计日志。
      </div>
    </div>

    <div class="role-hint">
      <div class="hint-title">权限说明</div>
      <div class="hint-text">{{ roleHint }}</div>
    </div>

    <template #footer>
      <el-button @click="openPasswordFromProfile">修改密码</el-button>
      <el-button type="primary" @click="profileVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.user-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 8px 0 4px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font: inherit;
}

.user-trigger:hover {
  border-color: var(--border);
  background: var(--hover-bg, rgba(127, 127, 127, 0.08));
}

.avatar {
  background: var(--brand-soft, #eaf1ff);
  color: var(--brand, #2f6fed);
  font-size: 13px;
}

.user-name {
  font-size: 13px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron {
  width: 12px;
  height: 12px;
  color: var(--text-secondary);
}

.dropdown-head {
  padding: 8px 16px 6px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}

.head-name {
  font-size: 13px;
  font-weight: 600;
}

.head-role {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ---- 个人设置弹层 ---- */
.profile-id {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 4px 0 16px;
}

.id-avatar {
  flex: none;
  background: var(--brand-soft, #eaf1ff);
  color: var(--brand, #2f6fed);
  font-size: 20px;
  font-weight: 600;
}

.id-text {
  min-width: 0;
  flex: 1;
}

.id-name {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.id-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-secondary);
}

.field-block {
  margin-bottom: 16px;
}

.field-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 600;
}

.field-tip {
  font-size: 11px;
  color: var(--text-secondary);
}

.field-line {
  display: flex;
  gap: 8px;
}

.field-error {
  margin-top: 4px;
  font-size: 11px;
  color: var(--danger, #f56c6c);
}

.info-table {
  border: 1px solid var(--border);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  flex: none;
  font-size: 12px;
  color: var(--text-secondary);
}

.info-value {
  min-width: 0;
  font-size: 13px;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-hint {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--radius-md, 8px);
  background: var(--primary-light, #ecf5ff);
}

/* ---- 数据与隐私 ---- */
.data-block {
  margin-top: 16px;
}

.data-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.data-note {
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.hint-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary, #2f6fed);
}

.hint-text {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text);
}

/* 窄屏只留头像，避免右侧被裁切 */
@media (max-width: 992px) {
  .user-name {
    display: none;
  }

  .chevron {
    display: none;
  }
}
</style>
