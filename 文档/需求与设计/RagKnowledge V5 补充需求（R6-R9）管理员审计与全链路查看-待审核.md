# RagKnowledge V5 补充需求（R6–R9）：管理员审计与用户全链路查看

> 版本：v5.0 补充稿（**待审核，尚未并入** `RagKnowledge 能力增强需求文档 v5.md`）
> 编写日期：2026-11-20
> 触发问题：用户菜单「删除我的运行日志」确认文案为“删除后管理员也无法查到”，与“管理员可查其他用户全部操作、问答与运行日志链路”的产品定位冲突
> 基线：V5-1、V5-2 已验收；V5-3 自主规划未开始；`pytest 294 passed / 1 skipped`
> 状态：**等待确认第 5 节 6 个决策点后，再并入 v5 正文与阶段表**

---

## 0. 本轮输入与需求映射

| 用户输入 | 本稿编号 | 需求摘要 | 优先级 |
|---|---|---|---:|
| 「删除我的运行日志」的提示逻辑要优化 | R6 | 纠正删除语义与确认文案：用户删除后管理员在保留期内仍可查 | P0 |
| 管理员可查其他用户的所有操作 | R8 | 补齐 `operation_log` 查询/导出接口与管理端页面 | P1 |
| 管理员可查其他用户的问答 | R7 | 新增按用户维度的问答记录、会话、消息、文档只读查询 | P1 |
| 管理员可查运行日志链路 | R7 | 用户详情页直达该用户每轮 `trace_id`，复用现有链路详情 | P1 |
| “用户的所有信息”要成体系 | R7/R8/R9 | 用户全景页 + 统一活动时间流 + 管理员查看行为反审计 | P1 |

---

## 1. 目标与边界

### 1.1 目标

1. **口径自洽**：用户删除自己的运行日志，与“管理员具备审计与排障查看权”不再互相打脸，界面文案如实描述真实结果。
2. **一个入口看全一个用户**：管理员在用户管理页点进任一用户，可看到该账号的概览、问答记录、会话与消息、运行日志链路、上传/删除文档、反馈、登录与操作审计。
3. **审计可查**：`operation_log` 从“只写不读”变成可筛选、可导出、可追溯的管理端能力。
4. **查看留痕**：管理员查看他人问答原文或链路详情的行为本身必须写审计，防止管理员权限被滥用且事后无法追查。

### 1.2 边界

- 管理员对他人数据**只读**：不能修改、删除、代发消息、冒用身份；不提供“以该用户身份登录”。
- 不展示密码哈希、令牌、完整 IP（沿用 `ip_masked` 掩码）、内部密钥与 SQL 文本。
- 不改变普通用户的隔离语义：`member` 访问任何 `/api/admin/*` 一律 `40303`；用户仍只能看本人数据。
- 不做管理员实时监听会话、在线状态、屏幕录制。
- 不做跨用户聚合 BI 报表、按部门/组织架构分组、审计告警规则（另立需求）。
- 不新增审计内容中的聊天正文；`operation_log` 仍保持“不含聊天内容”的设计约束，问答原文只存在于 `chat_io_log` / `chat_record`。

---

## 2. 现状核对（已读代码结论）

| # | 现状事实 | 证据位置 | 与本需求的差距 |
|---:|---|---|---|
| 1 | 删除本人日志为**物理删除** `chat_io_log` 与 `llm_call_log` 两表，返回删除条数 | `backend/services/io_log.py:594-606`、`backend/routers/user_io.py:40-44` | 删除后管理员确实查不到，与“管理员可查”冲突 |
| 2 | 确认文案明写“删除后管理员也无法查到” | `frontend/src/components/UserMenu.vue:112` | 文案与产品口径冲突 |
| 3 | 删除动作**没有写任何审计** | `user_io.py` 无 `audit.log_operation` 调用 | 谁在何时删了多少条无处可查 |
| 4 | 删除会话会连带物理删除该会话的全部 `chat_io_log` | `backend/routers/session.py:153` → `delete_session_logs` | 用户删会话后，管理员侧链路同样断档（需一并纳入 R6 口径） |
| 5 | `chat_io_log` 已含 `query/query_rewritten/answer/tool_chain/context_usage/status/error_code/elapsed_ms/first_token_ms/total_tokens/ip_masked/ua/trace_id/user_id/session_id/record_id` | `io_log.py:99-152` | 字段足够支撑管理员查看，无需扩列（除删除标记） |
| 6 | 管理端已有 I/O 日志列表/统计/导出/trace 详情，支持 `user_id` 筛选 | `backend/routers/admin_io.py`、`frontend/src/views/IoLogView.vue` | 能力分散在“日志页”，没有“用户维度”聚合入口 |
| 7 | 管理员 trace 详情无 owner 校验（可查任意人 trace） | `admin_io.py:118-124` → `io_log.get_detail` | 链路能力已具备，缺前端入口与留痕 |
| 8 | 用户管理仅列表/创建/启禁用/重置密码，无详情页 | `backend/routers/admin.py`、`frontend/src/views/UsersView.vue` | 缺口核心 |
| 9 | 会话与消息严格按 `user_id` 校验（`get_session_for_user` / `list_records`） | `backend/services/chat_store.py` | 无任何管理员跨用户读取接口 |
| 10 | `operation_log` 有 `actor_user_id/action/target_type/target_id/result/detail/created_at`，但**没有任何查询接口** | `backend/init_db.sql:79-91`；全库仅 `audit.log_operation` 写入 | 审计写入 19 类动作，管理员一条也看不到 |
| 11 | 审计动作已覆盖登录/改密/昵称/文档上传删除下载/重解析/重建索引/用户管理/配置更新/业务查询/业务导出 | `services/audit.py` 常量 + 各调用点 | 缺：删除本人日志、导出本人日志、会话删除、管理员查看与导出 |
| 12 | 反馈表 `chat_feedback` 有 `user_id/session_id/record_id/trace_id/rating` | `services/feedback_store.py:15-35` | 管理端反馈页未支持按 `user_id` 筛选 |
| 13 | `document` 表**没有上传者字段**，知识库为共享库；上传者只记在 `operation_log`（`DOC_UPLOAD` + `target_id=doc_id`） | `backend/init_db.sql:19-33`；`routers/docs.py:93` | “某用户上传的文档”只能经审计反查，需在 UI 注明 |
| 14 | 运行日志保留期 `IO_LOG_RETENTION_DAYS` 默认 90 天，到期物理清理；`operation_log` 无清理任务 | `io_log.py:619-644`、`backend/config.py` | “管理员可查多久”需明确为保留期口径 |
| 15 | 管理端导出 I/O 日志、导出反馈均未写审计 | `admin_io.py:67-115`、`admin_feedback.py:34` | 管理员导出行为不可追溯 |

**结论**：底层数据基本够用，真正的缺口是 ①删除语义与文案、②跨用户只读查询接口、③审计查询接口、④查看/导出留痕、⑤前端用户详情入口。

---

## 3. 需求清单

| 编号 | 需求 | 后端 | 前端 | 依赖 |
|---|---|---|---|---|
| R6 | 删除本人运行日志的语义与文案纠正（含会话删除链路口径） | 是 | 是 | 需先定第 5 节决策 1 |
| R7 | 管理员用户全景与跨用户只读查询（概览/问答/会话/消息/文档/反馈/活动流） | 是 | 是 | R6 的可见性过滤 |
| R8 | 操作审计查询与导出 + 审计动作补全 | 是 | 是 | 无 |
| R9 | 管理员查看行为反审计与合规约束 | 是 | 是 | R7/R8 |

---

## 4. 详细需求

### R6 删除本人运行日志：语义与文案纠正

#### R6.1 需求描述

用户点击「删除我的运行日志」时，系统必须同时满足两条产品要求：

1. 用户本人删除后，在其视角下这些问答记录不可再查看、不可再导出；
2. 管理员在日志保留期内，仍可因审计/排障查阅这些记录及其链路。

因此“删除”不再等价于“数据库物理行消失”。**具体采用哪种实现口径，取决于第 5 节决策 1。**

#### R6.2 三种候选口径（供裁决）

| 方案 | 用户侧结果 | 管理员侧结果 | 改造成本 | 合规观感 |
|---|---|---|---|---|
| **A 保留期软删除（推荐）** | 列表/导出/trace 详情均不可见；再次删除返回 0 条 | 仍可见完整问答原文与链路，列表中标记「用户已删除」 | 中：加列 + 全查询过滤 + 前端标记 | 需在文案中如实说明管理员仍可查 |
| **C 正文脱敏归档（折中）** | 同上，不可见 | 可查链路骨架（时间/意图/状态/耗时/token/trace_id/会话），问答正文替换为「用户已删除」 | 中：删除前就地 UPDATE 正文与 `tool_chain` | 隐私最强，但管理员失去“问答原文”能力 |
| **B 彻底物理删除** | 不可见 | 不可见 | 低：只改文案 | **不满足本轮需求**，仅作为对照 |

推荐 **A**：与“管理员可查其他用户所有问答、运行日志链路”的产品定位一致；代价是用户隐私承诺从“彻底删除”降级为“保留期内管理员可查”，必须由用户在界面上明确知情。

#### R6.3 方案 A 实现规则

1. `chat_io_log` 新增可空列 `user_deleted_at TIMESTAMP NULL`（`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，幂等）。
2. `DELETE /api/me/io-logs` 语义改为：把该用户全部 `user_deleted_at IS NULL` 的行置为 `now()`；返回本次新标记条数。
3. 用户侧全部读取路径强制过滤 `user_deleted_at IS NULL`：`/api/me/io-logs/export`、`/api/me/io-logs/{trace_id}`；`user_export` 同步改。
4. 管理员侧读取不过滤，列表返回 `user_deleted` 布尔值与 `user_deleted_at`，前端以灰色标签「用户已删除」呈现。
5. `llm_call_log` 不单独标记：它只有调用元数据（模型、tokens、耗时），按 `trace_id` 关联，用户侧本就不可见，不涉及隐私正文。
6. 保留期到期由现有 `cleanup_expired` 物理删除（含已标记行），管理员可见窗口 = `IO_LOG_RETENTION_DAYS`（默认 90 天）。
7. **会话删除**：用户删除会话可选 `chat_io_log` 时，不再物理删除，同样置 `user_deleted_at`（否则管理员侧出现“用户删会话即断档”）。`chat_record` 与会话本体仍按现有逻辑删除，不在本需求扩范围。

#### R6.4 文案（方案 A 定稿建议）

标题：`删除我的运行日志`

正文：
> 删除后，**你本人**将无法再查看或导出这些问答记录，且无法恢复。
> 为满足审计与排障要求，**管理员在日志保留期内（当前 90 天）仍可查看这批记录**。
> 确认继续？

按钮：`确认删除` / `取消`。二次确认后展示结果：`已从你的视角删除 N 条记录`。

若最终采用方案 C，正文改为：“删除后你的问答原文不可恢复；系统仅保留不含问题与回答正文的链路记录（时间、意图、状态、耗时、token）供管理员审计。”

#### R6.5 审计补记录

新增动作 `USER_LOG_DELETE`：`actor=本人 user_id`、`target_type="io_log"`、`target_id=user_id`、`result=1`、`detail={"removed": n, "mode": "soft"}`。
新增动作 `SESSION_DELETE`（现有会话删除未留痕）：`detail={"session_id":..., "records": n, "io_logs": n}`。

#### R6.6 验收

- 用户删除后，本人导出文件 `count=0`、逐条 trace 详情返回 `40405`；
- 管理员列表仍能查到这些行，且带「用户已删除」标记，trace 详情可打开；
- 审计表出现 `USER_LOG_DELETE` 记录，`detail.removed` 与提示条数一致；
- 保留期清理后（造数把 `created_at` 回溯 91 天）物理行消失，管理员也查不到，文案与实现一致。

---

### R7 管理员用户全景与跨用户只读查询

#### R7.1 需求描述

用户管理页增加「查看」入口，进入**用户详情（抽屉或独立页）**，包含 6 个 Tab，全部只读：

| Tab | 内容 | 数据源 |
|---|---|---|
| 概览 | 账号信息、注册时间、最后登录、状态、角色、会话数、问答轮次、近 7/30 天问答数、累计 token、上传文档数、反馈数、已删除日志数 | `app_user` / `chat_session` / `chat_io_log` / `chat_feedback` / `operation_log` |
| 问答记录 | 按时间倒序：时间、会话名、问题、回答摘要、意图、链路模式、状态、耗时、首字、token、`trace_id`；点行打开链路详情 | `chat_io_log` |
| 会话 | 该用户全部会话（含归档）：名称、消息数、创建/最后活跃时间；点开只读消息列表 | `chat_session` / `chat_record` |
| 文档 | 该用户发起上传/删除/下载的文档动作（知识库为共享库，注明“按审计反查归属”） | `operation_log`（`DOC_*`） |
| 反馈 | 该用户点赞/点踩记录与理由，可跳对应 trace | `chat_feedback` |
| 活动流 | 统一时间线：登录、问答、上传、下载、删除、导出、配置与管理操作 | `operation_log` + `chat_io_log` 合并排序 |

#### R7.2 接口

全部 `require_admin`，路径前缀 `/api/admin/users/{user_id}`：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/overview` | 概览统计；目标账号不存在返回 `40403` |
| GET | `/qa` | 问答分页；参数 `page/size(≤100)/start/end/status/intent/keyword/include_deleted` |
| GET | `/sessions` | 会话分页；`keyword/archived/page/size` |
| GET | `/sessions/{session_id}/messages` | 只读消息分页；会话不属于该用户返回 `40402` |
| GET | `/documents` | 基于审计反查的文档动作分页；`action/start/end` |
| GET | `/feedback` | 反馈分页；`rating` |
| GET | `/activity` | 活动流分页；`start/end/type`；`type ∈ login/qa/doc/export/admin/other` |

复用与新增约定：

- trace 详情**复用** `GET /api/admin/io-logs/{trace_id}`，不新造接口；前端在用户详情内跳转时携带 `from_user=user_id` 以便留痕。
- 返回字段永不包含 `password_hash`、令牌、完整 IP；`ua` 截断 120 字符；`detail` 中的敏感键（如 `password`、`token`）后端统一剔除。
- 分页统一 `{total, list, page, size}`；空数据返回 `total=0` 而非 404。

#### R7.3 权限与隔离

| 场景 | 期望 |
|---|---|
| `member` 调任一 `/api/admin/users/{id}/*` | `40303`，HTTP 403 |
| 管理员查不存在的 `user_id` | `40403` |
| 管理员查看自己 | 允许（`overview` 正常返回），但 `qa` 走同一接口亦可，不做特殊拦截 |
| 管理员查他人会话的 `session_id` 不属于该用户 | `40402`，不泄露该会话存在性 |
| 已禁用账号 | 数据仍可查（审计需要），概览标注「已禁用」 |

#### R7.4 性能约束

- 概览接口 4–5 条聚合 SQL，单表最大 `chat_io_log`；依赖现有 `idx_io_log_user_time`，P95 ≤ 300ms（10 万行基线）。
- `qa` / `activity` 单页查询走 `user_id + created_at` 索引；禁止 `SELECT *`，禁止在 Python 端全量拉取后分页。
- 概览统计可加 60s 进程内缓存（可选，若实测超 300ms 再上）。

#### R7.5 前端交互

- `UsersView` 行尾新增「查看」按钮 → 打开宽度 `min(1080px, 96vw)` 的抽屉，移动端全屏。
- 抽屉头部：头像、`display_name`、`username`、角色徽标、状态徽标、最后登录时间。
- Tab 切换不重置筛选；每个 Tab 有独立空态与加载态。
- 问答行点击 `trace_id` → 复用 `TraceDrawer`（只读模式，顶部横幅「正在查看用户 xxx 的记录，本次查看已记录审计」）。
- 375 宽：Tab 横向可滚动，表格转卡片列表，无横向溢出。

#### R7.6 验收

- 管理员 A 查看成员 B：6 个 Tab 均有真实数据，`qa` 行点击可打开链路；
- B 无法访问 A 的任何数据（既有隔离回归）；
- `member` 访问 `overview` 返回 `40303`；
- 造数 200 会话 / 5000 轮问答下，`overview` ≤ 300ms、`qa` 分页 ≤ 200ms；
- 返回体不含 `password_hash`、完整 IP、令牌。

---

### R8 操作审计查询与审计补全

#### R8.1 需求描述

`operation_log` 已写入 19 类动作但没有任何读取入口，管理员无法回答“谁在什么时候删了哪篇文档、导出了谁的数据”。本项补齐查询与导出，并补全缺失动作。

#### R8.2 接口

| 方法 | 路径 | 参数 |
|---|---|---|
| GET | `/api/admin/audit-logs` | `page/size(≤100)`、`actor_user_id`、`target_user_id`、`action`、`target_type`、`result`、`start/end`、`keyword`（对 `detail` 与 `target_id` 模糊匹配） |
| GET | `/api/admin/audit-logs/export` | 同筛选，CSV，上限 1 万行，复用 `export_store` 生成可重复下载链接 |
| GET | `/api/admin/audit-logs/actions` | 返回动作枚举 + 中文名，供前端下拉 |

返回行字段：`log_id`、`created_at`、`actor_user_id`、`actor_username`、`action`、`action_label`、`target_type`、`target_id`、`result`、`detail`。

`actor_username` 由 `app_user` 左连接补充；`actor_user_id` 为空（登录失败未识别账号）时显示「未识别」。

#### R8.3 审计动作补全

| 场景 | 新增 action | actor | target | detail |
|---|---|---|---|---|
| 用户删除本人运行日志 | `USER_LOG_DELETE` | 本人 | `io_log` / user_id | `{removed, mode}` |
| 用户导出本人日志 | `USER_LOG_EXPORT` | 本人 | `io_log` / user_id | `{count}` |
| 用户删除会话 | `SESSION_DELETE` | 本人 | `session` / session_id | `{session_name, records, io_logs}` |
| 用户批量删除会话 | `SESSION_DELETE_BATCH` | 本人 | `session` / `batch` | `{count, session_ids}` |
| 管理员查看他人问答/链路/会话原文 | `ADMIN_VIEW_USER_DATA` | 管理员 | `user` / 被查看 user_id | `{scope: qa|trace|session|message|overview, trace_id?, session_id?, page?}` |
| 管理员导出他人 I/O 日志 | `ADMIN_IO_EXPORT` | 管理员 | `user` / user_id（无筛选时 `all`） | `{filters, rows, capped}` |
| 管理员导出审计日志 | `AUDIT_EXPORT` | 管理员 | `audit_log` / `all` | `{filters, rows}` |
| 管理员导出反馈 | `FEEDBACK_EXPORT` | 管理员 | `feedback` / `all` | `{rows}` |

#### R8.4 审计写入策略（避免噪声）

- 列表类查询（`/admin/io-logs` 分页、`/audit-logs` 分页、`/feedback` 分页）**不逐条写审计**；
- 打开**原文/详情**的行为必写（问答行、trace 详情、会话消息）；
- 所有导出必写；
- 写入统一走 `audit.log_operation`，失败降级 warning，不阻断业务（沿用现有约束）。

#### R8.5 数据与索引

- 不新增表，不新增列。
- 新增索引：`idx_operation_log_target (target_type, target_id, created_at DESC)`，支撑“某用户被查看了多少次”。
- `action` 为自由字符串，前端下拉用 `/actions` 固定枚举 + 允许自定义输入。

#### R8.6 前端

- 新增「操作审计」页（管理端导航一级入口，或挂在系统设置下）：筛选栏（操作人、被操作用户、动作、结果、时间范围、关键词）+ 分页表 + 导出。
- 行点击展开 `detail` JSON（只读、等宽展示、可复制）。
- 用户详情「活动流」Tab 复用同一后端查询，按 `target_user_id` 过滤。

#### R8.7 验收

- 造数：管理员创建用户、禁用、重置密码、上传文档、删除文档、导出日志 → 审计页按各维度筛选均能命中；
- 按 `target_user_id` 查“成员 B 被谁查过”可列出 `ADMIN_VIEW_USER_DATA`；
- 导出 CSV 行数与筛选 `total` 一致，10 万行上限截断时 `capped=true`；
- `operation_log` 中无任何聊天正文（人工抽查 `detail`）。

---

### R9 管理员查看行为反审计与合规约束

#### R9.1 需求描述

管理员拥有查看他人全部问答原文的权限，这项权限必须**可被审计、可被追责**，且用户侧要知情。

#### R9.2 规则

1. 每次打开他人问答行、trace 链路详情、会话消息 → 写 `ADMIN_VIEW_USER_DATA`；同一管理员对同一 `trace_id` 在 60 秒内重复打开只记一次（去重，防误触刷屏）。
2. 前端在只读查看容器顶部固定提示：「正在查看用户 `{display_name}` 的数据，本次查看已记录审计日志」。
3. 用户隐私设置页（个人设置）增加说明文案：管理员具备审计查看权，范围与保留期同上。
4. 审计不可被删除：用户不可删，管理员也不提供删除/清空接口；`operation_log` 不进入 `cleanup_expired` 清理，保留期单独定义为 `AUDIT_LOG_RETENTION_DAYS`（默认 730 天，仅告警不自动删，是否自动清理见决策 5）。
5. 管理员自身操作同样留痕：管理员查看管理员的数据也记 `ADMIN_VIEW_USER_DATA`，不豁免。
6. 所有接口 `require_admin` 强制后端校验，不依赖前端隐藏菜单。

#### R9.3 验收

- 打开一次他人 trace → 审计页新增 1 条 `ADMIN_VIEW_USER_DATA`，`detail.trace_id` 正确；
- 60 秒内重复打开不新增；
- 审计页不存在删除按钮，接口层无 `DELETE /api/admin/audit-logs`；
- 只读横幅在 1440 与 375 均可见、不遮挡操作。

---

## 5. 待确认决策（审核重点）

| # | 决策点 | 候选 | 建议 | 影响面 |
|---:|---|---|---|---|
| 1 | 「删除我的运行日志」的删除语义 | A 保留期软删除 / C 正文脱敏归档 / B 彻底物理删除 | **A**（全量可查，符合“管理员可查全部问答”） | 用户隐私承诺、DB 列变更、全部用户侧查询过滤 |
| 2 | 用户删除会话时，其 `chat_io_log` 是否也软删除 | 软删除（推荐，链路不断档）/ 维持物理删除 | 软删除 | R6 一致性、管理员链路完整性 |
| 3 | 管理员可见窗口 | 跟随 `IO_LOG_RETENTION_DAYS=90` / 延长至 180 或 365 | 跟随 90 天，另设只读提示 | 配置中心、合规话术 |
| 4 | 用户详情入口形态 | 抽屉（推荐，改动小）/ 独立路由页 `/admin/users/:id` | 抽屉 | 前端路由、移动端适配 |
| 5 | 审计日志是否自动清理 | 永久保留（推荐，表小）/ 按 `AUDIT_LOG_RETENTION_DAYS=730` 自动删 | 永久保留，仅按容量告警 | 存储、合规 |
| 6 | 本需求的阶段位置 | 插到 V5-3 之前（作为 V5-3，自主规划顺延 V5-4）/ 排队为 V5-4 | **提前**：删除文案与口径错误正在线上生效 | 阶段表、验收报告命名 |

> 未确认前不写代码。确认后按“先 R6 文案与语义 → R8 审计查询 → R7 用户全景 → R9 留痕”顺序开发，因 R7 依赖 R6 的可见性过滤、R9 依赖 R7 的入口。

---

## 6. 接口与数据变更汇总

### 6.1 接口

| 方法 | 路径 | 变更 | 需求 |
|---|---|---|---|
| DELETE | `/api/me/io-logs` | 语义由物理删除改为软删除标记（方案 A） | R6 |
| GET | `/api/me/io-logs/export`、`/{trace_id}` | 读取强制过滤 `user_deleted_at` | R6 |
| GET | `/api/admin/users/{id}/overview` | 新增 | R7 |
| GET | `/api/admin/users/{id}/qa` | 新增 | R7 |
| GET | `/api/admin/users/{id}/sessions` | 新增 | R7 |
| GET | `/api/admin/users/{id}/sessions/{sid}/messages` | 新增 | R7 |
| GET | `/api/admin/users/{id}/documents` | 新增 | R7 |
| GET | `/api/admin/users/{id}/feedback` | 新增 | R7 |
| GET | `/api/admin/users/{id}/activity` | 新增 | R7 |
| GET | `/api/admin/audit-logs` | 新增 | R8 |
| GET | `/api/admin/audit-logs/export` | 新增 | R8 |
| GET | `/api/admin/audit-logs/actions` | 新增 | R8 |
| GET | `/api/admin/io-logs` | 返回增加 `user_deleted`、`user_deleted_at` | R6/R7 |
| GET | `/api/admin/io-logs/export` | 写审计 `ADMIN_IO_EXPORT` | R8 |

错误码沿用现有：`40303` 无权限、`40402` 会话不存在/不属于该用户、`40403` 用户不存在、`40405` trace 不存在、`40001` 参数错误。**不新增错误码。**

### 6.2 数据模型

| 表 | 变更 | 可回滚 |
|---|---|---|
| `chat_io_log` | 新增 `user_deleted_at TIMESTAMP NULL` + `idx_io_log_user_visible (user_id, user_deleted_at, created_at DESC)`（方案 A） | 是（可空列，加索引幂等） |
| `operation_log` | 不新增列；新增 `idx_operation_log_target` | 是 |

不新增表；不做不可回滚列变更；禁止全表 DELETE。

### 6.3 配置

| 参数 | 默认 | 用途 | 是否进配置中心 |
|---|---:|---|---|
| `AUDIT_LOG_RETENTION_DAYS` | 730 | 审计保留期（方案：仅展示/告警） | 是（只读展示） |
| `ADMIN_VIEW_LOG_DEDUP_SECONDS` | 60 | 重复查看去重窗口 | 否，`Settings` 即可 |
| `ADMIN_OVERVIEW_CACHE_SECONDS` | 0 | 概览统计缓存，默认关闭 | 否 |

新增键必须同步 `.env` 与 `.env.example`。

---

## 7. 前端改造清单

| 文件/组件 | 改造 |
|---|---|
| `components/UserMenu.vue` | 删除确认文案按 R6.4 更新；个人设置增加管理员查看权说明 |
| `views/UsersView.vue` | 行尾「查看」→ 用户详情抽屉 |
| 新增 `components/AdminUserDetailDrawer.vue` | 概览 + 6 Tab，只读横幅，复用 `TraceDrawer` |
| 新增 `views/AuditLogView.vue` | 审计筛选、表格、`detail` 展开、导出 |
| `views/IoLogView.vue` | 用户列显示 `display_name(username)`、可点击进用户详情；增加「含用户已删除」筛选项与灰色标记 |
| `components/TraceDrawer.vue` | 增加只读审计模式与顶部横幅（普通用户路径不变） |
| 新增 `api/adminUsers.js`、`api/adminAudit.js` | 封装 R7/R8 接口；`api/ioLogs.js` 补 `include_deleted` |

---

## 8. 阶段与验收口径

### 8.1 阶段建议（决策 6 确认后生效）

| 阶段 | 内容 | 验收口径 |
|---|---|---|
| V5-A（若提前，编号顺延）R6 | 删除语义、文案、审计补记、会话删除口径 | 用户侧不可见/管理员侧可见且带标记/审计可查/保留期清理一致 |
| V5-B R8 | 审计查询、导出、动作补全 | 8 类动作可筛可导，`detail` 无聊天正文 |
| V5-C R7 | 用户全景 7 个接口 + 抽屉 | 6 Tab 真实数据，跨用户隔离与 `40303`、性能达标 |
| V5-D R9 | 反审计去重、只读横幅、合规文案 | 查看必留痕、60s 去重、无删除入口 |

验收报告命名沿用既有规范，建议 `V5-4 管理员审计与全链路查看验收报告.md`（若提前则按顺延编号）。

### 8.2 新增测试建议

- `backend/tests/test_admin_user_overview.py`：7 个接口、越权 `40303`、不存在 `40403`、会话不属于该用户 `40402`、字段脱敏。
- `backend/tests/test_admin_audit_logs.py`：筛选组合、导出条数、`detail` 不含正文、`actions` 枚举。
- `backend/tests/test_me_io_delete_semantics.py`：软删除后用户侧 `count=0`、详情 `40405`、管理员仍可见、审计 1 条、重复删除返回 0。
- `backend/tests/test_admin_view_audit.py`：查看他人 trace 写 `ADMIN_VIEW_USER_DATA`、60s 去重。
- 前端：1440/375 抽屉与审计页人工验收截图，表格无横向溢出。

### 8.3 回归基线

- 全量 `pytest` 全绿（当前 294 passed / 1 skipped，新增用例后总数上升）；
- 前端 `npm run build` EXIT 0；
- 既有隔离回归脚本 `backend/scripts/check_auth_isolation.py` 通过；
- 普通用户路径（会话列表、链路抽屉、导出、反馈）行为不变。

---

## 9. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 软删除口径与 v3 §5.6「物理删除」承诺不一致 | 合规争议、用户投诉 | 用 R6.4 文案如实告知；决策 1 由用户确认；验收报告记录口径变更 |
| 遗漏某条用户侧查询没过滤 `user_deleted_at` | 用户看到“已删除”的数据 | 过滤收敛到 `io_log` 单一函数 `_user_visible_filters()`，配专项用例 |
| 管理员查看即刻写审计导致日志暴涨 | 表膨胀 | 列表查询不写；详情 60s 去重；按月分区另立需求 |
| `overview` 聚合在百万行下变慢 | 打开详情卡顿 | 索引 + 可选 60s 缓存 + 时间窗限制（近 30/90 天） |
| 会话删除仍物理删 `chat_io_log` | 管理员链路断档 | 决策 2 要求软删除 |
| 知识库共享导致“某用户的文档”归属不准 | 误判责任 | 文档 Tab 明确“按审计反推”，不展示“所有者”概念 |
| 增列与索引在旧库未执行 | 上线后 500 | `ensure_schema` 幂等 `ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`，并纳入启动自检 |

---

## 10. 结论

- 本稿把原始问题拆成 4 项：**R6 删除语义与文案、R7 用户全景跨用户只读、R8 审计查询与补全、R9 查看留痕**，共 4 个阶段、13 个接口、1 个可空列 + 2 个索引、3 个配置项。
- 核心事实：底层 `chat_io_log` 字段已足够支撑“问答 + 链路”，`operation_log` 早已在写入 19 类动作、只是没有读出口；真正要改的是**删除语义**与**管理员入口**。
- 最大分歧点是决策 1：建议采用 **A 保留期软删除**，把用户隐私承诺从“彻底删除”改为“本人不可见 + 管理员保留期内可查”，并在确认弹窗里写清。
- **本稿为待审核稿，未修改 v5 正文、未改任何代码。** 确认第 5 节 6 项决策后，再并入 `RagKnowledge 能力增强需求文档 v5.md`（新增 R6–R9、阶段表、接口与数据变更、已确认决策）并进入开发。
