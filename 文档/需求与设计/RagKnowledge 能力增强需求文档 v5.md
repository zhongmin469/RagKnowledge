# RagKnowledge 能力增强需求文档 v5

> 版本：v5.0
> 编写日期：2026-11-20
> 基线：v4 全量交付，V4-1–V4-3 的 N1–N11 已完成；当前 `pytest 304 passed / 2 skipped`（V5-4 新增 10 个用例后）
> 定位：知识库摄取与管理体验增强 + 自然语言任务自主规划 + 管理员审计与全链路查看
> 状态：**V5-1、V5-2、V5-4 已验收（2026-11-20）；V5-3 自主规划待开发**

---

## 0. 本轮输入与需求映射

| 用户优化点 | 本版编号 | 需求摘要 | 优先级 | 阶段 |
|---|---|---|---|---:|---|
| 优化点 1：增加可解析 Excel 类型 | R1 | 知识库支持 `.xlsx` / `.xls` / `.xlsm`，并扩展 `.csv` / `.doc` | P1 | V5-1 |
| 优化点 3：知识库上传 UI 优化 | R2 | 按主流知识库产品重构上传区与上传队列 | P1 | V5-1 |
| 优化点 4：时间筛选 + 名称关键字自动筛选 | R3 | 上传时间范围查询 + 文档名关键字 300ms 自动筛选 | P1 | V5-1 |
| 优化点 5：原文档下载与预览 | R4 | 管理员下载原件；已登录用户可预览 PDF/Markdown/DOCX/Excel | P1 | V5-2 |
| 优化点 2：自然语言描述，自我规划任务过程 | R5 | 自动模式识别复合目标，自动拆步骤；不要求用户先列步骤 | P1 | V5-3 |
| 「删除我的运行日志」提示要优化 | R6 | 删除改为“本人不可见 + 管理员保留期内可查”，纠正确认文案 | P0 | V5-4 |
| 管理员可查其他用户的问答 | R7 | 用户全景：概览/问答/会话/消息/文档/反馈/活动流只读接口 | P1 | V5-4 |
| 管理员可查其他用户的所有操作 | R8 | `operation_log` 查询/导出/动作补全 + 管理端审计页 | P1 | V5-4 |
| 管理员查看权限不可失控 | R9 | 查看他人数据反审计（60 秒去重）+ 只读横幅 | P1 | V5-4 |

版本号采用 **v5.0**：本轮同时增加摄取格式、知识库管理交互和 Agent 任务规划入口，已经不是 v4 的收尾补丁。版本决策见第 10 节。R6–R9 为 2026-11-20 追加的第三批补充需求（管理员审计与用户全链路），决策已确认并已交付 V5-4。

---

## 1. 目标与边界

### 1.1 目标

1. 让知识库从“只吃 PDF / DOCX / Markdown”扩展到常见 Excel 表格、CSV 和旧版 Word，内容可被切片、检索和引用。
2. 把知识库上传从“一个拖拽框”升级为可看懂、可重试、可追踪的多文件上传队列。
3. 让文档列表支持按上传时间范围和文档名关键字定位，减少大知识库里的翻页成本。
4. 让管理员不离开系统就能预览和下载原文档，形成“上传 → 检索 → 核对原件”的闭环。
5. 让用户在对话里只描述目标，由助手自行判断是否需要多步任务、自动拆解步骤并给出计划；不要求用户像任务中心一样先写“第一步、第二步”。
6. 让“用户删除日志”与“管理员审计查看权”的口径自洽：用户删除后本人不可见，管理员在保留期内仍可查，界面如实说明。
7. 给管理员一个“一个入口看全一个用户”的面板：概览、问答、会话与消息、文档、反馈、活动流。
8. 让 `operation_log` 从“只写不读”变成可筛选、可导出、可追溯；管理员查看他人数据必须留痕。

### 1.2 边界

- 不引入 OCR：扫描版 PDF、图片型 Excel 不做文字识别。
- 不做 Office 在线编辑、在线转换 PDF、版式还原；预览以“可读内容”为目标，不承诺像素级还原。
- 不新增写操作类工具：工作流仍只调用知识库、业务库只读查询、计算器、文档统计、联网搜索、通用生成。
- 不默认自动执行任务：先生成计划，用户确认后执行；`WORKFLOW_AUTO_RUN` 仍默认 `false`。
- 不改变现有问答主链路、SSE 事件类型和已有错误码语义。
- 不做文档级权限、文件夹、标签、版本管理；本轮只做单文档的上传、筛选、预览、下载、重解析、删除。
- 新增筛选与下载接口只对管理员开放；预览接口对所有已登录用户开放，普通用户从问答来源卡片触发原文档预览。
- 管理员对他人数据**只读**：不提供修改、删除、代发消息、冒充身份；不展示密码哈希、令牌、完整 IP。
- 用户删除日志改为软删除，**不再物理删除**；管理员可见窗口 = `IO_LOG_RETENTION_DAYS`（默认 90 天）。
- `operation_log` 仍保持“不含聊天正文”的约束，问答原文只存在于 `chat_io_log` / `chat_record`；审计本身不提供删除/清空。

### 1.3 需求追溯

| 本版项 | 现状缺口 |
|---|---|
| R1 | `backend/routers/docs.py` 与 `backend/services/loader.py` 的 `ALLOWED_EXTS / SUPPORTED_EXTS` 仅含 `.pdf/.docx/.md`；环境未安装表格/`.doc` 解析依赖 |
| R2 | `FileUploader.vue` 只有一个拖拽区，`DocsView.vue` 只有一段汇总提示；没有逐文件状态、进度、重试、移除 |
| R3 | `GET /api/docs/list` 只有 `keyword/status`；前端关键字 `watch` 立即请求，没有日期范围，也没有查询按钮 |
| R4 | `document.file_path` 已保存原件路径，`get_document_meta()` 可读，但没有下载/预览路由；`DocTable` 只有重解析和删除 |
| R5 | 任务中心已能 `goal → planner → steps`，但入口仍偏“任务模式/任务中心”，新建任务示例引导用户写“先…再…”，自动模式对复合目标的识别没有形成明确规则 |
| R6 | `DELETE /api/me/io-logs` 物理删除 `chat_io_log` / `llm_call_log`，删除后管理员确实查不到；`UserMenu.vue` 文案明写“管理员也无法查到”；删除动作无审计；删会话会连带物理删除该会话运行日志 |
| R7 | 用户管理只有列表/创建/启禁用/重置密码；会话与消息按 `user_id` 严格隔离，无任何管理员跨用户读取接口 |
| R8 | `operation_log` 已写入 20 类动作但没有任何查询接口；管理员导出 I/O 日志与反馈均未留痕 |
| R9 | 管理员查看他人 trace 无留痕、无只读提示，权限滥用事后不可追查 |

---

## 2. 需求清单

| 编号 | 需求 | 后端 | 前端 | 依赖 |
|---|---|---|---|---|
| R1 | 多格式解析入库（Excel / CSV / DOC） | 是 | 是 | 新增解析依赖 |
| R2 | 知识库上传区与上传队列重构 | 否 | 是 | R1 文件白名单 |
| R3 | 上传时间范围 + 文档名关键字筛选 | 是 | 是 | 无 |
| R4 | 原文档下载与在线预览 | 是 | 是 | R1（Excel/CSV/DOC 预览） |
| R5 | 自然语言任务自主规划 | 是 | 是 | 现有 workflow planner / PlanCard |
| R6 | 删除本人运行日志的语义与文案纠正 | 是 | 是 | `chat_io_log.user_deleted_at` |
| R7 | 管理员用户全景与跨用户只读查询 | 是 | 是 | R6 可见性过滤 |
| R8 | 操作审计查询与导出 + 动作补全 | 是 | 是 | `operation_log` |
| R9 | 管理员查看行为反审计与合规约束 | 是 | 是 | R7/R8 |

---

## 3. 详细需求

### R1 多格式解析入库（Excel / CSV / DOC）

#### R1.1 需求描述

管理员可以上传 `.xlsx`、`.xls`、`.xlsm`、`.csv`、`.doc` 文件。Excel/CSV 按表格转为可检索文本；`.doc` 先转为 `.docx`，再复用现有 Word 提取逻辑。入库后的检索、来源卡片、重解析与删除行为与 PDF/DOCX/MD 一致。

#### R1.2 现状

- 上传白名单只有 `.pdf`、`.docx`、`.md`，新增格式会在路由层直接返回 `40002`。
- `loader.extract_text()` 只分派 Markdown、PDF、DOCX。
- 当前环境未安装 `openpyxl`、`xlrd`、`pandas` 等 Excel 读取库；`python-docx` 已安装，但没有 `.doc` 转换器。
- 本机 Windows 已安装 Word，COM 自动化可用；项目当前没有 `pywin32`，也没有 LibreOffice/antiword。
- `document.file_path` 已保留原文件，重解析可以复用同一路径，不需要新增表字段。

#### R1.3 解析范围

| 格式 | 支持 | 说明 |
|---|---|---|
| `.xlsx` | 是 | 主要格式，读取全部工作表 |
| `.xlsm` | 是 | 按 xlsx 读取，忽略宏 |
| `.xls` | 是 | 旧版二进制格式，使用 xlrd 读取 |
| `.csv` | 是 | 按单表解析，自动识别编码与分隔符 |
| `.doc` | 是 | 旧版 Word 二进制格式，先转 `.docx` 再提取 |

依赖建议：

- `openpyxl`：读取 `.xlsx` / `.xlsm`，`data_only=True` 优先取公式缓存值。
- `xlrd>=2,<3`：读取 `.xls`，不用于 xlsx。
- `csv`：Python 标准库，不新增依赖。
- `pywin32>=306; sys_platform == "win32"`：`.doc` 在 Windows 上通过 Word COM 转 `.docx`；非 Windows 或未安装 Word 时，尝试 LibreOffice `soffice`，都没有则返回明确不可用提示。
- 不引入 pandas，避免为表格解析额外拉入大数据依赖。

#### R1.4 Excel 转文本规则

1. 按工作表顺序输出，每个工作表前插入 `## 工作表：{sheet_name}`，保证切片后仍能知道内容属于哪张表。
2. 识别首个非空行为表头；表头为空时使用 `列1、列2…` 作为兜底列名。
3. 数据行输出为 Markdown 表格；单元格内的换行压成空格，竖线转义，避免破坏表格结构。
4. 合并单元格按左上角值填充到整个合并区域；完全空白的行跳过。
5. 公式优先取缓存计算值；缓存为空时保留公式原文，并在表头前标注“公式未计算”。
6. 日期、时间、百分比、布尔值按单元格显示格式转成可读字符串；不输出 Excel 序列号。
7. 多工作表按顺序拼接，表与表之间空一行；空工作表跳过。
8. 表格内容超过限制时截断并写入明确标记，不允许静默丢数据。

#### R1.5 CSV 转文本规则

1. 编码依次尝试 `utf-8-sig`、`utf-8`、`gb18030`；全部失败时返回 `50003`，提示“CSV 编码无法识别，请另存为 UTF-8”。
2. 用 `csv.Sniffer` 识别逗号、分号、制表符；识别失败时按逗号解析。
3. 首行作为表头，输出为单表 `## 工作表：CSV` + Markdown 表格；表头为空时使用 `列1、列2…`。
4. 单元格内的换行、竖线按 Excel 规则压平/转义；空行跳过。
5. 行数、列数、单格字符上限与 Excel 共用；超限截断并提示。
6. 空文件或只有表头没有数据行：允许入库表头，但 `chunk_count` 必须大于 0；完全空文件返回 `50003`。

#### R1.6 DOC 转文本规则

1. `.doc` 是 OLE 二进制格式，`python-docx` 不能直接读取；必须先转成 `.docx`。
2. 转换优先级：
   - 有 `soffice`：执行 `soffice --headless --convert-to docx --outdir <temp> <file.doc>`，60 秒超时，校验产物存在且非空。
   - Windows 且 `pywin32` 可用：用 Word COM 打开，`Visible=False`、`DisplayAlerts=0`、`AutomationSecurity=3`（禁用宏），`ReadOnly=True`，另存为 `.docx`（`FileFormat=16`）。
   - 两者都不可用：返回 `50003`，提示“当前环境缺少 .doc 转换器，请另存为 .docx 后上传”。
3. 转换在临时目录完成，结束或异常时清理 `.docx` 临时文件；不覆盖原文件。
4. 加密/需要密码的 `.doc`：COM 或 LibreOffice 打开失败时返回 `50003`，提示“暂不支持加密 .doc，请解除密码后上传”；禁止弹出密码输入框。
5. 转换成功后复用现有 `python-docx` 提取：段落、表格文本、标题；不保留页眉页脚、图片、批注和分栏。
6. Word COM 调用必须 `CoInitialize/CoUninitialize`，异常时确保 `Document.Close` 与 `Application.Quit`，避免残留 WINWORD.EXE 进程。
7. 转换失败不得把 `.doc` 当纯文本强读，避免产出乱码切片。

建议上限（首版可先用代码常量，是否配置化见第 10 节）：

| 限制 | 默认 | 目的 |
|---|---:|---|
| 单文件工作表数 | 20 | 防止超多 sheet 拖垮解析 |
| 单工作表有效行数 | 5000 | 控制内存与切片数量 |
| 单工作表列数 | 200 | 防止异常宽表 |
| 单单元格字符数 | 200 | 防止单格长文本撑爆切片 |
| `.doc` 转换超时 | 60 秒 | 防止 Word/转换器卡死 |
| 单文件总切片数 | 沿用现有入库能力，不额外限制 | 由大小上限与切片参数控制 |

超限处理：保留前 N 行/列，并在文本末尾追加 `> 已截断：本工作表共 X 行，仅保留前 N 行`。不要只保留前几行却不提示。

#### R1.7 错误处理

| 场景 | 行为 |
|---|---|
| 后缀不在白名单 | `40002`，提示支持的类型 |
| 文件超过大小限制 | `40003`，沿用现有上传限制 |
| 文件损坏 / 非真实 Excel | `50003`，提示“Excel 文件无法解析，请确认文件未损坏或加密” |
| 加密 / 需要密码的 Excel | `50003`，提示“暂不支持加密 Excel，请解除密码后上传” |
| 所有工作表为空 | `50003`，提示“Excel 没有可提取内容” |
| CSV 编码无法识别 | `50003`，提示另存为 UTF-8 |
| `.doc` 转换器不可用 | `50003`，提示另存为 `.docx` |
| 加密 / 需要密码的 `.doc` | `50003`，提示解除密码；不弹窗 |
| 单元格内容为空但表结构存在 | 允许入库，文本中包含表头与空行说明，不报错 |

#### R1.8 改造点

- `backend/services/loader.py`：新增 `_extract_xlsx`、`_extract_xls`、`_extract_csv`、`_extract_doc`、`_doc_to_docx`，扩展 `SUPPORTED_EXTS`。
- `backend/routers/docs.py`：扩展 `ALLOWED_EXTS`，错误提示同步更新。
- `frontend/src/components/FileUploader.vue`：accept 与前端白名单加入 `.xlsx/.xls/.xlsm/.csv/.doc`；提示文案更新。
- `requirements.txt`：新增 `openpyxl`、`xlrd`、Windows 条件依赖 `pywin32`。
- 重解析、批量上传、分块上传自动复用同一条解析链路，不需要单独实现格式分支。

#### R1.9 验收

- `.xlsx` 单表、多表、中文表头、合并单元格、公式、日期、空行样本各 1 份，均能入库且 `chunk_count > 0`。
- `.xls` 与 `.xlsm` 各 1 份，能入库；解析失败时返回明确错误，不出现 500 堆栈。
- `.csv` 的 UTF-8 与 GBK 样本各 1 份，能识别表头与分隔符；编码错误返回 `50003`。
- `.doc` 的段落 + 表格样本 1 份，经 Word COM 或 LibreOffice 转换后能入库；转换器缺失时返回明确提示。
- 加密的 Excel 与 `.doc` 均返回 `50003`，不弹密码框、不产生残留 Word 进程。
- 用表格/文档中的具体值提问，能检索到对应切片并在来源卡片中显示文件名与工作表名（Excel/CSV）。
- 超过 5000 行的样本被截断且有明确标记，不出现请求超时或内存异常。
- PDF / DOCX / MD 上传、重解析、删除回归通过。
- 前端无效格式提示包含新增后缀，错误提示与后端一致。

---

### R2 知识库上传区与上传队列重构

#### R2.1 需求描述

把当前“一个虚线拖拽框 + 一行分块设置 + 一段上传结果”重构成主流知识库产品的上传体验：上方是清晰的上传入口和限制说明，下方是可逐文件查看状态的上传队列，失败可重试，完成后可清理。

参考业界常见模式：Dropzone 的拖拽热区、云盘产品的逐文件进度、知识库产品的“上传中 / 解析中 / 成功 / 失败”状态分层；不新增 UI 框架依赖，继续使用 Element Plus。

#### R2.2 现状

- `FileUploader.vue` 只有一个拖拽区域，选择文件后直接 emit，父组件串行上传。
- `DocsView.vue` 只有 `uploadProgress` 一行文案和 `uploadReport` 汇总 alert。
- 多个文件时，用户只能看到当前文件的一行进度，看不到排队、失败明细和重试入口。
- 大文件分块上传有百分比，但“上传完成”后还要等待后端解析/向量化，当前没有“处理中”状态。

#### R2.3 目标布局

```text
┌──────────────────────────────────────────────────────────────┐
│ 上传文档                                                     │
│  ┌──────────────────────────────┐  ┌──────────────────────┐  │
│  │  拖拽文件到这里，或点击选择    │  │ 支持格式             │  │
│  │  PDF/DOCX/MD/XLSX/XLS/CSV/DOC │  │ 单文件 ≤ 100MB       │  │
│  └──────────────────────────────┘  │ 大文件自动分块上传    │  │
│                                    └──────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│ 上传队列（3 个文件）                    成功 1 / 失败 1 / 排队 1 │
│ [图标] 报销制度.xlsx   2.4MB   ██████ 100%  处理中…   [移除]  │
│ [图标] 员工手册.pdf    8.1MB   ██████ 100%  成功      [移除]  │
│ [图标] 旧表格.xls      0.6MB   ██░░░░  35%   失败      [重试]  │
├──────────────────────────────────────────────────────────────┤
│ [清除已完成]  [全部重试失败项]                               │
└──────────────────────────────────────────────────────────────┘
```

#### R2.4 交互规则

1. 支持点击多选和拖拽多文件；拖拽进入时高亮热区，离开/放下后恢复。
2. 文件加入队列时先做本地校验：后缀、单文件大小；不合法直接标为“跳过”，不发起请求。
3. 合法文件按队列顺序逐个处理，避免多个文件的解析和 Embedding 同时抢占资源；单文件内部仍按现有“分块大小 + 并发数”上传分片。
4. 每个文件状态：
   - `queued` 排队中
   - `uploading` 上传中（显示分块百分比、已传/总量）
   - `processing` 上传完成，等待后端解析/切片/向量化
   - `success` 成功（显示切片数）
   - `failed` 失败（显示后端错误，提供重试）
   - `skipped` 跳过（格式/大小原因）
5. 失败项重试只重跑该文件；已成功项不重复上传。
6. 支持从队列移除未开始/失败/成功项；上传中的项不允许直接移除，避免前后端状态不一致。
7. 顶部汇总显示“成功 X / 失败 Y / 跳过 Z / 排队 N”，全部结束后保留结果，用户可手动清除。
8. 队列区为空时不显示空表格，显示一句“还没有待上传文件”。
9. 上传期间禁用“重建索引”等高危按钮，避免与入库并发冲突。
10. 分块大小、并发数设置保留，但收进“上传设置”折叠区，默认不抢占主视觉；选择仍存 `localStorage`。

#### R2.5 视觉与可访问性

- 主色只用于主按钮、进度条和成功状态；失败用现有 danger 色，不新造色板。
- 文件类型用短标签 `PDF / DOCX / MD / XLSX / XLS / CSV / DOC`，不使用大图标堆叠。
- 进度条必须有文字百分比，不能只靠颜色表达状态。
- 拖拽区支持键盘聚焦与 Enter 触发文件选择；文件输入保留 `aria-label`。
- 1440 下上传区和队列表格横向舒展；375 下队列行改为两行布局，操作按钮换行，不出现横向滚动。
- 错误文案直接展示后端 `msg`，不展示堆栈、路径或内部错误码；技术细节留在日志。

#### R2.6 改造点

- 新增 `frontend/src/components/UploadQueue.vue`，或把 `FileUploader.vue` 扩展为“上传面板 + 队列”。
- `DocsView.vue` 的上传状态从单个字符串改为 `queue` 数组和汇总对象。
- 复用现有 `uploadDoc`、`uploadDocChunked`；不改后端上传协议。
- `uploadReport` 保留为兼容结构，但页面展示以队列为准，避免两份状态不一致。

#### R2.7 验收

- 一次选择 6 个文件（含 1 个非法格式、1 个超限、1 个模拟失败），队列状态、汇总数字、错误原因全部正确。
- 失败项重试成功后，汇总从失败变为成功；已成功项不重复请求。
- 大文件显示分块百分比，上传完成后进入“处理中”，最终成功并显示切片数。
- 上传期间不能重复提交同一批文件；移除、清除、重试按钮状态正确。
- 1440 与 375 截图各一组，375 无横向溢出。
- 键盘可打开文件选择；进度条有文字百分比。
- 原有单文件、批量、分块上传接口回归通过。

---

### R3 上传时间范围与文档名关键字筛选

#### R3.1 需求描述

知识库列表支持两种筛选：

1. 选择上传时间范围后，点击【查询】按钮执行筛选。
2. 在文档名称输入框输入关键字（例如“图片”），停止输入约 300ms 后自动检索文档名包含该关键字的文档。

#### R3.2 现状

- 后端 `GET /api/docs/list` 支持 `page/size/keyword/status`，`keyword` 使用 `doc_name ILIKE`，中文关键字本身可用。
- 前端 `watch([keyword, statusFilter])` 立即请求，没有防抖；日期范围完全没有。
- 分页使用 `page/size`，筛选后需要重置到第 1 页。
- 当前排序 `doc_id DESC`，与上传时间基本一致。

#### R3.3 后端接口

`GET /api/docs/list` 增加：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `start_date` | `YYYY-MM-DD` | 否 | 上传时间下界，包含当天 00:00:00 |
| `end_date` | `YYYY-MM-DD` | 否 | 上传时间上界，包含当天 23:59:59 |
| `keyword` | string | 否 | 文档名模糊匹配，沿用 `ILIKE` |
| `status` | 0/1/2 | 否 | 沿用现有 |

规则：

- 只传 `start_date`：`create_time >= start_date 00:00:00`。
- 只传 `end_date`：`create_time < end_date + 1 天`。
- 同时传：`start_date <= create_time < end_date + 1 天`。
- `start_date > end_date`：返回 `40001`，提示“开始日期不能晚于结束日期”。
- 日期格式非法：返回 `40001`，不进入 SQL。
- 所有条件与 `keyword/status` 取交集；`total` 返回过滤后的总数。
- 时间语义使用服务器本地日期，和列表展示的 `create_time` 保持一致；不引入 UTC 转换。
- SQL 继续参数化；日期边界在 Python 侧转成 `date`，不要拼接字符串。
- 若 1 万篇文档下日期筛选出现明显全表扫描，再评估补 `idx_document_create_time`；本轮不强制新增索引。

#### R3.4 前端交互

工具栏建议顺序：

```text
[文档名称关键字] [上传时间范围] [状态] [查询] [重置]
```

规则：

1. 关键字输入 300ms 防抖，自动触发查询并重置到第 1 页；清空立即触发。
2. 日期范围使用 `el-date-picker type="daterange"`，提供“今天 / 近 7 天 / 近 30 天”快捷项；选择后不立即请求，点击【查询】才生效。
3. 日期与状态下拉统一由【查询】按钮应用，避免“日期未生效但状态先触发，列表结果混用新旧条件”；关键字保持自动筛选。这是对现有“状态即时生效”的一处行为调整，验收时按新口径执行。
4. 【查询】按钮同时应用当前日期范围、状态和已输入关键字，页码重置为 1。
5. 【重置】清空关键字、日期、状态，恢复全量列表并回到第 1 页。
6. 日期范围变化后，在按钮旁显示“待查询”提示，避免用户以为已经生效。
7. 请求使用序号或 `AbortController` 取消旧请求，防止慢请求覆盖新结果。
8. 空结果区分两种情况：
   - 没有任何文档：提示“暂无文档，上传后在此展示”。
   - 有文档但筛选无命中：提示“没有匹配的文档”，并提供【清空筛选】。
9. 列表上方显示“共 N 篇”，让用户知道筛选是否生效。
10. 375 下工具栏纵向排列，日期选择器宽度自适应，不出现横向溢出。

#### R3.5 验收

- 输入“图片”，300ms 后自动只显示文档名包含“图片”的文档；连续输入不产生每个字符一次请求。
- 选择 `2026-11-01` 至 `2026-11-20`，未点【查询】前列表不变；点击后只显示该范围文档，结束日当天 23:59 的文档也包含在内。
- 开始日期晚于结束日期时，前端阻止请求或后端返回 `40001`，提示明确。
- 关键字 + 日期 + 状态组合筛选，`total` 与列表条数一致。
- 【重置】恢复全量并回到第 1 页。
- 快速切换筛选时，旧请求不会覆盖新结果。
- 375 与 1440 截图通过，无横向溢出。

---

### R4 原文档下载与在线预览

#### R4.1 需求描述

管理员在知识库管理页可以预览和下载原件；普通已登录用户不能进入知识库管理页，但可以在问答来源卡片中预览所引用文档的原件。下载仅管理员可用。预览不改变文档、不触发重解析、不重新向量化。

#### R4.2 现状

- 上传时原件保存在 `data/uploads/{yyyyMMdd}/{timestamp}_{uuid8}.{ext}`，数据库 `document.file_path` 保存相对路径。
- `vector_store.get_document_meta()` 已能返回 `file_path`，但目前只用于重解析，没有对外路由。
- `DocTable` 只有“重解析 / 删除”，没有预览和下载。
- PDF 可由浏览器原生预览；DOCX/Excel/CSV 不能直接由浏览器渲染原始版式；`.doc` 需要先转换。

#### R4.3 接口设计

| 方法 | 路径 | 权限 | 返回 |
|---|---|---|---|
| GET | `/api/docs/{doc_id}/download` | 管理员 | 原文件二进制，`Content-Disposition: attachment` |
| GET | `/api/docs/{doc_id}/preview` | 已登录用户 | PDF 返回 `application/pdf` inline；DOCX/DOC 返回按页渲染字节；其他格式返回 JSON 预览结构 |

预览返回结构建议：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "kind": "docx | markdown | html | sheet",
    "doc_name": "报销制度.docx",
    "content": "",
    "docx_base64": "UEsDBBQ……",
    "truncated": false,
    "sheets": [
      {
        "name": "差旅报销",
        "headers": ["项目", "上限"],
        "rows": [["住宿", "500"]],
        "total_rows": 120,
        "truncated": true,
        "html": "<table>…保留合并单元格、列宽、字体、底色与对齐…</table>",
        "html_total_rows": 121,
        "html_truncated": true,
        "col_widths": [120, 90]
      }
    ]
  }
}
```

- PDF 不走 JSON，直接流式返回原文件，`Content-Disposition: inline`，由前端 `iframe` 打开。
- Markdown 返回原文或渲染所需文本，前端复用 `MarkdownRenderer`，继续走 `marked + DOMPurify`，禁止原始 HTML 执行。
- DOCX 默认返回 `kind=docx` 与 `docx_base64`，前端用 `docx-preview` 在浏览器内按页渲染，保留纸张尺寸、页边距、分页、页眉页脚、表格、图片与字体；单文件上限 6 MB，超过上限或前端渲染失败时改用语义 HTML。
- `.doc` 复用 R1 的转换结果先转 `.docx`，再按 DOCX 规则返回按页渲染字节；转换器缺失时明确提示下载原件。
- `GET /api/docs/{doc_id}/preview?html=1` 为 DOCX/DOC 的显式 HTML 降级入口，返回 `kind=html`；保留标题层级、粗体/斜体、列表、表格和正文段落。
- CSV 返回 `kind=sheet`，按单表返回表头和前 N 行，并附带带列标/行号的基础 HTML 表格；工作表名固定为 `CSV`。
- Excel 返回 `kind=sheet`，按工作表返回表头与前 N 行；额外返回 `html`，保留合并单元格、列宽、字体、底色、边框、对齐与常见数字格式，并生成 Excel 式列标（A/B/C）与行号列。
- 其他格式返回 `40002`“该格式暂不支持在线预览，请下载原文件”。

#### R4.4 安全与文件定位

1. 下载接口使用 `require_admin`；预览接口使用 `get_current_user`，要求已登录但不要求管理员。知识库管理页仍只对管理员展示，普通用户从问答来源卡片触发预览。
2. 根据 `doc_id` 查 `document.file_path`，不接受前端传任意路径。
3. 将 `file_path` 解析为绝对路径后，必须确认仍在 `settings.upload_dir` 目录内；拒绝 `..`、绝对路径、符号链接逃逸。
4. 文件不存在时返回 `40407`“原文件不存在，可能已被清理”；文档不存在仍返回 `40401`。
5. 下载文件名使用 `Content-Disposition` 的 `filename*`（RFC 5987）编码，兼容中文名；禁止把原始文件名直接拼进响应头。
6. 响应不暴露服务器绝对路径、数据库路径或堆栈。
7. 下载操作写入 `operation_log`，记录 `doc_id`、文件名和字节数；预览不强制写审计，避免高频日志膨胀。
8. 预览读取上限：文本最多 200,000 字符；Excel 每表最多 100 行、最多 10 个工作表；超限返回 `truncated=true` 并在前端提示。

#### R4.5 前端交互

`DocTable` 操作列改为：

```text
预览 | 下载 | 重解析 | 删除
```

- `DocTable` 仅管理员可见，四个操作都可用；下载按钮不向普通用户暴露。
- 新增共享预览弹窗 `DocPreviewDialog.vue`，知识库管理页和问答来源卡片共用，避免两套预览逻辑。
- `SourceCard` 展开态新增【预览原文】：仅对知识库来源（`!isWeb` 且有 `doc_id`）显示，所有已登录用户可用；不显示下载按钮。
- 预览弹窗：
  - 顶部显示文档名、类型、大小、上传时间、切片数。
  - PDF：`iframe` 内嵌，加载失败显示“无法预览，请下载原件”。
  - Markdown：使用现有 `MarkdownRenderer` 渲染，链接继续只允许 `http/https/mailto`。
  - DOCX / DOC：前端动态加载 `docx-preview`，按 A4 纸张和原页边距分页渲染，支持缩放、适合宽度与页数提示；渲染容器带纸张阴影和页间距，接近 Word 阅读视图。渲染失败时自动请求 `?html=1` 降级为 `SafeHtml` 语义视图，不直接报错。
  - Excel / CSV：工作表标签放在底部，表格带 Excel 列标（A/B/C）与行号列，表头与行号 `sticky` 固定；提供缩放、适合宽度，表格区域横向可滚动；显示“共 X 行，预览前 100 行”。
  - DOCX 在 375 宽度下自动按“适合宽度”缩放，默认落在可读比例；Excel 375 下保留列标/行号与缩放控件，不出现页面级横向溢出。
  - 不支持：显示“该格式暂不支持在线预览”并给出下载引导；普通用户只显示提示，不显示下载按钮。
- 下载：点击后请求 `download` 接口，浏览器保存原文件；失败时用统一错误提示，不把 JSON 错误当文件保存。
- 375：预览弹窗全屏，表格横向滚动；操作按钮在表格行内换行或收进“更多”菜单，不出现横向溢出。
- 上传中/处理中的文档允许下载原件，但预览按钮根据 `status` 给出“文档处理中，暂不可预览”提示；失败文档允许下载原件排查。

#### R4.6 验收

- PDF、Markdown、DOCX、XLSX、CSV、DOC 各 1 份，预览内容可读；PDF 使用浏览器原生预览；DOCX/DOC 按页渲染，标题、粗体、列表、表格、页边距与分页位置与原件大体一致；Excel/CSV 保留合并单元格、列宽、字体与底色，并显示列标和行号。
- DOCX 预览工具栏显示“共 N 页”，缩放按钮可用；强制 `?html=1` 时能降级到语义 HTML，页面不白屏、不报错。
- Excel 预览底部工作表标签可切换；列标 A/B/C 与行号 1/2/3 固定，横向滚动时仍可见。
- 上传 8 种后缀（`.pdf/.docx/.md/.xlsx/.xlsm/.xls/.csv/.doc`）全部成功；启动时校验 `openpyxl`、`xlrd`、`python-docx`、`mammoth`，缺依赖时给出明确安装命令，不允许到上传阶段才报“缺少 openpyxl”。
- 下载文件与上传文件字节一致，SHA-256 相同；中文文件名下载后名称正确。
- `.xls` 预览显示工作表名、表头与前 100 行及基本样式；超过 100 行有截断提示；CSV 单表预览正常。
- 管理员可预览、可下载；普通已登录用户可预览，但调用下载接口返回 `40303`。
- 普通用户从问答来源卡片打开预览弹窗成功，页面不暴露知识库管理入口。
- Markdown 中的 `<script>` 或 `javascript:` 链接不执行；预览不产生 XSS。
- 构造 `../`、绝对路径、符号链接逃逸请求，均被拒绝，不返回目录内容。
- 文件被手动删除后，预览/下载返回 `40407`，文档列表仍可删除该记录。
- 下载审计记录存在；预览不产生大量审计噪声。
- 1440 与 375 截图通过；无横向溢出。

#### R4.7 修复补丁：依赖自愈与格式保真（2026-11-20）

**问题 1：上传 Excel 报“缺少 openpyxl 依赖”**

- 根因：后端被 `C:\Python312\python.exe` 启动，绕过了项目 `.venv`，导致 `.venv` 中已安装的 `openpyxl`/`xlrd` 不可见。
- 修复：
  1. `backend/scripts/run_dev.py` 启动时检测当前解释器；若不是项目 `.venv`，自动用 `.venv\Scripts\python.exe` 重新执行入口。
  2. 启动前检查 `openpyxl`、`xlrd`、`python-docx`、`mammoth`，缺失时打印 `pip install -r backend/requirements.txt` 并退出，避免运行到上传阶段才失败。
  3. `backend/requirements.txt` 明确加入 `mammoth>=1.8`。
- 验收：八种后缀逐一真实上传成功；启动日志显示使用 `.venv`。

**问题 2：DOCX/DOC 预览是纯文本，Excel 丢失版式**

- 根因：V5-2 首版预览只做“可读内容”，DOCX 走 `loader.extract_text` 返回纯文本，Excel 只把值塞进 `el-table`，样式与合并单元格全部丢失。
- 修复：
  1. 新增 `backend/services/preview_html.py`：DOCX 用 `mammoth` 转语义 HTML；`.doc` 先转 `.docx` 再转 HTML；Excel 生成带单元格样式、合并单元格、列宽与行高的 HTML 表格；`.xls` 用 xlrd 读取格式信息；CSV 生成基础表格。
  2. 预览协议新增 `kind=html` 与 `sheets[].html/html_total_rows/html_truncated/col_widths`；旧 `headers/rows` 保留，兼容原有调用方。
  3. 前端新增 `SafeHtml.vue`，统一用 `DOMPurify` 消毒；`DocPreviewDialog` 增加 DOCX/DOC HTML 分支与 Excel 样式表格分支。
  4. 样式保留范围：标题层级、粗体/斜体、列表、表格、合并单元格、列宽、字体、字号、颜色、底色、边框、对齐和常见数字/日期格式。
- 验收：DOCX 首页标题为 `<h1>`、加粗文本为 `<strong>`、表格带 `doc-table` 类；Excel HTML 含 `colspan`、字体加粗与底色；1440/375 弹窗无横向溢出。

**仍有边界**

- 以下边界为“语义 HTML 降级链路”的边界；默认 DOCX 按页渲染由 R4.8 提供，已覆盖页眉页脚、分页与 A4 纸张。
- `.doc` 格式保真仍依赖 LibreOffice 或 Windows WPS/Office COM；缺失转换器时只能下载原件。
- Excel 图表、条件格式、图片和透视表不进入预览；这些对象仍可通过下载原件查看。

#### R4.8 原格式预览增强（2026-11-20）

**目标**

在不新增文档服务、不引入 LibreOffice/OnlyOffice/Collabora 的前提下，用纯前端只读组件把 DOCX/DOC 和 Excel/CSV 的预览体验拉到“接近 Office 原文件”。验收口径固定为：内容结构正确、样式大致保留、接近 Office 原文件，接受只读，不承诺可编辑和像素级一致。

**方案**

1. DOCX/DOC 改为“原字节 + 前端按页渲染”，不再默认走 mammoth 语义 HTML。
   - 后端 `_docx_preview()`：`.docx` 直接读原文件；`.doc` 先用现有转换器转 `.docx`，复用同一份字节。
   - 文件不超过 `PREVIEW_DOCX_MAX_BYTES = 6 MB` 时返回 `kind=docx`、`docx_base64`，并令 `content=""`、`truncated=false`。
   - 超过上限时回退 `mammoth` 语义 HTML，避免把大文件塞进 JSON。
   - `preview_html.py` 拆出 `_docx_stream_to_html()`、`docx_to_html()`、`docx_bytes_to_html()`、`doc_to_docx_bytes()`、`doc_to_html()`，`.doc` 只转换一次即可复用。
   - `GET /api/docs/{doc_id}/preview?html=1` 提供显式降级；前端渲染异常时自动调用，不把技术错误直接抛给用户。
2. 前端 `DocPreviewDialog.vue` 新增 `kind=docx` 分支。
   - 动态 `import('docx-preview')`，`renderAsync()` 渲染到独立容器；`className='rag-docx'`、`inWrapper=true`、`breakPages=true`，渲染页眉页脚、脚注与分页，关闭批注、修订与 `altChunks`。
   - 渲染后清理脚本、iframe、object、embed、`on*` 事件属性、危险链接和非 `data/blob` 图片，保持只读与 XSS 防护。
   - 页面外层加纸张阴影、页间距、缩放与“适合宽度”；顶部显示“共 N 页”。
3. Excel/CSV 增加 Office 式坐标轴。
   - `_sheet_table_html()` 统一生成 `<colgroup>`、左上角 corner、列标 `A/B/C…` 与行号 `1/2/3…`。
   - `_xlsx_sheet_html()` 每行生成 `sheet-rowhead`，表头生成 `sheet-colhead`，继续保留 openpyxl 的合并单元格、列宽、行高、字体、字号、颜色、底色、边框、对齐与数字格式。
   - `_xls_sheet_html()` 使用 `xlrd.formula.colname` 生成列标；`csv_to_html()` 同样补列标/行号，表头作为第 1 行。
   - 前端工作表标签移到底部，新增“表格”工具栏：缩小、放大、适合宽度；表头与行号 `sticky`，横向滚动时保持可见。
4. 375 适配。
   - DOCX 打开后自动按“适合宽度”缩放并计算比例，避免初始只看到纸张左上角。
   - Excel 表格在弹窗内部滚动，页面级横向溢出必须为 0。
5. 修复“DOCX 仍显示旧 HTML”的挂载时序问题。
   - 根因：`load()` 先置 `loading=true`，写入 `preview` 后立刻 `nextTick` 调 `renderDocx()`；外层 `v-if="loading"` 尚未卸载，`docxBody` ref 为空，渲染函数直接走 HTML 降级。
   - 修复：写入 `preview` 后先把 `loading=false`，再 `await nextTick()`，确保预览容器与 ref 已挂载后再渲染；其余分支同样调整，Excel 移动端自动适配也因此生效。

**依赖与构建**

- 前端新增 `docx-preview@^0.3.7`，动态 import 后单独 chunk；`package-lock.json` 同步更新。
- 不新增后端进程、端口或文档服务；仍然只依赖现有 FastAPI + Vite。

**安全与边界**

- 预览接口仍要求登录；下载仍仅管理员。DOCX 原字节会以 base64 返回给已登录用户，属于“可预览但不可下载”的现有产品口径，本轮不改变权限模型。
- `docx-preview` 产物统一走前端清洗；后端不使用浏览器执行任何文档脚本。
- 只读预览，不支持编辑、批注、修订留痕、表单填写和宏。
- 6 MB 以上 DOCX、复杂浮动文本框、艺术字、SmartArt、Excel 图表/条件格式/透视表仍可能降级或丢失；这些边界在验收报告中如实记录。

**验收**

- DOCX/DOC 打开后出现纸张页面、页边距、分页和“共 N 页”，不再直接显示语义 HTML；375 下自动适合宽度且无横向溢出。
- Excel/XLS/XLSM/CSV 显示列标、行号和底部工作表标签；合并单元格、字体、底色、边框、对齐保持；缩放按钮生效；375 无页面级横向溢出。
- `?html=1` 降级可用；前端渲染异常时自动降级。
- 后端定向测试覆盖 `kind=docx`、base64 解码、`?html=1`、Excel 列标/行号；前端 `npm run build` 通过。

---

### R5 自然语言任务自主规划

#### R5.1 需求描述

用户在“自动”模式下只需描述想完成的结果，例如：

> 把知识库里报销相关制度整理一下，对比差旅和日常报销的额度，最后给我一份结论。

系统自行判断这是复合目标，调用现有 workflow planner 拆成若干步骤，展示计划卡；用户确认后执行。用户不需要先写“第一步查知识库、第二步统计、第三步总结”。

任务中心保留，但定位为“查看历史任务和详情”，不再是唯一入口；新建任务也只要求写目标，不要求写步骤。

#### R5.2 现状

- `backend/services/workflow.py` 的 `plan_task(goal, ...)` 已经接收自然语言目标，由 LLM 生成 `steps`，并有步数、工具白名单、参数 schema、权限、危险动作校验。
- 对话 `chat.py` 在 `intent=workflow` 时调用 `plan_task`，通过 `workflow` SSE 帧返回 `task`，前端 `PlanCard` 已支持开始、暂停、取消、继续和步骤时间线。
- `WORKFLOW_AUTO_RUN` 默认 `false`，计划生成后停在 `awaiting_confirm`。
- 缺口不在“有没有 planner”，而在：
  1. 自动模式对“复合目标”的识别规则不明确，用户可能仍要手动切到“任务”模式。
  2. 任务中心新建任务占位文案引导用户写“先查询…再统计…”，强化了“用户先列步骤”的心智。
  3. 计划卡只展示步骤，缺少“规划假设/需要补充的信息”，目标含糊时容易直接编步骤。
  4. 规划失败时只提示“调整描述”，没有“补一个关键信息/拆成两个任务”的明确下一步。

#### R5.3 自动识别规则

在 `自动` 模式下，满足以下任一条件时优先进入 `workflow` 规划；否则保持单步问答：

1. 目标包含两个及以上不同动作，例如“查询/统计/对比/汇总/生成/整理/导出”。
2. 目标包含两个及以上交付物，例如“既要…又要…”“并给出建议/报告/清单”。
3. 目标需要跨能力，例如知识库 + 业务库、知识库 + 计算、统计 + 生成。
4. 用户明确说“帮我完成/整理/规划/分几步做/做个方案”，但没有给出步骤。
5. LLM 意图分类返回 `workflow` 且置信度达到阈值。

不进入 workflow 的情况：

- 单问单答：“报销标准是什么”“文档总数是多少”“算一下 12*8”。
- 纯知识库检索或纯业务库查询，即使问题较长，只要不需要多步编排。
- 用户明确选择“仅知识库 / 仅通用 / 业务库”模式时，不自动改走 workflow。
- 目标含糊到无法确定对象或交付物时，先 `clarify`，不要硬拆步骤。

#### R5.4 规划输出要求

沿用现有 `plan_json` 结构，新增可选字段：

```json
{
  "goal": "……",
  "assumptions": ["按当前知识库全部文档理解", "金额单位按人民币"],
  "steps": [
    {
      "id": "s1",
      "title": "检索报销相关制度",
      "tool": "knowledge_search",
      "args": {"query": "报销 差旅 日常 额度"},
      "depends_on": []
    }
  ],
  "budget": {"max_seconds": 180, "max_tokens": 8000}
}
```

- `assumptions` 只写会影响执行结果的必要假设，不输出模型思维链。
- 每一步必须有 `title`、`tool`、`args`、`depends_on`；工具只允许现有白名单。
- 最多 6 步；超过时返回“请拆分为两个更小的任务”，不生成半截计划。
- 目标缺少关键对象/时间/范围时，planner 应返回 `clarify` 或计划中明确假设；不得编造企业内部数据。
- 计划生成后默认 `awaiting_confirm`；只有用户点“开始执行”或管理员把 `WORKFLOW_AUTO_RUN` 设为 `true` 才执行。
- 不在计划卡展示内部推理过程，只展示目标、假设、步骤、依赖、工具和预算。

#### R5.5 对话与任务中心文案

- 模式选择器“任务”提示改为：“描述目标即可，系统自动拆解步骤；确认后执行。”
- 任务中心“新建任务”占位文案改为：“例如：整理知识库里报销相关制度，对比差旅和日常额度，并给出结论。”
- 删除“先查询…再统计…”这类引导用户写步骤的示例。
- 计划生成后的对话文案明确：“已根据目标拆成 N 步，确认后开始执行；如需调整目标，直接补充说明。”
- 规划失败时按原因给下一步：
  - 目标太泛：提示补充对象、范围或交付物。
  - 超过 6 步：提示拆成两个任务。
  - 工具/权限不满足：说明哪一步被跳过或无法执行。
  - 模型不可用：提示稍后重试或改用单步问答。

#### R5.6 改造点

- `backend/agent/decision.py`：补充复合目标启发式；保留 LLM 分类与置信度。
- `backend/prompts.py`：调整 `WORKFLOW_PLAN_SYSTEM_PROMPT`，明确“用户只给目标，不要求用户列步骤；必要时给假设或澄清”。
- `backend/services/workflow.py`：解析 `assumptions`；计划校验增加该字段的可选校验；规划失败原因结构化。
- `backend/routers/chat.py`：自动模式命中 workflow 时复用现有 `plan_task`；不新增 SSE 事件类型。
- `frontend/src/components/PlanCard.vue`：展示“规划假设”折叠区；不改变现有执行按钮。
- `frontend/src/views/WorkflowView.vue` / `ModeSelector.vue`：文案调整。
- 不新增任务表字段；`assumptions` 存在 `plan_json` 内即可。

#### R5.7 验收

用 10 条固定用例验收：

| # | 输入 | 期望 |
|---:|---|---|
| 1 | 整理知识库报销制度，对比差旅和日常额度，给结论 | 进入 workflow，3–6 步，含 knowledge_search + general_chat |
| 2 | 统计文档总数和失败文档数，再给清理建议 | 进入 workflow，含 doc_stats + general_chat |
| 3 | 查上月订单总额并按地区拆分 | 进入 workflow 或 biz 单步 + 生成；不得编造数据 |
| 4 | 总结这份文档并列出待办 | 进入 workflow，含 knowledge_search + general_chat |
| 5 | 报销标准是什么 | 不进入 workflow，直接知识库回答 |
| 6 | 文档总数是多少 | 不进入 workflow，直接 doc_stats |
| 7 | 帮我处理一下 | 先 clarify，不生成计划 |
| 8 | 删除所有文档 | 拒绝，不生成写操作计划 |
| 9 | 一个需要 8 步的目标 | 返回拆分提示，不生成半截计划 |
| 10 | 目标含两个交付物但未说明范围 | 生成计划并展示 assumptions，或先澄清 |

验收口径：

- 10 条中至少 9 条路由正确；简单问答不得被误判为 workflow。
- 生成计划 100% 通过现有工具白名单、参数 schema、步数、危险动作校验。
- 计划默认停在 `awaiting_confirm`，不自动执行；点“开始执行”后正常出步骤事件。
- 计划卡展示目标、假设、步骤、依赖、工具；步骤数量 ≤6。
- 规划失败有明确原因和下一步，不只返回“失败”。
- 现有任务中心计划/执行/暂停/取消/恢复回归通过。

---

### R6 删除本人运行日志的语义与文案纠正

#### R6.1 需求描述

用户在个人菜单里删除自己的运行日志时，现状提示为“将物理删除你本人的全部问答运行日志（含问题与回答原文），删除后管理员也无法查到，且不可恢复”。这与产品定位冲突：管理员需要能查其他用户的操作、问答与运行日志链路，用于问题定位与合规审计。

因此把“用户删除”定义为**从用户本人视角删除**：用户侧立即不可见、不可导出；系统仍保留完整记录，管理员在日志保留期内（默认 90 天，跟随 `IO_LOG_RETENTION_DAYS`）可查看；超过保留期由既有清理机制正常回收。界面文案必须如实说明，不得再宣称“管理员也查不到”。

#### R6.2 实现口径

| 项 | 规则 |
|---|---|
| 删除范围 | `DELETE /api/me/io-logs` 作用于当前用户本人全部 `chat_io_log` 记录（含问答原文与检索片段） |
| 删除方式 | 软删除：`UPDATE chat_io_log SET user_deleted_at = now() WHERE user_id = ? AND user_deleted_at IS NULL` |
| 已删除的数据 | 用户侧列表、详情、导出全部不可见；重复删除返回 `removed=0`，幂等 |
| 管理员侧 | `GET /api/admin/io-logs` 默认可见全部（含已软删除），并返回 `user_deleted` 标记；支持 `include_deleted` / `only_deleted` 显式筛选 |
| 会话删除联动 | 删除会话时，该会话下的运行日志同样只做软删除，不物理删除，避免链路断档 |
| 管理员详情 | `get_detail(trace_id, include_deleted=True)` 可读已软删除记录，读取时写 `ADMIN_VIEW_USER_DATA` 审计 |
| 审计 | 用户删除写 `USER_LOG_DELETE`（detail `{removed, mode:"soft"}`）；导出写 `USER_LOG_EXPORT`；删除会话写 `SESSION_DELETE` |

#### R6.3 前端文案（必须一致）

确认弹窗正文：

> 删除后，你本人将无法再查看或导出这些运行日志；管理员在日志保留期内（当前 90 天）仍可查看，用于问题定位与合规审计。

成功提示：`已从你的视角删除 N 条运行日志`。

个人设置区补充说明：管理员具备审计查看权限，可查看本人在保留期内的问答与运行日志；该权限受审计留痕约束。

#### R6.4 改造点

- `backend/services/io_log.py`：`chat_io_log` 增加 `user_deleted_at`；`delete_user_logs` / `delete_session_logs` 改为软删除；`_filters` 支持 `include_deleted` / `only_deleted`；`_row_to_dict` 派生 `user_deleted`。
- `backend/routers/user_io.py`、`backend/routers/session.py`：写审计。
- `frontend/src/components/UserMenu.vue`：文案与提示纠正。
- `frontend/src/views/IoLogView.vue`：管理员视图增加“删除状态”列与三态筛选。

#### R6.5 验收

1. 用户删除后，`/api/me/io-logs` 计数为 0，导出返回空；
2. 同一 trace 管理员列表可见且 `user_deleted=true`，详情可读；
3. 再次删除返回 removed=0；
4. 删除会话后该会话日志管理端仍可查；
5. `operation_log` 出现 `USER_LOG_DELETE`，detail 含 `mode=soft`；
6. 文案中不再出现“管理员也无法查到”。

---

### R7 管理员用户全景与跨用户只读查询

#### R7.1 需求描述

管理员需要在用户管理里点开一个用户，就能看到该用户的“全链路”：概览、问答记录、会话列表、会话消息、文档、反馈、活动流。全部**只读**，不提供代发、修改、删除。

#### R7.2 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/users/{user_id}/overview` | 账号信息 + 总量（问答/会话/文档/反馈/审计）+ 近 7 天/30 天问答数 + 已删除问答数 + 最近登录/最近问答 |
| GET | `/api/admin/users/{user_id}/qa` | 该用户问答记录分页，含 `user_deleted` 标记 |
| GET | `/api/admin/users/{user_id}/sessions` | 该用户会话分页 |
| GET | `/api/admin/users/{user_id}/sessions/{sid}/messages` | 会话消息只读分页；非该用户会话返回 `40402` |
| GET | `/api/admin/users/{user_id}/documents` | 该用户上传文档分页 |
| GET | `/api/admin/users/{user_id}/feedback` | 该用户反馈分页 |
| GET | `/api/admin/users/{user_id}/activity` | 统一时间线：`chat_io_log` 与 `operation_log` 合并，`type` 取 `qa/login/doc/export/admin/other` |

统一约束：全部 `require_admin`；用户不存在返回 `40403`；日期参数非法返回 `40001`；不返回密码哈希、令牌、完整 IP。

#### R7.3 前端

- `UsersView.vue` 操作列新增「查看」，打开 `AdminUserDetailDrawer.vue` 右侧抽屉。
- 抽屉 6 个 Tab：概览 / 问答记录 / 会话 / 文档 / 反馈 / 活动流；会话支持只读查看消息弹窗。
- 抽屉顶部固定只读审计横幅：说明“本次查看会记入审计日志，被查看用户可追溯”。

#### R7.4 验收

1. 管理员可对任意普通用户打开 6 个 Tab 并分页；
2. 普通用户访问任一 `/api/admin/users/*` 返回 `40303`；
3. 指定非本用户会话消息返回 `40402`，不泄露存在性以外的信息；
4. 打开概览与消息均写 `ADMIN_VIEW_USER_DATA`；
5. 抽屉在 1440 与 375 宽度下可用（窄屏为全宽抽屉、Tab 横向滚动）。

---

### R8 操作审计查询与导出 + 动作补全

#### R8.1 需求描述

`operation_log` 已在大量路径写入，但此前没有任何读取入口，等于“只写不查”。本轮补齐查询、筛选、导出，并把缺口动作补上，使管理员能按人、按动作、按时间、按对象追溯所有操作。

#### R8.2 动作补全

新增动作常量与中文名：

| action | 中文名 | 触发点 |
|---|---|---|
| `USER_LOG_EXPORT` | 导出本人运行日志 | `GET /api/me/io-logs/export` |
| `USER_LOG_DELETE` | 从本人视角删除日志 | `DELETE /api/me/io-logs` |
| `SESSION_DELETE` | 删除会话 | 删除单个会话 |
| `SESSION_DELETE_BATCH` | 批量删除会话 | 批量删除 |
| `ADMIN_VIEW_USER_DATA` | 查看他人数据 | 管理员读取他人 trace / 用户全景 |
| `ADMIN_IO_EXPORT` | 管理员导出运行日志 | `GET /api/admin/io-logs/export` |
| `AUDIT_EXPORT` | 导出审计日志 | `GET /api/admin/audit-logs/export` |
| `FEEDBACK_EXPORT` | 导出反馈 | `GET /api/admin/feedback/export` |

`operation_log` 增加 `idx_operation_log_target` 支撑按对象检索；本轮累计动作枚举 20 个。

#### R8.3 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/audit-logs` | 分页查询：`user_id` / `action` / `target_type` / `target_id` / `start_date` / `end_date` / `keyword` |
| GET | `/api/admin/audit-logs/actions` | 动作枚举 + 中文名，供前端下拉 |
| GET | `/api/admin/audit-logs/export` | CSV 导出，上限 1 万行，导出本身写 `AUDIT_EXPORT` |

同时 `GET /api/admin/feedback` 增加 `user_id` 筛选；`GET /api/admin/io-logs` 增加 `include_deleted` / `only_deleted`。

#### R8.4 前端

新增 `AuditLogView.vue`（菜单「操作审计」）：筛选条（用户、动作、对象、时间、关键字）+ 表格 + detail 展开 + 导出按钮；`api/adminAudit.js` 封装。

#### R8.5 验收

1. 按 `user_id` 过滤命中该用户全部动作；按 `action` 过滤命中对应动作；
2. 导出 CSV 行数 = 查询结果（≤1 万），且导出后新增一条 `AUDIT_EXPORT`；
3. 动作枚举返回 20 项且每项有中文名；
4. 非管理员访问返回 `40303`；
5. 日期非法返回 `40001`，不到 SQL 层报错。

---

### R9 管理员查看行为反审计与合规约束

#### R9.1 需求描述

管理员能看他人数据，就必须能追查“谁在什么时候看了谁”。所有跨用户读取都要留痕，并在界面明确告知；同时避免翻页、刷新产生海量噪音。

#### R9.2 规则

| 项 | 规则 |
|---|---|
| 留痕范围 | 管理员读取他人 trace 详情、用户全景概览、会话消息 → `ADMIN_VIEW_USER_DATA` |
| 去重 | 同一管理员对同一对象同一动作，`ADMIN_VIEW_LOG_DEDUP_SECONDS`（默认 60 秒）内只记一次 |
| 自身数据 | 管理员查看自己的数据不记 `ADMIN_VIEW_USER_DATA` |
| 保留 | 审计日志永久保留，不自动清理（`AUDIT_LOG_RETENTION_DAYS=730` 仅作为容量评估参考，不做删除） |
| 可见性回显 | 用户全景概览返回 `viewed_by_admin`，让被查看事实可被追查 |
| 界面提示 | 他人 trace 抽屉显示橙色只读审计横幅；用户详情抽屉顶部同类横幅 |

#### R9.3 改造点

- `backend/services/audit.py`：新增 `view_dedup_ok()`（内存 dict + 锁 + monotonic）与 `log_view()`。
- `backend/routers/admin_io.py`：他人 trace 以 `include_deleted=True` 读取并写审计。
- `frontend/src/components/TraceDrawer.vue`：新增 `adminView` / `ownerLabel` props 与审计横幅。

#### R9.4 验收

1. 60 秒内重复打开同一用户概览只产生 1 条 `ADMIN_VIEW_USER_DATA`；
2. 隔 60 秒后再次打开新增 1 条；
3. 管理员查看自己的 trace 不记该动作；
4. 他人 trace 抽屉出现只读审计横幅，自己的 trace 不出现；
5. 审计日志页面能按 `target_id` 查到“谁看过这个用户”。

---

## 4. 明确不做

| 项 | 原因 |
|---|---|
| `.ppt/.pptx` 解析 | 需要版式与备注抽取，另立需求 |
| OCR 扫描件、图片型 Excel | 当前无 OCR 能力 |
| Office 原样渲染、转 PDF、在线编辑 | 超出“入库转换 + 可读预览”范围，需要完整 Office/LibreOffice 渲染服务 |
| Excel 图表、图片、批注、颜色样式还原 | 预览只保证可读内容，不保证视觉还原 |
| 文档版本管理、文件夹、标签、文档级权限 | 本轮只做知识库管理基础体验 |
| 工作流写操作（改数据、发邮件、下单、删除文档） | 权限与审计成本高，保持只读工具 |
| 默认自动执行自然语言任务 | 误操作风险高，保留确认闸门 |
| 自然语言修改已生成计划（如“把第 2 步换成业务库”） | 本轮先做好“目标 → 计划”，计划修订列入后续 |
| 多智能体协作、跨会话长期记忆 | 超出当前 planner/executor 架构 |
| 上传断点续传、暂停/恢复单个上传 | 当前分块上传已支持失败清理；断点续传另立需求 |
| 用户真正物理删除运行日志（连管理员侧一并销毁） | 与“管理员可查全链路”冲突；如需要应作为带审批流的数据销毁功能另立需求 |
| 管理员修改/删除/代发用户数据、冒充用户身份 | 只做只读查看，写操作撤销风险高 |
| 审计日志的删除、清空、自动过期回收 | 审计需完整可追溯，保留策略另行评审 |
| 基于审计数据的告警、报表、异常行为分析 | 本轮只交付查询与导出，分析能力另立需求 |
| 跨用户检索（按关键字直接搜所有用户的提问原文） | 涉及隐私范围与索引成本，先按“先定位用户再查看”设计 |

---

## 5. 接口与数据变更汇总

### 5.1 接口

| 方法 | 路径 | 变更 | 阶段 |
|---|---|---|---|
| POST | `/api/docs/upload` | 白名单增加 `.xlsx/.xls/.xlsm/.csv/.doc` | V5-1 |
| POST | `/api/docs/upload/batch` | 复用同一白名单 | V5-1 |
| POST | `/api/docs/upload/complete` | 复用同一白名单 | V5-1 |
| GET | `/api/docs/list` | 新增 `start_date`、`end_date` | V5-1 |
| GET | `/api/docs/{doc_id}/download` | 新增，管理员下载原件 | V5-2 |
| GET | `/api/docs/{doc_id}/preview` | 新增，已登录用户预览 | V5-2 |
| POST | `/api/chat/stream` | 自动模式命中复合目标时返回现有 `workflow` 帧；不新增事件类型 | V5-3 |
| POST | `/api/workflow/plan` | 入参不变；计划 JSON 增加可选 `assumptions` | V5-3 |
| DELETE | `/api/me/io-logs` | 语义变更：物理删除改为软删除（`user_deleted_at`），返回 `{removed, mode:"soft"}`，写 `USER_LOG_DELETE` | V5-4 |
| GET | `/api/me/io-logs/export` | 只导出未软删除记录；写 `USER_LOG_EXPORT` | V5-4 |
| GET | `/api/admin/io-logs` | 新增 `include_deleted` / `only_deleted`，返回 `user_deleted`；导出写 `ADMIN_IO_EXPORT` | V5-4 |
| GET | `/api/admin/feedback` | 新增 `user_id` 筛选；导出写 `FEEDBACK_EXPORT` | V5-4 |
| GET | `/api/admin/audit-logs` | 新增，分页查询审计（user_id/action/target/时间/关键字） | V5-4 |
| GET | `/api/admin/audit-logs/actions` | 新增，动作枚举 + 中文名 | V5-4 |
| GET | `/api/admin/audit-logs/export` | 新增，CSV 导出上限 1 万行，写 `AUDIT_EXPORT` | V5-4 |
| GET | `/api/admin/users/{user_id}/overview` | 新增，用户概览（含 `qa_deleted`、`viewed_by_admin`），写 `ADMIN_VIEW_USER_DATA` | V5-4 |
| GET | `/api/admin/users/{user_id}/qa` | 新增，用户问答记录分页 | V5-4 |
| GET | `/api/admin/users/{user_id}/sessions` | 新增，用户会话分页 | V5-4 |
| GET | `/api/admin/users/{user_id}/sessions/{sid}/messages` | 新增，会话消息只读；越权返回 `40402` | V5-4 |
| GET | `/api/admin/users/{user_id}/documents` | 新增，用户文档分页 | V5-4 |
| GET | `/api/admin/users/{user_id}/feedback` | 新增，用户反馈分页 | V5-4 |
| GET | `/api/admin/users/{user_id}/activity` | 新增，问答日志 + 操作日志统一时间线 | V5-4 |

错误码：

- 沿用 `40002` 文件类型不支持、`40003` 文件超限、`40001` 参数错误、`40401` 文档不存在、`50003` 解析/入库失败。
- 新增 `40407` 原文件不存在（仅下载/预览使用）。
- V5-4 沿用 `40303` 无权限、`40402` 会话不存在、`40403` 用户不存在、`40001` 参数错误、`50003` 服务暂不可用，**未新增错误码**。
- 不改变已有错误码含义。

### 5.2 数据模型

| 表 | 变更 | 阶段 |
|---|---|---|
| `document` | 不新增字段；继续使用 `file_path` 定位原件 | V5-1/V5-2 |
| `document` | 可选：`idx_document_create_time`，仅在日期筛选压测需要时新增 | V5-1 |
| `workflow_task` | 不新增字段；`assumptions` 存在 `plan_json` 内 | V5-3 |
| `chat_io_log` | 新增 `user_deleted_at TIMESTAMP NULL`（幂等 `ADD COLUMN IF NOT EXISTS`） | V5-4 |
| `chat_io_log` | 新增索引 `idx_io_log_user_visible (user_id, user_deleted_at, created_at DESC)` | V5-4 |
| `operation_log` | 不新增列；新增索引 `idx_operation_log_target (target_type, target_id)` | V5-4 |
| `operation_log` | action 取值扩展 8 类（`USER_LOG_*`、`SESSION_DELETE*`、`ADMIN_*`、`AUDIT_EXPORT`、`FEEDBACK_EXPORT`） | V5-4 |

不新增表，不做不可回滚的列变更。

### 5.3 配置

新增建议项（是否全部登记配置中心见第 10 节）：

| 参数 | 默认 | 用途 | 阶段 |
|---|---:|---|---|
| `EXCEL_MAX_SHEETS` | 20 | 单文件最多解析工作表数 | V5-1 |
| `EXCEL_MAX_ROWS_PER_SHEET` | 5000 | 单表最多有效行数 | V5-1 |
| `EXCEL_MAX_COLS` | 200 | 单表最多列数 | V5-1 |
| `EXCEL_MAX_CELL_CHARS` | 200 | 单格文本上限 | V5-1 |
| `DOC_CONVERT_TIMEOUT` | 60 | `.doc` 转 `.docx` 超时秒数 | V5-1 |
| `DOC_PREVIEW_MAX_CHARS` | 200000 | 文本/JSON 预览字符上限 | V5-2 |
| `DOC_PREVIEW_MAX_ROWS` | 100 | Excel 每表预览行数 | V5-2 |
| `DOC_PREVIEW_MAX_SHEETS` | 10 | Excel 预览工作表数 | V5-2 |
| `ADMIN_VIEW_LOG_DEDUP_SECONDS` | 60 | 管理员查看他人数据的审计去重窗口 | V5-4 |
| `AUDIT_LOG_RETENTION_DAYS` | 730 | 审计日志保留期（仅容量评估参考，不自动删除） | V5-4 |
| `ADMIN_OVERVIEW_CACHE_SECONDS` | 0 | 用户概览缓存秒数（默认关闭，保证数据实时） | V5-4 |

若新增配置，必须同步更新 `.env` 与 `.env.example`，保持两边键集合一致；不能只写在一处。

---

## 6. 阶段与里程碑

| 阶段 | 内容 | 验收口径 |
|---|---|---|
| V5-1 知识库摄取与管理 | R1 多格式解析 + R2 上传队列 + R3 时间/关键字筛选 | Excel/CSV/DOC 样本入库与检索；上传队列 1440/375；筛选接口与 UI；PDF/DOCX/MD 回归 |
| V5-2 原文档访问 | R4 下载 + 预览 | Excel/CSV/DOCX/DOC/PDF/MD 预览；下载哈希一致；普通用户预览/下载权限分离；路径穿越拦截；40407；1440/375 |
| V5-3 自主任务规划 | R5 自然语言目标 → 自动计划 | 10 条路由用例 ≥9；计划校验 100%；确认后执行；简单问答不误触发 |
| V5-4 管理员审计与全链路查看 | R6 删除语义纠正 + R8 审计查询 + R7 用户全景 + R9 反审计 | 软删除与管理员可见性、7 个用户只读接口、审计查询/导出、60 秒去重、`pytest` 全绿、`npm run build` 通过；1440/375 |

每阶段交付：

1. 逐条验收结论（PASS/FAIL + 实测值）；
2. 关键截图（1440 / 375）；
3. 后端 `pytest`、前端 build、上一阶段接口回归；
4. 数据清理记录与基线差集；
5. 独立验收报告 MD，命名统一为“V5-1 主题验收报告”“V5-2 主题验收报告”“V5-3 主题验收报告”“V5-4 主题验收报告”；v6 版本依次使用 `V6-1`、`V6-2` 前缀，`present_files` 交付后再等确认。

阶段执行顺序说明：V5-4 因涉及对外口径错误，优先级提到 V5-2 之后先做，执行顺序为 **R6 → R8 → R7 → R9**（先纠正删除语义，再补审计读侧，再做用户全景，最后加反审计与只读约束）；V5-3 自主规划顺延至 V5-4 之后开发。

---

## 7. 验收与回归基线

| 项 | 当前基线 | v5 要求 |
|---|---|---|
| pytest | 304 passed / 2 skipped（V5-4 新增 10 例后） | 全绿，新增用例后总数增加 |
| 前端 build | EXIT 0（V5-4 后），仅既有 `ui-vendor` chunk 体积提示 | EXIT 0，无新增错误 |
| OpenAPI / 业务端点 | 按 V5-4 新增 15 个端点后更新断言 | 旧端点不缺失 |
| 配置中心 | 11 组 / 62 参数 + V5-4 三项新配置 | 若新增参数，按实际更新断言 |
| SSE 事件 | 现有类型不变 | 不新增、不破坏 |
| 鉴权 | 管理接口 `require_admin` | 下载 `require_admin`；预览 `get_current_user`；`/api/admin/users/*`、`/api/admin/audit-logs*` 全部 `require_admin` |
| 真实环境冒烟 | 真实 PG + HTTP 8011 | 软删除三态、管理员可见性、审计命中、7 个用户接口返回量与权限错误码 |
| 数据清理 | baseline 差集 | 禁止全表 DELETE |

新增专项测试建议：

- `backend/tests/test_docs_multiformat.py`：xlsx/xls/xlsm/csv/doc 解析、空表、加密、编码、截断、转换器缺失。
- `backend/tests/test_docs_filter_api.py`：日期边界、组合筛选、非法日期。
- `backend/tests/test_docs_preview.py`：下载哈希、预览结构、普通用户预览/管理员下载、路径穿越、40407。
- `backend/tests/test_workflow_autoplan.py`：10 条路由用例、计划校验、默认不执行。
- `backend/tests/test_admin_audit_api.py`：软删除与管理员可见性、`include_deleted/only_deleted`、审计查询与动作枚举、7 个用户全景接口、越权/不存在/非法日期错误码（离线 monkeypatch 风格，10 例）。
- `frontend` 手工/脚本 UI 验收：上传队列、筛选、预览弹窗，1440/375。

---

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Excel 超大表/异常宽表导致内存上涨 | 上传超时或进程不稳 | 行/列/工作表上限，超限截断并提示；解析放线程池 |
| `.xls` 依赖兼容性差 | 旧文件解析失败 | 固定 `xlrd>=2,<3`；失败提示解除密码/另存 xlsx |
| `.doc` 依赖 Word COM 或 LibreOffice | 服务器未装转换器时无法入库 | 启动时探测转换器；缺失时返回明确提示，不崩溃；测试按可用性跳过 |
| Word COM 残留进程/弹窗 | 服务器残留 WINWORD.EXE、请求卡死 | `Visible=False`、`DisplayAlerts=0`、`AutomationSecurity=3`、超时与 finally 清理 |
| CSV 编码/分隔符识别错误 | 乱码或串列 | 多编码回退 + `csv.Sniffer`；无法识别时明确报错，不静默乱码 |
| 合并单元格、公式缓存导致内容偏差 | 检索结果缺值 | 合并区域填充左上角值；公式缓存为空保留公式并标注 |
| 上传队列状态与后端结果不一致 | 用户重复上传/误判 | 单文件状态机；成功/失败以接口返回为准；失败重试只重跑单个文件 |
| 日期边界时区不一致 | 少一天/多一天 | 服务器本地日期，结束日 +1 天开区间；接口用例覆盖 23:59 |
| 预览 Markdown 触发 XSS | 安全问题 | 复用 `marked + DOMPurify`，禁止原始 HTML，URI 白名单 |
| 路径穿越读取任意文件 | 安全问题 | `doc_id` 查路径；resolve 后校验在 upload_dir 内；拒绝符号链接逃逸 |
| PDF 大文件预览占内存 | 浏览器卡顿 | `FileResponse` 流式返回，不在后端整文件读入内存 |
| 自动规划误触发，简单问题变任务 | 体验变差、成本上升 | 复合目标规则 + 置信度阈值 + 简单问答回归集 |
| 计划编造步骤或数据 | 错误执行 | 工具白名单、参数校验、危险动作拒绝、无数据时明确说明 |
| 默认自动执行导致误操作 | 安全风险 | `WORKFLOW_AUTO_RUN=false`，计划卡确认后才执行 |
| 用户删除后仍被管理员看到，被误解为“没删干净” | 信任风险 | 文案明确“从本人视角删除 + 管理员保留期内可查”；成功提示写清范围 |
| 软删除数据在保留期到期后被回收，事后无法回溯 | 审计断档 | 保留期取出并写入配置说明；确有长期留存需求的问答另存 `chat_record` |
| 审计表持续增长（永久保留） | 存储与查询变慢 | `idx_operation_log_target` + 分页 + 导出上限 1 万行；容量按 730 天估算，超阈值时再评估归档 |
| 管理员查看行为高频写入审计 | 日志噪音、写放大 | 60 秒窗口去重（`ADMIN_VIEW_LOG_DEDUP_SECONDS`）；只对跨用户读取记 `ADMIN_VIEW_USER_DATA` |
| 管理员权限集中，缺乏二次校验 | 内部风险 | 只读接口 + 强制留痕 + `viewed_by_admin` 回显；后续可加二次确认与审批流 |

---

## 9. 开发前检查清单

- [x] 需求决策已确认（2026-11-20）
- [x] 明确解析格式：`.xlsx/.xls/.xlsm/.csv/.doc`
- [x] 明确权限：下载仅管理员，预览所有已登录用户
- [x] 明确自动规划默认“计划 + 确认”，不自动执行
- [ ] 安装并探测 `openpyxl`、`xlrd`、Windows `pywin32`
- [ ] 准备 xlsx/xls/xlsm/csv/doc 测试样本
- [ ] 验证本机 `.doc` 转换器（Word COM 已验证，LibreOffice 未安装）
- [ ] 新增配置默认值并同步 `.env` / `.env.example`
- [ ] 确认可选索引是否纳入
- [ ] 确认测试样本与造数/清理方案
- [ ] 确认前端不引入新 UI 依赖
- [x] V5-4：确认删除口径为保留期软删除，管理员保留期内可查（2026-11-20）
- [x] V5-4：确认 `user_deleted_at` 幂等建列与两个新索引可回滚
- [x] V5-4：确认审计三项配置同步写入 `.env` 与 `.env.example`
- [x] V5-4：确认管理员接口全部 `require_admin`，错误码不新增
- [x] V5-4：确认真实库冒烟造数可清理（Test_UID 已 cleanup）
- [ ] V5-4：确认审计表长期增长应对（当前仅索引+分页+导出上限）

---

## 10. 已确认决策

| # | 决策点 | 结论 | 状态 |
|---:|---|---|---|
| 1 | 版本号 | 本版采用 **v5.0** | 采用 |
| 2 | 解析格式 | `.xlsx/.xls/.xlsm/.csv/.doc` | 已确认 |
| 3 | 解析上限 | 每表 5000 行、200 列、20 表；`.doc` 转换 60 秒超时；截断并提示 | 默认执行 |
| 4 | 预览边界 | PDF 原生；MD 渲染；DOCX/DOC 文本；Excel/CSV 表格；不做版式还原 | 已确认 |
| 5 | 自动规划 | 默认生成计划、确认后执行；`WORKFLOW_AUTO_RUN=false`；简单问答不误触发 | 已确认 |
| 6 | 计划修订 | “用自然语言修改已生成步骤”本轮不做，列入后续 | 已确认 |
| 7 | 新增参数 | 先进 `Settings` 与 `.env` / `.env.example`，是否进配置中心开发时再定 | 默认执行 |
| 8 | 下载/预览权限 | 下载仅管理员；预览所有已登录用户；普通用户从问答来源卡片进入 | 已确认 |
| 9 | 日期时区 | 服务器本地日期，结束日包含全天；开始日 > 结束日返回 `40001` | 默认执行 |
| 10 | 上传 UI 依赖 | 只用 Element Plus，不引入新 UI 库 | 默认执行 |
| 11 | 「删除我的运行日志」语义 | 改为方案 A：保留期软删除，用户侧不可见，管理员保留期内可查 | 已确认 |
| 12 | 会话删除时运行日志 | 一并软删除，不物理删除，避免链路断档 | 已确认 |
| 13 | 管理员可见窗口 | 随 `IO_LOG_RETENTION_DAYS`（当前 90 天） | 已确认 |
| 14 | 用户全景呈现方式 | 右侧抽屉（Drawer）6 Tab，不做独立页面 | 已确认 |
| 15 | 审计日志保留 | 永久保留，不自动清理 | 已确认 |
| 16 | 阶段顺序 | 本需求提前为 V5-4，V5-3 自主规划顺延 | 已确认 |

---

## 11. 结论

- v5 共 9 项需求，分 4 个阶段：**V5-1 摄取与管理、V5-2 原件访问、V5-4 管理员审计与全链路查看、V5-3 自主规划**。
- 首批先做 **R1 + R2 + R3**：多格式解析、上传队列、时间/关键字筛选（已验收）。
- 第二批做 **R4**：在原文档解析基础上补预览和下载，并把“普通用户可预览、下载仍限管理员”落到来源卡片（已验收）。
- 第三批做 **R6 + R8 + R7 + R9**：纠正“删除后管理员也查不到”的语义错误，补齐操作审计可查可导出，提供用户全景只读视图，并对管理员查看行为强制留痕（V5-4 已验收，`pytest 304 passed / 2 skipped`、前端 build 通过、真实 PG/HTTP 冒烟通过）。
- 第四批做 **R5**：复用现有 workflow planner 和 PlanCard，重点补“自动识别复合目标 + 只让用户描述目标 + 规划假设/失败原因”（V5-3 待开发）。
- **下一步进入 V5-3 开发。**
