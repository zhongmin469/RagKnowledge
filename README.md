# RagKnowledge · 企业文档智能问答 Agent（RAG + LangGraph）

面向企业内网的私有文档知识库 + 多工具 Agent：覆盖 RAG 全链路（解析 → 清洗 → 切片 → 向量化 → 检索 → 重排 → 生成 → 引用溯源），以及 LangGraph 多工具编排、会话记忆、工作流任务、联网兜底、多用户隔离、运行日志、操作审计与配置中心。全部能力在 **PostgreSQL + FastAPI + Vue3** 内闭环，默认只监听本机回环地址。

> 本 README 以 **2026-11-23** 的代码与本地开发库为基线；里程碑编号已在第五节统一命名。历史上的验收报告保留原文件名，编号映射见 5.1，报告对照见 5.4。

---

## 一、能力地图

### 1.1 对话与 Agent

| 能力 | 关键实现 | 状态 |
|---|---|---|
| 多工具 Agent | LangGraph 状态图；7 类意图（`knowledge / biz_query / calculator / doc_stats / general / workflow / clarify`）与 4 个工具（`knowledge_search / calculator / doc_stats / biz_query`）；工具循环上限 3 轮、失败不重试、`dedup` 去重 | ✅ |
| SSE 流式问答 | `POST /api/chat/stream`；事件含 `tool / token / source / notice / table / workflow / query_rewrite / done / error`；前置阶段每 10s 发 `: ping` 心跳；前端首事件 30s 超时 | ✅ |
| 引用溯源 | 来源卡片展示文档标题、文档摘要、片段摘要、相似片段与相似度；`doc_id / chunk_id` 可定位；低相关后置；精确词/短语高亮 | ✅ |
| 通用对话 | `general` 意图直答，不强制走知识库；内部实体词表命中时自动降级回知识库，避免通用能力抢答内部问题 | ✅ |
| 联网兜底 | 内部知识不足时按 `FALLBACK_MODE` 选择 `web / guide / contact_admin`；百炼 `qwen-plus + enable_search`，供应商可切 `bailian / bocha / tavily` | ✅ |
| 工作流任务中心 | `plan → run → confirm / cancel / pause / resume`；步骤事件流；无依赖步骤并行（默认并发 2）；步数、超时与预算上限 | ✅ |
| 业务库查询 | `biz_a / biz_b` 两套 schema；意图注册表驱动；只读事务、行数与超时上限、个人限流；大结果转 CSV 导出 | ✅ |
| 会话记忆 | 原文窗口 8 轮 / 3000 token、滚动摘要、会话事实三层；事实多版回溯；会话记忆面板可查看/删除 | ✅ |
| 消息反馈与导出 | 单条回答点赞/点踩与理由；会话导出 Markdown / JSON；业务结果 CSV 导出链接 | ✅ |
| 自然语言自主规划 | 一句话描述复合目标，由助手自动判断并拆步骤（V5-3） | ⏳ 待开发 |

> 多轮默认：`MULTI_ROUND_ENABLED=True`、`LLM_REPLAN_ENABLED=False`，再决策走确定性规则（零额外 LLM 调用）；置 True 后由 `replan_node` 调 LLM 产出带新 `args` 的决策并回跳工具；`MAX_TOOL_ROUNDS=3`、最近工具失败不重试、`dedup` 三重兜底。

### 1.2 知识库摄取与管理

| 能力 | 关键实现 | 状态 |
|---|---|---|
| 多格式解析 | `.pdf`、`.docx`、`.doc`、`.md`、`.xlsx`、`.xlsm`、`.xls`、`.csv` 共 8 种；Excel 合并单元格填充、跨列标题识别、行列与工作表上限；`.doc` 先转 `.docx` 再解析 | ✅ |
| 上传方式 | 单文件、服务端顺序批量、分片上传（`chunk` + `complete`）；前端逐文件上传队列（排队/进度/重试/移除/汇总） | ✅ |
| 列表筛选 | 文档名关键字 300ms 防抖、上传时间范围、处理状态；分页 | ✅ |
| 原件预览 | PDF 浏览器内联；Markdown 渲染；DOCX/DOC 优先按页渲染，失败降级 mammoth 语义 HTML；Excel/CSV 样式化表格（合并单元格、列宽、字体、底色） | ✅ |
| 原件下载 | 管理员下载原始文件，形成「上传 → 检索 → 核对原件」闭环 | ✅ |
| 维护操作 | 重解析（事务替换切片与向量）、删除（FK 级联）、重建 HNSW 索引；确认与防重复提交 | ✅ |
| 文档摘要 | 入库/重解析时对切片做确定性归并，写入 `document.summary`；检索时透出 `doc_summary`；历史文档可回填 | ✅ |

### 1.3 检索与生成

| 能力 | 当前默认值 / 实现 |
|---|---|
| 向量存储 | PostgreSQL 17 + pgvector；`document_chunk.embedding vector(1024)`；HNSW 余弦索引 `idx_chunk_embedding` |
| 召回与截断 | 候选 20 条（`RETRIEVAL_CANDIDATES`）→ 展示 Top-5（`TOP_K`）；余弦阈值 `RETRIEVAL_MIN_SCORE=0.5` |
| 重排 | 百炼 `gte-rerank-v2` 原生 text-rerank；`RERANK_ENABLED` 开关，失败降级原序 |
| Query 改写 | 多轮追问场景用轻任务小模型改写检索句；`QUERY_REWRITE_ENABLED` 可关，关闭后完全用原句 |
| 生成 | 主模型 `deepseek-chat`（OpenAI 兼容）；生成温度与最大 token 可在配置中心在线调整 |
| 轻任务模型 | `qwen3.6-flash` 承担摘要、记忆抽取、标题、query 改写；未配置时自动回落主模型 |
| 提示词治理 | 版本化存储、灰度与启用；`done` 帧回传实际生效版本，便于排障 |

### 1.4 会话与体验

| 能力 | 说明 |
|---|---|
| 会话标题 | 首问后规则提炼 ≤16 字；手动重命名不被覆盖；可选 LLM 提炼（默认关） |
| 会话列表 | 分页（默认 50 条/页）+ 前端虚拟滚动；服务端关键词搜索；今天 / 近 7 天 / 更早分组；消息数与相对时间 |
| 会话操作 | 重命名、删除（二次确认）、置顶、归档、批量操作；长期无消息自动归档（`SESSION_ARCHIVE_DAYS=30`） |
| 历史分页 | 首次加载最近 20 条，顶部「加载更早」并补偿滚动位置 |
| 输入区 | 1–8 行自适应、400 字软提示 / 500 字硬上限、快捷键、流式中可输入仅禁发送；按会话草稿并持久化到 `localStorage` |
| 前端体验 | 暗色主题与记忆、1280 / 992 / 768 响应式、Markdown + DOMPurify + 代码高亮、智能滚动、空状态与错误卡片、基础与进阶无障碍 |

### 1.5 治理、审计与安全

| 能力 | 说明 |
|---|---|
| 登录与角色 | HttpOnly Cookie 会话；`admin / member` 两级角色；会话与记录按用户私有 |
| 配置中心 | 11 组、62 个运行参数在线调整（检索、生成、通用对话、记忆、会话、上传、兜底、业务库、日志、任务编排、配额）；优先级 `app_config > .env > 代码默认` |
| 运行日志 | 每次问答生成 `trace_id`，记录输入、输出、token 用量、模型调用与工具链；支持统计、明细、CSV 导出 |
| 日志删除语义 | 用户删除 = 从本人视角软删除（本人不可见/不可导出）；管理员在 `IO_LOG_RETENTION_DAYS`（默认 90 天）内仍可查，并标注「用户已删除」 |
| 操作审计 | `operation_log` 记录 20+ 类动作；管理端可筛选、展开详情、导出 CSV |
| 用户全景 | 管理员按用户查看概览、问答记录、会话与消息、上传文档、反馈、活动流（6 个 Tab，全部只读） |
| 反审计 | 管理员查看他人问答或链路详情写 `ADMIN_VIEW_USER_DATA`，同对象 60 秒去重，页面展示只读横幅 |
| 配额与限流 | 每日 token 额度、每分钟请求上限；业务库查询独立限流 |
| 反馈管理 | 管理端反馈列表、筛选、导出 |

### 1.6 当前边界与已知优化点

- **V5-3 自然语言自主任务规划未开发**：现有一句话触发工作流的能力尚未接入自动拆步，当前以任务中心的显式计划/确认为主。
- 不做 Docker 化与发布流水线、异步任务队列、OCR（扫描版 PDF / 图片型 Excel 不识别）、Milvus、OAuth/SSO、细粒度 RBAC、多语言。
- 不做 Office 在线编辑、在线转 PDF、像素级版式还原；预览以「可读内容 + 常见版式」为目标。
- 不做跨设备草稿/历史同步、管理员实时监听、跨用户 BI 报表、审计告警规则。
- 前端 `ui-vendor` 仍约 1,007 kB（gzip 328 kB），主要来自 Element Plus 全量引入；构建会提示 >500 kB。后续可按需引入组件/图标或按页面拆包。
- 服务只绑定 `127.0.0.1`；对外部署需自行加 HTTPS 并开启 Cookie `Secure`。

---

## 二、技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3.4 + Element Plus 2.8 + Vite 5；`axios`；`marked` + `DOMPurify` + `highlight.js`；`docx-preview`（按页预览）+ `mammoth`（语义 HTML 降级）；`@tanstack/vue-virtual`（会话虚拟滚动）；`fetch + ReadableStream` 手写 SSE 解析 |
| 后端 | Python 3.12+（本机 `.venv` 为 3.13）+ FastAPI + Uvicorn；分层单体（routers / services / agent / 基础设施）；`psycopg3` 异步连接池；`pydantic-settings` 统一配置 |
| Agent | LangGraph 状态图：工具 → assess → replan →（工具 \| answer）；7 类意图、4 个工具、循环上限 3 轮、工具去重与失败收敛 |
| 存储 | PostgreSQL 17 + pgvector：业务数据、向量、会话、记忆、日志、审计、配置同库；`vector(1024)` + HNSW 余弦索引 |
| Embedding | 百炼 `text-embedding-v3`，1024 维，OpenAI 兼容 `/embeddings`，单批 ≤10；保留本地 / Ollama 适配器分支 |
| LLM | 主模型 DeepSeek `deepseek-chat`；小模型 `qwen3.6-flash`（`summary / memory_extract / title / query_rewrite`），失败回落主模型 |
| Rerank | 百炼 `gte-rerank-v2` 原生 text-rerank 端点，复用百炼 Key，失败降级原序 |
| 联网检索 | 百炼 DashScope `qwen-plus + enable_search`（默认）；可切博查 / Tavily；独立 Key 变量 |
| 文档解析 | `PyPDF2`、`python-docx`、`mammoth`、`openpyxl`、`xlrd`、`markdown`；`.doc` 转换优先 LibreOffice，Windows 回退 Word COM（`pywin32`） |
| CI | GitHub Actions 轻量离线流水线：后端 pytest + 装配自检 + 静态编译；前端 `npm ci` + `vite build` |

依赖清单以 `backend/requirements.txt`（兼容下限）为准；根目录 `requirement.txt` 为当前环境的 `pip freeze` 快照，便于复现具体版本。

---

## 三、目录结构

```text
RagKnowledge/
├── 文档/                          # 项目文档（按类型归档，入口见 文档/README.md）
│   ├── 需求与设计/                # 主需求、v2–v5 能力增强、架构设计、权限模型、前端优化需求
│   ├── 验收报告/                  # 交付验收、M1–M8、V4-1–V4-3、V5-1–V5-4、前端优化 P1/P2
│   ├── 开发运维指南/              # PostgreSQL/pgvector 安装、运维与回归手册
│   └── 测试与质量/                # 小模型覆盖度审计、登录校验卡死修复等
├── docs/                          # 界面截图资产：m1~m8-screens、v4-screens、v5-screens
├── .github/workflows/ci.yml       # 离线 CI（后端单测/装配 + 前端构建）
├── backend/
│   ├── main.py                    # FastAPI 入口：lifespan、中间件、全局异常、17 个路由注册
│   ├── config.py                  # Pydantic Settings 统一配置
│   ├── db.py                      # 异步连接池 + register_vector + to_vector
│   ├── errors.py / app_logging.py / llm.py / prompts.py
│   ├── init_db.sql                # DDL（__EMBEDDING_DIM__ 占位符，幂等）
│   ├── scripts/                   # 建库/迁移/启动/回填/回归与评测脚本（见第七节）
│   ├── schemas/                   # 请求/响应模型
│   ├── routers/                   # auth/chat/session/session_memory/docs/workflow/biz/export/system
│   │   └── admin*.py, user_io.py  # 管理端：用户、配置、日志、反馈、提示词、审计、用户全景
│   ├── services/                  # ingest/rag/memory/workflow/query_rewrite/session_title/evidence
│   │   └── ...                    # chat_store/vector_store/account_store/audit/io_log/quota/app_config
│   ├── agent/                     # state / decision / graph / replan / dedup
│   │   └── tools/                 # search / calc / doc_stats / biz_query
│   └── tests/                     # 单元、API 与离线回归测试
├── frontend/src/
│   ├── api/                       # http/sse/chat/docs/auth/admin*/ioLogs/sessionMemory/workflow/status
│   ├── composables/               # useChat/useStreamRender/useTypewriter/useTheme/draftStore
│   ├── components/                # 对话、来源、Markdown、上传队列、预览、记忆、抽屉等 28 个组件
│   ├── views/                     # Chat/Workflow/Docs/Users/AuditLog/IoLog/Config/Login
│   ├── config/  styles/  utils/   # 品牌、示例问题、主题/Markdown 样式、高亮工具
├── data/uploads/                  # 原始文档留档（不入库）
├── .env.example                   # 环境变量样例（复制为 .env）
├── requirement.txt / pyproject.toml
└── README.md
```

分层依赖规则：`routers` 只做协议与响应组装；`services` 做流程编排与事务边界；SQL 收敛在 `vector_store.py`、`chat_store.py`、`account_store.py`、`session_memory_store.py`、`audit.py`、`io_log.py` 与 `db.py`；`agent` 不直接读写数据库；外部 LLM / Embedding 只经 `llm.py` / `embedder.py` 访问。

导入约定：`backend/` 已包化（入口 `backend.main:app`，仓库根在 `sys.path`）。包内模块统一相对导入；`backend/scripts/*` 与 `backend/tests/*` 作为独立入口无法相对导入，统一用 `backend.<x>` 绝对包名。因此 pytest 必须在仓库根执行。

---

## 四、启动与访问

### 4.1 访问地址

| 用途 | 地址 |
|---|---|
| **前端页面（从这里进）** | <http://127.0.0.1:5173> |
| 接口文档（Swagger） | <http://127.0.0.1:8000/docs> |
| 健康检查 | <http://127.0.0.1:8000/health> |

> 服务只绑定 `127.0.0.1`，仅本机可访问；前端经 Vite 代理 `/api → 8000`。

### 4.2 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（PowerShell）；Linux/macOS 可运行，`.doc` 转换需 LibreOffice |
| Python | 3.12+（`backend/requirements.txt` 声明 3.10+；本机 `.venv` 为 3.13.17） |
| Node | 20+（CI 使用 Node 20） |
| 数据库 | PostgreSQL 17 + pgvector 0.8+（本机实测 17.12 / 0.8.7） |
| 密钥 | `LLM_API_KEY`、`EMBEDDING_API_KEY` 必填；Rerank / 联网检索复用百炼 Key 或单独配置 |

### 4.3 默认管理员

| 项 | 值 |
|---|---|
| 用户名 | `admin` |
| 密码 | `Admin@12345` |
| 角色 | `admin`（文档/索引维护、账号管理 + 全部普通用户能力） |

默认值在代码中配置，可被 .env 或环境变量覆盖（backend/config.py）：

```ini
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=Admin@12345      # 置空则改为随机生成，迁移脚本只在控制台打印一次
DEFAULT_ADMIN_DISPLAY_NAME=系统管理员
DEMO_CREDENTIAL_HINT=false              # 是否在登录页显示上面这组演示账号（默认关闭）
```

找回/重置超级账号（仓库根执行）：

```powershell
.venv\Scripts\python.exe backend\scripts\ensure_admin.py                    # 缺则创建；已存在不改密码
.venv\Scripts\python.exe backend\scripts\ensure_admin.py --reset-password   # 强制重置并吊销其登录态
```

### 4.4 首次准备（已有环境可跳过）

*数据库（任选其一）**

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

PostgreSQL 自身安装与 pgvector 扩展步骤见 `文档/开发运维指南/PostgreSQL17-pgvector安装指南.md`。也可直接用 Docker `pgvector/pgvector:pg17` 镜像快速起库（项目实际以本机 PG 17 运行）。

### 4.5 日常启动（两个终端）

```powershell
# 终端 1：后端（Windows 必须用 run_dev.py，裸 uvicorn 会因 Proactor 事件循环连不上库）
# 工作目录 = 仓库根；包化后入口为 backend.main:app
.venv\Scripts\python.exe backend\scripts\run_dev.py      # http://127.0.0.1:8000

# 终端 2：前端（Vite 代理 /api -> 8000）
cd frontend
npm run dev                                          # http://127.0.0.1:5173
```

Windows 下**不要**裸跑 `uvicorn main:app`：Proactor 事件循环会让 psycopg 异步连接失败。`run_dev.py` 会显式构造 `SelectorEventLoop`，并自动切换到项目 `.venv`、启动前校验 `openpyxl / xlrd / python-docx / mammoth` 是否安装。

启动顺序：PostgreSQL（`127.0.0.1:5432/rag_agent`）→ 后端 8000 → 前端 5173。后端代码改动后需重启进程（`reload=False`）。

启动后浏览器打开 <http://127.0.0.1:5173>，用 `admin / Admin@12345` 登录。

### 4.6 页面与角色

| 页面 | admin | member |
|---|---|---|
| 智能对话（会话、流式问答、来源卡、记忆面板、反馈） | ✅ | ✅ |
| 任务中心（工作流计划/执行/事件/暂停恢复） | ✅ | ✅ |
| 知识库管理（上传队列、筛选、预览/下载、重解析、重建索引） | ✅ | — |
| 用户管理（列表、新建、启禁用、重置密码、用户全景抽屉） | ✅ | — |
| 配置中心（62 项运行参数、重置） | ✅ | — |
| 运行日志（明细、统计、导出、链路详情） | ✅ | — |
| 操作审计（筛选、详情、CSV 导出） | ✅ | — |

**验证多用户隔离**：管理员在「用户管理」新建 `member` 账号 → 用无痕窗口登录 → member 只看到自己的会话与记录，看不到管理菜单；越权接口返回 `40303`，访问他人会话返回 `40402`。

### 4.7 停止与端口清理

```powershell
# 前台终端 Ctrl+C；或按端口清理
Get-NetTCPConnection -LocalPort 5173,8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### 4.8 配置优先级

`配置中心（app_config 表）> .env / 环境变量 > 代码默认值`。配置中心覆盖项可单条重置；模型名、BaseURL 与 Key 统一放 `.env`，避免两处口径漂移。当前可在线调整 62 项，覆盖检索、生成、通用对话、记忆窗口、会话归档、上传限制、兜底策略、业务库、日志保留、任务编排与配额。

### 4.9 接口一览（分组）

接口文档：<http://127.0.0.1:8000/docs>。所有 `/api/admin/*` 仅 `admin` 可访问。

- **元信息**：`GET /health`、`GET /api/system/info`、`GET /api/system/status`。
- **认证**：`POST /api/auth/login`（HttpOnly Cookie）、`POST /api/auth/logout`、`GET /api/auth/me`、`GET /api/auth/demo-hint`、`POST /api/auth/password`、`PATCH /api/auth/profile`。
- **问答**：`POST /api/chat/stream`（SSE）、`GET /api/chat/suggestions`、`POST /api/chat/feedback`、`GET /api/chat/record/{session_id}`、`GET /api/chat/session/{session_id}/export`。
- **会话**：`POST /api/chat/session`、`GET /api/chat/session/list`、`POST /api/chat/session/batch`、`PATCH /api/chat/session/{id}/pin`、`PATCH /api/chat/session/{id}/archive`、`PATCH /api/chat/session/{id}`、`DELETE /api/chat/session/{id}`。
- **会话记忆**：`GET /api/sessions/{id}/memory`、`DELETE /api/sessions/{id}/memory`、`GET /api/sessions/{id}/memory/{fact_id}/history`、`DELETE /api/sessions/{id}/memory/facts/{mem_id}`、`PUT /api/sessions/{id}/memory/settings`。
- **文档**：`POST /api/docs/upload`、`POST /api/docs/upload/batch`、`POST /api/docs/upload/chunk`、`POST /api/docs/upload/complete`、`DELETE /api/docs/upload/chunk`、`GET /api/docs/list`、`GET /api/docs/{id}/preview`、`GET /api/docs/{id}/download`、`POST /api/docs/{id}/reparse`、`POST /api/docs/reindex`、`DELETE /api/docs/{id}`。
- **工作流**：`POST /api/workflow/plan`、`POST /api/workflow/run`、`GET /api/workflow/list`、`GET /api/workflow/{id}`、`GET /api/workflow/{id}/events`、`POST /api/workflow/{id}/confirm|cancel|pause|resume`。
- **业务库**：`GET /api/biz/intents`、`GET /api/biz/intents/detail`、`POST /api/biz/query`。
- **导出**：`GET /api/export/{token}`（大结果 CSV 下载）。
- **我的日志**：`GET /api/me/io-logs`、`GET /api/me/io-logs/export`、`GET /api/me/io-logs/{trace_id}`、`DELETE /api/me/io-logs`。
- **管理端**：`/api/admin/users`（列表/新建/启禁用/重置密码）、`/api/admin/users/{id}/(overview|qa|sessions|documents|feedback|activity)` 与 `sessions/{sid}/messages`、`GET /api/admin/audit-logs`（`/actions`、`/export`）、`/api/admin/io-logs`（`/stats`、`/export`、`/{trace_id}`）、`/api/admin/feedback`（`/export`）、`/api/admin/prompts`（版本/灰度/启用）、`/api/admin/config`（读/改/重置）。

### 4.10 常见问题

| 现象 | 原因与处理 |
|---|---|
| 5173 打不开或接口 500 | 后端没起；先确认 `http://127.0.0.1:8000/health` 返回 200 |
| 后端报 `ProactorEventLoop` | 裸跑了 uvicorn；改用 `backend\scripts\run_dev.py` |
| 上传 Excel 报缺少 `openpyxl` | 8000 端口由系统 Python 启动；用 `run_dev.py`，它会自动切到 `.venv` 并校验依赖 |
| 登录提示用户名或密码错误 | 密码被改过；执行 `ensure_admin.py --reset-password` |
| 页面一直停在登录页 | Cookie 未生效；确认从 `5173` 访问（走 Vite 代理同源），不要直接用 `8000` 打开页面 |
| 全部接口 401 | 登录态过期或被吊销（改密/重置/禁用会吊销）；重新登录 |
| 普通用户看不到管理菜单 | 预期行为；后端对越权请求返回 `40303` |
| 文档预览空白或报错 | 缺 `mammoth / openpyxl / xlrd` 依赖，或后端未重启；装依赖后重启 `run_dev.py` |
| 检索结果为空 | 检查 `RETRIEVAL_MIN_SCORE`（默认 0.5）与 `TOP_K`；文档是否入库成功、切片数是否 >0 |

---

## 五、里程碑与当前进度

### 5.1 统一命名规范

| 编号族 | 含义 | 原始叫法 |
|---|---|---|
| `S0` | 基线骨架：目录、配置、契约、依赖自检 | 骨架 + 服务层 |
| `M0`–`M8` | 核心链路里程碑（环境、入库、检索、Agent、SSE、UI、评测、治理、会话体验） | M0–M8 |
| `V2-1`…`V2-5` | v2 能力增强批次 | v2 文档中的 M1–M5 |
| `V3-1`…`V3-5` | v3 能力增强批次 | v3 文档中的 M1–M5 |
| `V4-1`…`V4-3` | v4 收尾增强批次 | V4-1–V4-3（N1–N11） |
| `V5-1`…`V5-4` | v5 阶段 | V5-1–V5-4 |
| `UX-1`…`UX-3` / `UX-P1` / `UX-P2` | 前端优化批次 | 阶段一/二/三、P1 细节补齐、P2 进阶项 |

> 历史验收报告文件名保持不变（如「M1 配置中心验收报告」），本节编号是唯一对外口径；引用旧报告时按上表对照。

### 5.2 里程碑台账

| 编号 | 里程碑 | 范围摘要 | 状态 |
|---|---|---|---|
| `S0` | 骨架与服务层 | 目录/配置/契约/纯函数；前后端依赖与代理联通 | ✅ |
| `M0` | 环境与向量底座 | PG 17 + pgvector、建库建表、`vector(1024)` HNSW、`db_ready=true` | ✅ |
| `M1` | 摄取入库 | 上传解析切片入库单事务、文档列表/删除、FK 级联 | ✅ |
| `M2` | 检索与生成 | HNSW 余弦检索、阈值过滤、Prompt、LLM 生成、来源结构 | ✅ |
| `M3` | Agent 编排 | LangGraph 状态图、工具节点、意图路由、循环上限、去重 | ✅ |
| `M4` | SSE 与会话落库 | 流式决策/生成/降级、会话与记录落库、历史回填 | ✅ |
| `M5` | 核心 UI | 对话与知识库两页面、来源卡、token 渲染、中断复位 | ✅ |
| `M6` | 调优与评测 | Rerank、心跳、防重复、阈值分布、HNSW 计划验证 | ✅ |
| `M7` | 治理基础 | 配额限流、运行日志、配置中心、提示词版本化 | ✅ |
| `M8` | 会话体验与可信度 | 三层记忆、证据强度、导出与反馈、自动归档 | ✅ |
| `V2-1` | 配置中心 | 管理员在线调整检索/生成/兜底参数，覆盖与重置 | ✅ |
| `V2-2` | 输入框固定与顶栏重构 | 输入框钉底、多行上限、顶栏层级与窄屏折叠 | ✅ |
| `V2-3` | 联网兜底与能力标注 | 内部不足转联网、`answer_mode` 标注与兜底话术 | ✅ |
| `V2-4` | 业务库双库查询 | `biz_a` / `biz_b` 意图注册表、只读事务、限流 | ✅ |
| `V2-5` | 跨库联表与大结果导出 | 单 SQL 跨 schema 联表、行数上限、CSV 导出链接 | ✅ |
| `V3-1` | 会话记忆底座 | 窗口治理、滚动摘要、会话事实与版本历史 | ✅ |
| `V3-2` | 通用对话 | `general` 直答、内部词表降级、模式选择 | ✅ |
| `V3-3` | 输入输出日志 | `trace_id`、token 用量、明细与统计、导出与保留期 | ✅ |
| `V3-4` | 工作流 Agent | 计划/执行/确认/暂停恢复、步骤事件、超时与预算 | ✅ |
| `V3-5` | 打磨 | 临时会话、链路时间线、模型分级、反馈、额度等 | ✅ |
| `V4-1` | 会话规模（N1–N3） | 200+ 会话分页与虚拟滚动、标题小模型、工作流并行 | ✅ |
| `V4-2` | 事实版本与检索改写（N9/N8/N4/N7） | query 改写、事实多版回溯、批量操作、搜索防抖 | ✅ |
| `V4-3` | 会话页细节（N5/N6） | 归档计数、时间显示、宽度拖拽 | ✅ |
| `V5-1` | 多格式解析与知识库筛选 | 8 种格式、上传队列、时间范围与关键字筛选 | ✅ |
| `V5-2` | 格式保真与原件预览下载 | DOCX/DOC HTML、Excel 样式表格、原件下载 | ✅ |
| `V5-3` | 自然语言自主规划 | 一句话复合目标自动拆步与执行 | ⏳ 待开发 |
| `V5-4` | 管理员审计与全链路查看 | 日志软删除语义、审计查询导出、用户全景、反审计 | ✅ |
| `UX-1` | 前端优化阶段一 | 品牌/头像/Markdown/滚动/输入区/来源折叠/设计令牌 | ✅ |
| `UX-2` | 前端优化阶段二 | 会话标题、来源富字段、工具真实状态、`done` 元信息 | ✅ |
| `UX-3` | 前端优化阶段三 | 示例问题、侧栏、消息操作、角标、管理页、异常恢复 | ✅ |
| `UX-P1` | P1 细节补齐 | 主流程与管理页缺口、首屏超时、无障碍基础项 | ✅ |
| `UX-P2` | P2 进阶项 | 暗色与响应式进阶、历史分页、进阶无障碍、文档摘要、拆包 | ✅ |

### 5.3 当前进度快照（2026-11-23）

| 项 | 实测值 |
|---|---|
| 后端离线测试 | `304 passed, 2 skipped`（`.venv\Scripts\python.exe -m pytest backend/tests -q`，7.78s） |
| 前端生产构建 | `npm run build` 通过（17.87s）；主包 `index` 约 257 kB，`ui-vendor` 约 1,007 kB（有 >500 kB 提示） |
| 数据库 | PostgreSQL 17.12 / pgvector 0.8.7；`vector(1024)` + HNSW 余弦索引 |
| 本地数据 | `document=5`、`document_chunk=136`、`chat_session=3`、`chat_record=5`、`app_user=2` |
| 最近提交 | `3ac2064`（2026-11-23，V5-4 管理员审计与全链路查看） |
| 待开发 | `V5-3` 自然语言自主任务规划 |

### 5.4 验收报告索引

全部报告位于 `文档/验收报告/`，按统一编号对照：

| 编号族 | 报告文件 |
|---|---|
| 交付总验收 | `交付验收报告.md` |
| 核心链路 `M6`–`M8` | `M6 体验增强验收报告.md`、`M7 治理能力验收报告.md`、`M8 会话体验与可信度验收报告.md` |
| v2 批次（对应 `V2-1`…`V2-5`） | `M1 配置中心验收报告.md`、`M2 输入框固定与顶栏重构验收报告.md`、`M3 联网兜底与能力标注验收报告.md`、`M4 业务库双库查询验收报告.md`、`M5 跨库联表与大结果导出验收报告.md` |
| v3 批次（对应 `V3-1`…`V3-5`） | `M1 会话记忆底座验收报告.md`、`M2 通用对话验收报告.md`、`M3 输入输出日志验收报告.md`、`M4 工作流 Agent 验收报告.md`、`M5 打磨验收报告.md` |
| `V4-1`–`V4-3` | `V4-1 N1 会话规模验收报告.md`、`V4-1 N10-N11 会话页体验验收报告.md`、`V4-2 N9-N8-N4-N7 验收报告.md`、`V4-3 N5-N6 验收报告.md` |
| `V5-1`–`V5-4` | `V5-1 多格式解析与知识库筛选验收报告.md`、`V5-2 格式保真与依赖修复验收报告.md`、`V5-2 原格式预览增强验收报告.md`、`V5-2 原文档下载与在线预览验收报告.md`、`V5-4 管理员审计与全链路查看验收报告.md` |
| `UX-1`–`UX-P2` | `阶段一前端优化验收报告.md`、`阶段二前端优化验收报告.md`、`阶段三前端优化验收报告.md`、`P1细节补齐验收报告.md`、`P2进阶项优化验收报告.md` |

---

## 六、关键设计与安全

- **单库同事务**：文档元数据与切片向量同库；上传入库与删除都在显式事务里完成，无双写补偿。
- **SQL 全参数化**：统计工具枚举白名单；计算器走正则 + AST 白名单，不使用 `eval`。
- **向量维度三重约束**：模型输出维度 = `EMBEDDING_DIM` = 表列 `vector(N)`；启动与入库双重校验。
- **向量写入统一包装**：经 `to_vector()` 写入，避免 pgvector-python 未注册 list dumper 的类型错误。
- **服务端强制鉴权**：Cookie 只存不透明令牌，库内只存 `SHA-256(token)`；`get_current_user / require_admin` 在依赖层校验，前端隐藏按钮只是体验优化。
- **会话私有**：`chat_session.user_id` 归属校验；删除前锁定 owner；越权统一 `40402`，不泄露存在性。
- **密码不落明文**：PBKDF2-SHA256（260k 迭代）+ 随机盐；改密 / 重置 / 禁用即吊销对应登录态。
- **管理员只读 + 留痕**：用户全景与链路查看全部只读；跨用户读取写 `ADMIN_VIEW_USER_DATA`，同对象 60 秒去重，避免审计噪声。
- **日志删除语义自洽**：用户删除是软删除（本人视角不可见），管理员在保留期内仍可查，界面文案与实际能力一致。
- **配额与限流**：每日 token 额度与每分钟请求上限；业务库查询独立限流，避免单用户拖垮服务。
- **最小暴露**：只绑定 `127.0.0.1`；对外部署需自行加 HTTPS、Cookie `Secure`，并用环境变量覆盖默认管理员密码。

---

## 七、常用回归命令

### 7.1 纯离线、零模型调用（日常首选）

```powershell
# 仓库根执行；pytest 需从根收集 backend.tests 包
Set-Location D:\wangzhongmin\data\git_code\RagKnowledge

.venv\Scripts\python.exe -m pytest backend/tests -q      # 纯函数/API/解析/防重复/鉴权/审计等
.venv\Scripts\python.exe backend\scripts\check_env.py    # 依赖、导入、FastAPI 装配、路由注册
.venv\Scripts\python.exe -m compileall -q backend        # 静态字节编译

Set-Location frontend
npm run build                                            # 前端生产构建

# 一键本地离线回归（后端 pytest + check_env + compileall；加 -Frontend 追加 npm ci 与 vite build）
powershell -ExecutionPolicy Bypass -File backend\scripts\offline_regression.ps1
```

当前基线：`304 passed, 2 skipped`。

### 7.2 需要本地 PostgreSQL、但不调用模型（零费用）

| 脚本 | 用途 |
|---|---|
| `check_chat_sse.py` | 真实 SSE 对话链路（`REAL_LLM` 默认 SKIP） |
| `check_hnsw_index.py` | 事务内造数验证 HNSW 执行计划，结束回滚 |
| `check_auth_isolation.py` | 会话归属隔离与越权删除/重命名 |
| `check_auth_http.py` | 认证链路与权限矩阵，临时账号与审计行自动清理 |
| `check_agent_graph.py` | Agent 状态图装配与工具路由 |
| `check_ingest_chain.py` / `check_docs_api.py` | 入库链路与文档接口 |
| `check_maintenance.py` | 重解析替换切片 + HNSW REINDEX，测完清理 |
| `backfill_doc_summary.py` | 历史文档摘要回填（幂等） |
| `eval_memory_window.py` | 记忆窗口与摘要策略离线评估 |

### 7.3 联网执行（按需执行，会产生少量 Embedding / Rerank / LLM 调用费用）

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

### 7.4 CI

`.github/workflows/ci.yml` 在 push/PR 到 `main` 时运行：

- `backend-offline`：安装依赖 → `pytest backend/tests -q` → `check_env.py` → `compileall`；
- `frontend-build`：`npm ci` → `npm run build`。

CI 刻意不接数据库、密钥与联网评测脚本，也不做部署发布；本地等价步骤由 `offline_regression.ps1` 覆盖。

---

## 八、文档与截图

- 文档总索引：`文档/README.md`（按需求与设计、验收报告、开发运维、测试与质量四类归档）。
- 关键文档：
  - `文档/需求与设计/需求文档.md`（主需求）
  - `文档/需求与设计/RagKnowledge 能力增强需求文档 v2.md`–`v5.md`
  - `文档/需求与设计/架构设计文档.md`、`技术架构与技术亮点（面试剖析版）.md`
  - `文档/需求与设计/设计方案-多用户隔离与权限模型.md`、`前端优化需求文档.md`
  - `文档/开发运维指南/运维与回归手册.md`、`PostgreSQL17-pgvector安装指南.md`
- 界面截图：`docs/m1-screens` … `docs/m8-screens`、`docs/v4-screens`、`docs/v5-screens`。

> 维护提示：能力、里程碑、测试与数据计数变化时，请同步更新第五节「当前进度快照」和第一节「能力地图」，避免 README 与实际代码脱节。
