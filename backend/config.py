"""全局应用配置读取。

设计原则：
- 配置来源优先级：环境变量 > .env 文件 > 代码默认值（pydantic-settings 保证）。
- 禁止在业务代码里硬编码密钥、模型名、切片参数、Top-K、向量维度、连接串。
- 运行目录约定为 backend/（`uvicorn main:app` 在 backend 下启动）；
  .env 可放在项目根（../.env）或 backend 本地（./.env），按顺序读取。
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
"""
Pydantic Settings 的取值优先级: 
代码初始化参数 > 系统环境变量 >  .env 文件 > 类字段默认值
"""

# backend/ 目录 = 本文件所在目录；项目根 = 其上一级
BACKEND_DIR: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = BACKEND_DIR.parent


class Settings(BaseSettings):
    """应用配置。字段命名与 .env 中的大写变量自动对应（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),  # 先读项目根 .env，再读 backend/.env
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 服务 ----------
    APP_HOST: str = "127.0.0.1"          # 服务仅监听本机回环地址
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    # ---------- 数据库（PostgreSQL + pgvector，单库） ----------
    DB_DSN: str = "postgresql://postgres:postgres@127.0.0.1:5432/rag_agent"
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 10

    # ---------- LLM（OpenAI 兼容协议，Provider 可配置） ----------
    LLM_PROVIDER: str = "deepseek"
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_API_KEY: str = ""                # 未配置时 LLM 生成能力不可用
    LLM_MODEL: str = "deepseek-chat"
    # WP5-2 模型分级：标题/摘要/事实抽取等轻任务走小模型，回答走主模型。
    # 小模型为空时自动回落主模型，兼容只配置一个模型的现有环境。
    LLM_ROUTING_ENABLED: bool = True
    LLM_SMALL_MODEL: str = ""
    LLM_SMALL_PURPOSES: str = "summary,memory_extract,title,query_rewrite"
    # 轻任务可独立指向另一家 OpenAI 兼容服务（如百炼 Qwen）；留空时回落主模型。
    # 模型名/BaseURL/Key 统一放在 .env，配置中心不再维护模型名，避免两处口径漂移。
    LLM_SMALL_BASE_URL: str = ""
    LLM_SMALL_API_KEY: str = ""
    # N9 多轮检索 query 改写：只影响知识库检索与 rerank，关闭后完全回到原句
    QUERY_REWRITE_ENABLED: bool = True
    QUERY_REWRITE_TIMEOUT_MS: int = 5000
    LLM_TIMEOUT: int = 60
    # 生成参数：可在「配置中心」在线调整，这里是 .env / 代码默认值
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 1024
    # plan 是否优先使用 LLM 结构化决策；False 时回退确定性关键词决策
    LLM_PLAN_ENABLED: bool = True

    # ---------- Embedding（适配器模式；API 文本向量模型） ----------
    EMBEDDING_PROVIDER: str = "api"      # local / api / ollama
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_DIM: int = 1024           # 必须与 document_chunk.embedding 的 vector(N) 一致
    EMBEDDING_BATCH_SIZE: int = 10       # 单批数量还受供应商接口限制约束
    EMBEDDING_API_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_API_KEY: str = ""          # 缺失时入库/检索向量化失败并由调用方降级或报错

    # ---------- 切片 ----------
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # ---------- 检索 ----------
    # 展示 Top-K（最终交给 LLM 的片段数）；可在配置中心在线调整
    TOP_K: int = 5
    # 向量召回候选数（重排的输入规模）；候选数应 >= TOP_K
    RETRIEVAL_CANDIDATES: int = 20
    # 相似度阈值（作用于余弦相似度，不是 rerank_score）；0 表示不过滤
    RETRIEVAL_MIN_SCORE: float = 0.5
    RERANK_ENABLED: bool = False
    RERANK_MODEL: str = "gte-rerank-v2"
    RERANK_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    RERANK_TOP_N: int = 5        # 重排后保留条数；<=0 表示保留全部候选
    RERANK_TIMEOUT: int = 10
    # 来源卡片持久化的相似片段长度；历史短摘要 + 后续按需拉取完整片段
    SOURCE_EXCERPT_CHARS: int = 800
    HNSW_EF_SEARCH: int = 40
    # pgvector 0.8+ 取值：off / relaxed_order / strict_order；0.7.x 无此项，代码需容错
    HNSW_ITERATIVE_SCAN: str = "relaxed_order"
    HNSW_MAX_SCAN_TUPLES: int = 20000

    # ---------- Agent ----------
    HISTORY_ROUNDS: int = 5              # 旧字段：仅兼容旧调用方（v3 起改用窗口治理参数）
    MAX_TOOL_ROUNDS: int = 3              # 工具循环上限，防止重复回跳死循环
    # assess 后是否允许再规划回跳工具；默认按确定性规则收敛，避免额外 LLM 调用
    MULTI_ROUND_ENABLED: bool = True
    # 是否由 LLM 做再决策；True 会增加 LLM 调用，默认 False
    LLM_REPLAN_ENABLED: bool = False
    # 首问标题是否调用 LLM 提炼；False 时走规则提炼，稳定性优先
    SESSION_TITLE_LLM_ENABLED: bool = False
    SESSION_TITLE_MAX_LEN: int = 16

    # ---------- 会话记忆（M1 / WP1）----------
    # 窗口治理：轮数上限 + token 预算双闸门，超预算优先保会话事实/摘要、砍原文轮次
    HISTORY_WINDOW_ROUNDS: int = 8          # 最近 N 轮原文（一问一答 = 1 轮）
    HISTORY_MAX_TOKENS: int = 3000          # 原文窗口 + 事实 + 摘要的总预算（估算值）
    HISTORY_TURN_MAX_TOKENS: int = 400      # 单轮 user+assistant 摘要体的 token 上限
    HISTORY_ANSWER_HEAD_CHARS: int = 300    # answer_digest：保留答案开头字符数
    HISTORY_ANSWER_TAIL_CHARS: int = 150    # answer_digest：保留答案结尾字符数
    # 滚动摘要：累计未摘要轮次超过触发值后压缩，保留最近 N 轮不摘要
    SUMMARY_ENABLED: bool = True
    SUMMARY_TRIGGER_ROUNDS: int = 12
    SUMMARY_KEEP_ROUNDS: int = 8            # 硬不变量：必须 >= HISTORY_WINDOW_ROUNDS
    SUMMARY_MAX_CHARS: int = 400
    SUMMARY_LLM_ENABLED: bool = True        # False 时用规则摘要（抽取问句/首句），不调模型
    # 会话事实：异步抽取，同一 (session, kind, key) 只有一条 active
    SESSION_FACT_ENABLED: bool = True
    SESSION_FACT_EVERY_ROUNDS: int = 4      # 每 N 轮抽取一次
    SESSION_FACT_MAX_TOKENS: int = 300      # 单次抽取注入的对话 token 上限
    SESSION_FACT_MAX_ITEMS: int = 8
    SESSION_FACT_HISTORY_LIMIT: int = 20         # 注入上下文的事实条数上限
    SESSION_FACT_MIN_CONFIDENCE: float = 0.6
    SESSION_FACT_LLM_ENABLED: bool = True   # False 时仅跑规则抽取（离线/评测用）

    # ---------- 会话管理（M8 / WP5-9）----------
    # 长期无新消息的会话自动归档，避免 200+ 会话把侧栏压垮；0 或负数不归档
    SESSION_ARCHIVE_DAYS: int = 30
    # v4 / N1：会话列表默认页大小；前端不传 size 时按该值取
    SESSION_LIST_PAGE_SIZE: int = 50

    # ---------- 通用对话（M2 / WP2）----------
    # 一键合规开关：false 时通用意图回落引导话术，不调用模型
    ALLOW_GENERAL_CHAT: bool = True
    GENERAL_TEMPERATURE: float = 0.7        # 通用创作温度高于知识库（0.3）
    # 内部实体词表（逗号分隔）：命中则强制把 general 降级为 knowledge，防止通用能力抢答内部问题
    INTERNAL_TERMS: str = "报销,审批,员工手册,组织架构,内部制度,考勤制度,薪资制度"

    # ---------- 工作流 Agent（M4 / WP4）----------
    # 计划最多步数；超过直接拒绝并要求拆分任务（§6.4 / §6.11-6）
    WORKFLOW_MAX_STEPS: int = 6
    WORKFLOW_STEP_TIMEOUT: int = 60          # 单步超时（秒）
    WORKFLOW_TASK_TIMEOUT: int = 180         # 单任务整体超时（秒）
    WORKFLOW_AUTO_RUN: bool = False          # 默认先出计划、用户确认后再跑
    WORKFLOW_PARALLEL: bool = True           # v4/N3：无依赖步骤并行总开关；关闭等同并发 1
    WORKFLOW_MAX_PARALLEL: int = 2           # v4/N3：并行上限 1–4，1 表示回到串行
    WORKFLOW_LLM_REFLECT: bool = False       # 默认规则反思，True 时每步多一次 LLM 判断
    WORKFLOW_MAX_REPLANS: int = 2            # 失败后改计划/降级次数上限
    WORKFLOW_BUDGET_SECONDS: int = 180       # 单任务时间预算（与整体超时同口径）
    WORKFLOW_BUDGET_TOKENS: int = 8000       # 展示用预算上限，超时不强制中止

    # ---------- SSE 心跳 ----------
    # 流前置阶段（决策 LLM / 向量化 / Rerank）静默期发送 SSE 注释帧 ": ping" 的间隔（秒）；
    # 前端 sse.js 对 ":" 开头行直接跳过，不产生业务事件，仅用于防止代理/网关静默断连。
    SSE_HEARTBEAT_SEC: float = 10.0

    # ---------- 联网兜底（M3）----------
    # 内部知识不足时是否允许联网检索；关掉后 web 模式等同未配置，直接回落话术
    WEB_SEARCH_ENABLED: bool = True
    # 支持的供应商：bailian（阿里百炼，默认）/ bocha（博查）/ tavily
    # 可在配置中心热切换，切换后只有"供应商默认地址"与"Key 归属"跟着变，兜底语义不变
    WEB_SEARCH_PROVIDER: str = "bailian"
    # 留空 = 用该供应商的默认地址；百炼默认走 DashScope 原生 text-generation 端点
    WEB_SEARCH_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    # 百炼联网问答使用的模型（需支持 enable_search）；留空 = qwen-plus
    WEB_SEARCH_MODEL: str = "qwen-plus"
    # 百炼搜索专用 Key：与 EMBEDDING_API_KEY 同属 DashScope 账号，但用独立变量名，
    # 便于单独轮换/停用；为空时才回落到 EMBEDDING_API_KEY（同厂商，非跨厂商借用）
    BAILIAN_SEARCH_API_KEY: str = ""
    # 其他供应商（博查 / Tavily）各自的 Key，与百炼 Key 互不通用
    WEB_SEARCH_API_KEY: str = ""
    # 显式允许时才把 LLM Key 当搜索 Key；默认关闭，避免跨厂商泄露凭据
    WEB_SEARCH_REUSE_LLM_KEY: bool = False
    # 百炼"搜索+生成"一次完成，耗时比纯搜索 API 长，默认给到 20s
    WEB_SEARCH_TIMEOUT: float = 20.0
    WEB_SEARCH_MAX_RESULTS: int = 5
    # 百炼搜索策略：turbo（默认，速度与效果均衡）/ max（更全但更慢）/ agent（多轮检索，需流式）
    WEB_SEARCH_STRATEGY: str = "turbo"

    # 内部知识不足时的兜底方式：web（联网）/ guide（引导重问）/ contact_admin（联系管理员）
    FALLBACK_MODE: str = "web"
    # 过滤后有效命中少于该条数即判"内部知识不足"，不用残片作答
    FALLBACK_MIN_HITS: int = 2
    FALLBACK_TEXT_GUIDE: str = (
        "内部知识库里没有找到足够相关的内容。方便的话，请补充一点背景："
        "你想了解的是哪份文档、哪个业务流程，或者具体想查的字段与时间范围？描述得越具体，我越容易定位到资料。"
    )
    FALLBACK_TEXT_CONTACT: str = (
        "内部知识库里没有找到足够相关的内容。为避免给出不准确的信息，本次不作答，"
        "请联系系统管理员补充相关文档或开通对应能力。"
    )
    # ---------- 业务库查询（M4）----------
    # 业务库只读 DSN：建议单独建只读角色；留空 = 复用主库 DSN，但仍在 READ ONLY 事务里执行
    BIZDB_DSN_READONLY: str = ""
    # 意图注册表文件（相对 backend 目录）
    BIZ_INTENTS_FILE: str = "biz_intents.json"
    # 内联展示行数上限（超过则只给汇总 + CSV 下载链接，见 M5）
    BIZ_QUERY_INLINE_MAX_ROWS: int = 100
    # 单次查询硬上限：注册表 max_rows 与它取小（默认 3000，对应需求 4.6 的 3000 行用例）
    BIZ_QUERY_HARD_MAX_ROWS: int = 3000
    # 语句超时（秒），超时按 40001 返回，不拖垮连接
    BIZ_QUERY_TIMEOUT: float = 5.0
    # 每个用户每分钟最多查询次数
    BIZ_QUERY_RATE_PER_MIN: int = 10
    # 大结果导出的落盘目录（相对项目根）与下载链接有效期（分钟；0 = 永不过期）
    EXPORT_DIR_NAME: str = "data/exports"
    BIZ_EXPORT_TTL_MINUTES: int = 0

    # ---------- 输入输出运行日志（v3 / WP3）----------
    # 与 operation_log（审计）隔离：这里记录聊天内容，用于排障与质量分析，可配置保留期
    IO_LOG_ENABLED: bool = True
    # 保留天数：超期后由定时任务物理清理（默认 90 天）
    IO_LOG_RETENTION_DAYS: int = 90
    # 写队列容量：队满丢弃并计数，绝不阻塞问答主链路
    IO_LOG_QUEUE_MAX: int = 1000

    # ---------- 管理端审计与查看留痕（v5 R8/R9）----------
    # 管理员查看他人问答/链路的去重窗口（秒）：窗口内重复查看只留一条审计
    ADMIN_VIEW_LOG_DEDUP_SECONDS: int = 60
    # operation_log 保留天数：仅用于管理端展示提示，不自动清理（审计不可删）
    AUDIT_LOG_RETENTION_DAYS: int = 730
    # 用户详情概览统计缓存秒数；0 = 关闭缓存
    ADMIN_OVERVIEW_CACHE_SECONDS: int = 0

    # ---------- 配额与限流（v3 / WP5-6）----------
    # 演示环境防止单个用户把 Key 打爆：日 token 上限 + 每分钟请求数限流。
    # 管理员可在配置中心在线调整；关闭后不做任何拦截。
    QUOTA_ENABLED: bool = True
    QUOTA_DAILY_TOKEN_LIMIT: int = 200000
    QUOTA_RATE_LIMIT_PER_MINUTE: int = 20

    # ---------- 文件上传 ----------
    # 单次请求整体上传的硬上限（/docs/upload、/docs/upload/batch 走这条路径）
    UPLOAD_MAX_MB: int = 10
    UPLOAD_DIR_NAME: str = "data/uploads"
    # 分块上传（/docs/upload/chunk + /docs/upload/complete）相关限制
    # 单文件总大小上限：分块上传让大文件不必一次读进内存，因此这里放宽
    UPLOAD_TOTAL_MAX_MB: int = 100
    # 单个分块大小上限：前端可自选分块大小，但不能超过该值
    UPLOAD_CHUNK_MAX_MB: int = 32
    # 分片落盘目录（相对项目根）与过期清理时长；未完成的上传超过该时长会被清理
    UPLOAD_CHUNK_DIR_NAME: str = "data/uploads/.chunks"
    UPLOAD_CHUNK_STALE_HOURS: int = 24
    # 前端知识库页的默认分块大小与并发数（用户仍可在页面上自行调整，选择会存 localStorage）
    UPLOAD_DEFAULT_CHUNK_MB: int = 4
    UPLOAD_DEFAULT_CONCURRENCY: int = 3

    # ---------- 多格式解析（v5 / R1）----------
    # Excel/CSV 解析上限：防止异常宽表/超长表把内存和切片数拖垮；超限截断并写入标记
    EXCEL_MAX_SHEETS: int = 20
    EXCEL_MAX_ROWS_PER_SHEET: int = 5000
    EXCEL_MAX_COLS: int = 200
    EXCEL_MAX_CELL_CHARS: int = 200
    # .doc 转 .docx 的超时（秒）；支持 LibreOffice 或 Windows Word COM，二者都不可用时明确报错
    DOC_CONVERT_TIMEOUT: int = 60

    # ---------- 默认管理员（演示环境开箱即用）----------
    # 由 scripts/migrate_auth_multitenant.py 首次建库与 scripts/ensure_admin.py 使用；
    # 生产部署请用环境变量覆盖，并登录后立即改密（或把 DEFAULT_ADMIN_PASSWORD 置空改为随机生成）。
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@12345"
    DEFAULT_ADMIN_DISPLAY_NAME: str = "系统管理员"

    # 是否在登录页显示演示账号提示（默认关闭）。
    # 开启后 GET /api/auth/demo-hint 才会返回明文密码；仅在默认密码确实能登录时才展示，
    # 改了密码或禁用账号后自动隐藏，避免给出过期的错误提示。切勿在生产环境开启。
    DEMO_CREDENTIAL_HINT: bool = False

    # ---------- 派生路径 / 列表 ----------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def upload_dir(self) -> Path:
        p = ROOT_DIR / self.UPLOAD_DIR_NAME
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def upload_max_bytes(self) -> int:
        return self.UPLOAD_MAX_MB * 1024 * 1024

    @property
    def upload_total_max_bytes(self) -> int:
        """分块上传时单文件合并后的总大小上限。"""
        return self.UPLOAD_TOTAL_MAX_MB * 1024 * 1024

    @property
    def upload_chunk_max_bytes(self) -> int:
        """单个分片的大小上限。"""
        return self.UPLOAD_CHUNK_MAX_MB * 1024 * 1024

    @property
    def chunk_dir(self) -> Path:
        """分片临时目录；不存在时自动创建。"""
        p = ROOT_DIR / self.UPLOAD_CHUNK_DIR_NAME
        p.mkdir(parents=True, exist_ok=True)
        return p

    def safety_check(self) -> list[str]:
        """启动时执行软性配置检查，返回警告列表；不阻断应用启动。"""
        warnings: list[str] = []
        if not self.LLM_API_KEY:
            warnings.append("未配置 LLM_API_KEY，LLM 生成能力不可用（仅影响 M2 之后链路）")
        if self.EMBEDDING_PROVIDER.lower() == "api" and not self.EMBEDDING_API_KEY:
            warnings.append("EMBEDDING_PROVIDER=api 但未配置 EMBEDDING_API_KEY，向量化（入库/检索）不可用")
        if self.RERANK_ENABLED and not self.EMBEDDING_API_KEY:
            warnings.append("RERANK_ENABLED=true 但未配置 EMBEDDING_API_KEY（Rerank 复用该 Key），重排将回退原序")
        if self.EMBEDDING_DIM <= 0:
            warnings.append("EMBEDDING_DIM 必须为正整数")
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            warnings.append("CHUNK_OVERLAP 应小于 CHUNK_SIZE，否则切片退化为重复窗口")
        if self.SUMMARY_KEEP_ROUNDS < self.HISTORY_WINDOW_ROUNDS:
            warnings.append(
                "SUMMARY_KEEP_ROUNDS 应不小于 HISTORY_WINDOW_ROUNDS，否则摘要水位与原文窗口重叠，最近上下文会丢"
            )
        if self.SUMMARY_TRIGGER_ROUNDS <= self.SUMMARY_KEEP_ROUNDS:
            warnings.append("SUMMARY_TRIGGER_ROUNDS 应大于 SUMMARY_KEEP_ROUNDS，否则摘要永不触发")
        return warnings


@lru_cache
def get_settings() -> Settings:
    """单例配置。各处使用 `from config import settings` 即可。"""
    return Settings()


settings: Settings = get_settings()
