# RagKnowledge · 企业文档智能问答 Agent（RAG + LangGraph 工具 Agent）

面向企业内网的私有文档知识库 + 多工具 Agent：覆盖 RAG 全链路（解析→清洗→切片→向量化→检索→生成→引用溯源）与 LangGraph 多工具 Agent（知识库检索 / 数学计算 / 文档统计 / 业务库查询），支持多轮追问改写、三层会话记忆、工作流 DAG 并行、SSE 流式输出、多用户隔离与运维治理。

> **当前能力包括**：
> - PG17 + pgvector 单库与 `vector(1024)` HNSW；
> - 文档解析切片入库、向量检索、Rerank、阈值过滤与来源溯源；
> - LangGraph 意图决策与多工具编排；
> - SSE 流式问答、心跳与中断处理；
> - 三层会话记忆与事实版本历史；工作流 DAG 并行执行；
> - 会话游标分页、虚拟滚动、搜索防抖与批量操作；
> - 双模型路由与 query 改写；
> - 多用户隔离、角色鉴权、配额限流与运行日志。

## 一、技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue3 + Element Plus + Vite；`fetch` 手写 SSE 解析，`@tanstack/vue-virtual` 处理大会话列表 |
| 后端 | Python FastAPI + Uvicorn，分层单体（路由/服务/Agent/领域能力/基础设施） |
| Agent | LangGraph 状态图；7 类意图、4 个工具、循环上限 3 轮、工具去重与失败收敛 |
| 存储 | PostgreSQL 17 + pgvector，业务数据、向量、会话、记忆、日志、配置同库；HNSW 余弦索引 |
| Embedding | 百炼 `text-embedding-v3`，默认 1024 维，OpenAI 兼容 `/embeddings`，单批 ≤10，匹配 `vector(1024)`；本地 BGE / Ollama 为适配器预留分支 |
| LLM | 主模型 DeepSeek `deepseek-chat`（OpenAI 兼容协议）；小模型 Qwen `qwen3.6-flash` 负责摘要、事实抽取、标题与 query 改写，失败回落主模型 |
| Rerank | 百炼 `gte-rerank-v2`（原生 text-rerank 端点，复用百炼 Key；`RERANK_ENABLED` 开关，失败降级原序） |

已纳入：**登录鉴权与多用户隔离**（HttpOnly Cookie Session、admin/member 角色、会话按用户私有、操作审计）。

**暂时未做**：Docker 化项目、部署发布、异步队列、OCR、Milvus 集群、OAuth/SSO、细粒度 RBAC；现有轻量离线 CI 不接数据库、密钥与发布流程。

## 二、目录结构

```
RagKnowledge/
├── 文档/                       # 项目文档（按类型归档）
│   ├── 需求与设计/             # 需求、设计与技术复盘
│   ├── 验收报告/               # 阶段、M/P、V4-1~V4-3 验收
│   ├── 开发运维指南/           # 安装、开发与运维说明
│   └── 测试与质量/             # 审计、排查与测试修复
├── README.md / .env.example / .gitignore
├── backend/
│   ├── main.py                 # FastAPI 入口（lifespan、CORS、路由注册、全局异常）
│   ├── config.py               # Pydantic Settings 统一配置
│   ├── db.py                   # 异步连接池 + register_vector + to_vector 包装
│   ├── errors.py / app_logging.py / llm.py / prompts.py
│   ├── init_db.sql             # DDL（__EMBEDDING_DIM__ 占位符，幂等）
│   ├── scripts/init_db.py      # 渲染维度并执行建库建表
│   ├── scripts/migrate_auth_multitenant.py  # 幂等迁移：认证/审计表、会话归属、初始管理员
│   ├── schemas/                # 请求/响应模型
│   ├── routers/                # auth/chat/session/docs/workflow/biz/admin/system 等
│   ├── services/               # ingest/rag/memory/workflow/query_rewrite/session_title
│   │   └── ...                 # chat_store/vector_store/account_store/prompt_store/app_config
│   ├── agent/                  # state/decision/graph/replan/dedup/tools
│   └── tests/                  # 单元、集成与回归测试
├── frontend/                   # Vue3：api、composables、views、components
│   ├── src/api/                # http/sse/chat/docs/auth/admin/workflow
│   ├── src/composables/        # useChat/useStreamRender/useTypewriter
│   └── src/views/              # Chat/Docs/Users/Login/Config/IoLog/Workflow
├── docs/                       # 界面截图资产（m5-screens / v4-screens）
├── .github/workflows/ci.yml    # 轻量离线 CI：后端单测/装配 + 前端构建
└── data/uploads/               # 原始文档留档（不入库）
```

分层依赖规则：routers 只做协议与响应组装；services 做流程编排与事务边界；SQL 收敛在 `services/vector_store.py`、`services/chat_store.py`、`services/account_store.py`、`services/audit.py` 与 `db.py`；agent 不直接读写数据库；外部 LLM/Embedding 只经 `llm.py`/`embedder.py` 访问。

## 三、启动与访问（含默认管理员）

### 3.1 访问地址

| 用途 | 地址 |
| --- | --- |
| **前端页面（从这里进）** | <http://127.0.0.1:5173> |
| 接口文档（Swagger） | <http://127.0.0.1:8000/docs> |
| 健康检查 | <http://127.0.0.1:8000/health> |

> 服务只绑定 `127.0.0.1`，仅本机可访问。

### 3.2 默认管理员（超级账号，拥有全部权限）

| 项 | 值 |
| --- | --- |
| 用户名 | `admin` |
| 密码 | `Admin@12345` |
| 角色 | `admin`（可管理文档/索引 + 管理账号 + 全部普通用户能力） |

默认值在代码中配置，可被 `.env` 或环境变量覆盖（`backend/config.py`）：

```ini
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=Admin@12345      # 置空则改为随机生成，迁移脚本只在控制台打印一次
DEFAULT_ADMIN_DISPLAY_NAME=系统管理员
DEMO_CREDENTIAL_HINT=false              # 是否在登录页显示上面这组演示账号（默认关闭）
```

- 首次初始化由 `scripts/migrate_auth_multitenant.py` 按上述配置创建；
- 已有环境想“找回/重置”这个超级账号，执行：

  ```powershell
  # 工作目录 = 仓库根
  python backend\scripts\ensure_admin.py                    # 缺则创建；已存在则不改密码
  python backend\scripts\ensure_admin.py --reset-password   # 强制重置为配置密码并吊销其登录态
  ```

- 登录后请到右上角「修改密码」改掉默认密码；生产部署请用环境变量覆盖默认值。

**登录页演示提示（默认关闭）**：把 `DEMO_CREDENTIAL_HINT` 置为 `true` 后，登录页会显示
“演示环境默认超级管理员：`admin` / `Admin@12345`”并提供「一键填入」。
该提示只在默认密码确实还能登录时才出现——一旦你改了密码或禁用了账号，即使开关仍开着也会自动隐藏，不会给出过期凭据。**生产环境不要开启。**

### 3.3 首次准备（已完成环境可跳过）

**数据库（任选其一）**

```powershell
# Docker（最省事，镜像已内置 pgvector）
docker run -d --name pgvector -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=rag_agent -p 5432:5432 pgvector/pgvector:pg16
# 或本机 PostgreSQL 安装 pgvector 扩展后：CREATE DATABASE rag_agent;
```

**后端**

```powershell
# 在仓库根目录 D:\code\code_git\RagKnowledge 下执行
python -m venv .venv ; .venv\Scripts\activate
python -m pip install -r backend\requirements.txt
copy .env.example .env               # 填入 DB_DSN、LLM_API_KEY、EMBEDDING_API_KEY、EMBEDDING_DIM
python backend\scripts\create_database.py    # 幂等建 rag_agent 库（本机 PG；Docker 方式可跳过）
python backend\scripts\init_db.py            # 幂等建扩展/表/HNSW 索引并回读校验（vector(1024)）
python backend\scripts\migrate_auth_multitenant.py   # 建认证/审计表、会话归属，并创建默认管理员
python backend\scripts\ensure_admin.py       # 可选：确认超级账号存在/打印当前配置
```

**前端**

```powershell
cd frontend
npm install
```

### 3.4 日常启动（两个终端）

```powershell
# 终端 1：后端（Windows 必须用 run_dev.py，裸 uvicorn 会因 Proactor 事件循环连不上库）
# 工作目录 = 仓库根；包化后入口为 backend.main:app
.venv\Scripts\python.exe backend\scripts\run_dev.py      # http://127.0.0.1:8000

# 终端 2：前端（Vite 代理 /api -> 8000）
cd frontend
npm run dev                                          # http://127.0.0.1:5173
```

启动后浏览器打开 <http://127.0.0.1:5173>，用 `admin / Admin@12345` 登录。

**登录后能看到什么**

- 智能对话：新建会话、流式问答、来源卡片（知识库来源可预览原文）；会话仅本人可见，可重命名/删除；
- 知识库管理（管理员）：批量上传、文档预览/下载（DOCX/DOC 用 `docx-preview` 按页渲染，还原 A4 纸张、页边距、分页、页眉页脚与表格；Excel/CSV 显示列标/行号、合并单元格、列宽、字体、底色与底部工作表标签，支持缩放和适合宽度）、文档列表、重解析、删除、重建 HNSW 索引；
- 用户管理（管理员）：账号列表、新建账号、启用/禁用、重置密码；
- 右上角：当前角色、修改密码、退出登录。

**验证“多用户隔离”的推荐做法**：用管理员进「用户管理」新建一个 `member` 账号 → 用无痕窗口登录该 member → 对比两边的菜单与知识库列表；member 只能看到自己的会话，且看不到「知识库管理 / 用户管理」。

### 3.5 停止与重启

- 前台终端直接 `Ctrl+C`；
- 若由 AI 会话以后台任务方式启动，可让它停掉，或按端口清理：

  ```powershell
  Get-NetTCPConnection -LocalPort 5173,8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  ```

### 3.6 接口一览（供调用方参考）

接口文档：<http://127.0.0.1:8000/docs>；健康检查：`GET /health`；配置元信息：`GET /api/system/info`（管理员）。

- 认证：`POST /api/auth/login`（HttpOnly Cookie）、`POST /api/auth/logout`、`GET /api/auth/me`、`POST /api/auth/password`。
- 问答：`POST /api/chat/stream`（SSE）、`GET /api/chat/record/{session_id}`、`GET /api/chat/session/{session_id}/export`、`GET /api/chat/suggestions`、`POST /api/chat/feedback`。
- 会话：`POST /api/chat/session`、`GET /api/chat/session/list`、`POST /api/chat/session/batch`、`PATCH /api/chat/session/{id}/pin`、`PATCH /api/chat/session/{id}/archive`、`PATCH /api/chat/session/{id}`、`DELETE /api/chat/session/{id}`。
- 会话记忆：`GET /api/sessions/{session_id}/memory`、`GET /api/sessions/{session_id}/memory/{fact_id}/history`、`DELETE /api/sessions/{session_id}/memory/facts/{mem_id}`、`PUT /api/sessions/{session_id}/memory/settings`。
- 工作流：`POST /api/workflow/plan`、`POST /api/workflow/run`、`GET /api/workflow/list`、`GET /api/workflow/{task_id}`、`GET /api/workflow/{task_id}/events`、`POST /api/workflow/{task_id}/confirm`、`POST /api/workflow/{task_id}/cancel`、`POST /api/workflow/{task_id}/pause`、`POST /api/workflow/{task_id}/resume`。
- 业务查询：`GET /api/biz/intents`、`POST /api/biz/query`。
- 文档接口（管理员）：`POST /api/docs/upload`（单文件兼容）、`POST /api/docs/upload/batch`（服务端顺序批量聚合）、`POST /api/docs/upload/chunk` / `complete`（分片上传）、`POST /api/docs/{doc_id}/reparse`（重解析替换切片向量）、`POST /api/docs/reindex`（重建 HNSW 索引）、`GET /api/docs/list`、`DELETE /api/docs/{doc_id}`。
- 用户管理（管理员）：`GET/POST /api/admin/users`、`PATCH /api/admin/users/{id}/status`、`POST /api/admin/users/{id}/reset-password`；管理员登录后可在顶部「用户管理」页完成列表、新建账号、启用/禁用与重置密码（禁用/重置会立即吊销该账号登录态）。

### 3.7 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| 5173 打开报 `ECONNREFUSED` / 接口 500 | 后端没起；先确认 `http://127.0.0.1:8000/health` 返回 200 |
| 后端报 `ProactorEventLoop` 相关错误 | 用了裸 `uvicorn`；改用 `python backend\scripts\run_dev.py`（仓库根执行） |
| 登录提示“用户名或密码错误” | 密码被改过；执行 `python backend\scripts\ensure_admin.py --reset-password` |
| 页面一直停在登录页 | Cookie 未生效：确认从 `5173` 访问（经 Vite 代理同源），不要直接用 `8000` 打开页面 |
| 全部接口 401 | 登录态过期或被吊销（改密/重置/禁用都会吊销）；重新登录 |
| 普通用户看不到管理菜单 | 预期行为；后端也会对越权请求返回 `40303` |

## 四、里程碑与当前进度

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| 骨架 + 服务层 | 目录、配置、契约、纯函数；后端依赖自检；前端依赖、构建、开发服务与代理联通 | ✅ 完成 |
| M0 | PG + pgvector 环境、建库建表建 HNSW、扩展版本验证、异步连接 `db_ready=true` | ✅ PG 17.11 + vector 0.8.6，`vector(1024)` HNSW |
| M1 | 上传解析切片入库单事务链路、文档列表/删除 | ✅ 事务入库、FK 级联删除 |
| M2 | 向量检索 SQL + Prompt + LLM 生成 + 引用来源 | ✅ HNSW 余弦检索、阈值过滤、来源结构 |
| M3 | LangGraph 状态图、工具节点、意图路由、循环上限 | ✅ 显式状态图、工具去重、单轮收敛 |
| M4 | SSE 流式、会话与记录落库、历史回填 | ✅ 决策/流式/降级、落库 saved 标志 |
| M5 | 两页面 UI 与交互、来源卡片、中断恢复 | ✅ 会话管理、token 渲染、来源卡、中断复位 |
| M6 | 调优、异常兜底、日志、评测与 Rerank | ✅ gte-rerank-v2、心跳、防重复、HNSW 验证 |
| M7 | 治理能力：配额与限流、运行日志、配置中心、提示词版本化 | ✅ 62 个运行参数、6 条提示词版本 |
| M8 | 会话体验与可信度：三层记忆、证据强度、导出与反馈 | ✅ 记忆/摘要/事实链路收口 |
| v2 / v3 | 通用对话、联网兜底、工作流 Agent、业务库查询与治理增强 | ✅ 全量交付 |
| v4 | N1–N11：会话规模、标题小模型、工作流并行、归档计数、事实版本历史、批量操作、搜索防抖、小模型审计、query 改写、时间显示、宽度拖拽 | ✅ 全量交付并通过验收 |

> 当前进度以本节为准：主链路、治理能力与 v4 能力增强均已收口。

## 五、关键安全与一致性设计

- **单库同事务**：切片向量与文档元数据同库，上传 T2 原子入库、删除显式事务清切片，无双写补偿；
- **SQL 全参数化**：统计工具枚举白名单、计算器正则 + AST 白名单（不使用 eval）；
- **向量维度三维约束**：模型输出维度 = `EMBEDDING_DIM` = 表列 `vector(N)`，启动与入库双重校验；
- **向量写入统一 `Vector(...)` 包装**：pgvector-python 未注册 list dumper，直传 list 会报类型错误；
- **服务端强制鉴权**：Cookie 只存不透明令牌，库内只存 `SHA-256(token)`；`get_current_user` / `require_admin` 在 FastAPI 依赖层校验，前端隐藏按钮只是体验优化；
- **会话私有**：`chat_session.user_id` 归属校验 + 删除前 `SELECT ... FOR UPDATE` 锁定 owner，越权统一 40402，既不泄露存在性也不会误删他人记录；
- **密码不落明文**：PBKDF2-SHA256（260k 迭代）+ 随机盐；改密/重置/禁用即吊销对应登录态；
- 服务仅绑定 `127.0.0.1`；对外部署需自行加 HTTPS 并开启 Cookie `Secure`。

## 六、常用回归命令（离线零费用 / 联网按需）

**纯离线、零模型调用（日常首选；无网络费用）**：

```powershell
# 一键本地离线回归（后端 pytest + check_env + compileall；加 -Frontend 追加 npm ci 与 vite build）
powershell -ExecutionPolicy Bypass -File backend\scripts\offline_regression.ps1

# 工作目录 = 仓库根（pytest 需从根收集 backend.tests 包）
python -m pytest backend/tests -q          # 纯函数/解析/防重复/心跳/再规划/鉴权 API 单测
python backend\scripts\check_env.py        # 依赖与内部模块导入、FastAPI 装配、路由注册（不连库不调模型）
python -m compileall -q backend            # 静态字节编译，只编译不执行、不联网
cd frontend
npm run build                              # 前端生产构建（验证无编译错误）
```

> 需要本地 PostgreSQL 但不调用模型、无模型费用的脚本：`check_chat_sse.py`（REAL_LLM 默认 SKIP）、`check_hnsw_index.py`（事务内造数验证 HNSW 计划、结束回滚不污染数据）、`check_auth_isolation.py`（会话归属隔离与越权删除/重命名）、`check_auth_http.py`（认证链路与权限矩阵，临时账号与审计行自动清理）。

**联网（按需执行，会产生少量 Embedding / Rerank / LLM 调用费用）**：

```powershell
# 工作目录 = 仓库根
python backend\scripts\check_rerank.py             # 真实 gte-rerank-v2 排序 + 坏端点降级探针
python backend\scripts\assess_retrieval.py         # 召回基线评测（Hit@K/MRR；复用已入库样料，仍会调 embedding/rerank）
python backend\scripts\score_distribution.py       # 只读向量余弦分数分布（不写库、不调 LLM；需先有入库向量）
python backend\scripts\check_docx_pdf_ingest.py     # DOCX/PDF 真实 embedding 入库 + 向量命中验证，脚本内关 rerank、测完自动清理复原基线
python backend\scripts\check_replan_live.py          # 动态多轮再规划门控轻测：默认离线零费用不触网；置 $env:REPLAN_LIVE="1" 才发起 1 次真实再决策、不写库
python backend\scripts\assess_rerank_gain.py         # B档 Rerank 增益复评：内嵌10篇测试语料真实入库，OFF纯向量/ON重排双模式对比指标，自动清理复原基线、不改生产阈值
python backend\scripts\check_maintenance.py          # C档运维能力：临时文档重解析事务替换切片 + HNSW REINDEX 验证；自动删除临时 DB 记录与本地文件，不重嵌入留存样料
```

> 轻量离线 CI 位于 `.github/workflows/ci.yml`：`backend-offline`（pytest + check_env + compileall）与 `frontend-build`（npm ci + vite build）；触发于 push/PR 到 main，刻意不纳入数据库、密钥与联网评测脚本，也不做部署发布；本地等价步骤由 `offline_regression.ps1` 覆盖。

> Agent 多轮：图链路为 工具 → assess → replan →（工具 | answer）。`MULTI_ROUND_ENABLED` 控制是否允许再决策回跳（默认 True；`LLM_REPLAN_ENABLED=False` 时 `plan_next` 恒收敛、行为与单轮一致、零额外 LLM 调用）；`LLM_REPLAN_ENABLED` 默认 False，置 True 后由 `replan_node` 调 LLM 产出带新 `args` 的决策、写回 `state.decision` 并回跳对应工具（开启会增加 LLM 决策调用）；轮次受 `MAX_TOOL_ROUNDS=3` 上限、最近工具失败不重试、`dedup` 重复键三重兜底；前端工具标签在第二轮及以上显示“· 第N轮”、首轮不显示；真实再决策门控轻测见 `scripts/check_replan_live.py`（默认离线零费用、`REPLAN_LIVE=1` 单次联网、不写库）。

> 启动顺序：先 PostgreSQL（`127.0.0.1:5432/rag_agent`）→ `python backend\scripts\run_dev.py`（仓库根执行，后端 8000）→ `npm run dev`（前端 5173，Vite 代理 `/api`→8000）。Windows 下后端勿裸 `uvicorn main:app`：Proactor 事件循环会导致 psycopg 异步连接异常，须经 `run_dev.py` 选择器循环启动。
>
> 导入约定：`backend/` 已包化（入口 `backend.main:app`，仓库根在 `sys.path`）。包内部各模块统一用相对导入（`backend/x.py` → `from .config import …`；`backend/routers/x.py` → `from ..services import …`；`backend/agent/tools/x.py` → `from ...services import …`）；`backend/scripts/*`、`backend/tests/*` 作为独立入口无法相对导入，统一用 `backend.<x>` 绝对包名。因此 pytest 必须**在仓库根**执行 `python -m pytest backend/tests -q`。
>
> 数据边界：当前留存 4 篇样料（document/chunk=4/4）与 1 个 `admin` 账号；测试产生的会话/记录/临时账号/审计行应在用完后删除，权威计数保持 `session/record=0`。
