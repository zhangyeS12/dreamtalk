# dreamtalk 工作交接

更新日期：2026-09-28。此文件记录当前开发现场与接续工作，不替代 [AGENTS.md](AGENTS.md)。先读 AGENTS，再读本文，最后核对实际 Git 状态和相关代码；不能把下面的基线哈希当作永远不变的当前 HEAD。

## 最新接续：2026-09-28 自动模型容量与请求预留

- 从 `36567bc` 接续，正式目录 `D:\LivingWorld` / `codex/chat-feedback`。用户同意把常见模型容量自动匹配、手动值移入高级设置、回复长度独立选择，并改善整份模型容量预留造成的聊天门槛。后续用户明确指出耗时过长、过度集中 DeepSeek；应收紧切片、优先成熟通用实现并如实说明每个提供商的完成范围，不能将自动识别容量等同于所有服务已支持按请求预留。
- 复用 models.dev/MIT 的 18 个模型与服务容量快照；React、桌面保存校验和 Core 读取同一 JSON。输入可信容量使用完整 context window，不能使用可能减去最大输出额度的 catalog input 字段。已匹配模型自动填容量；未知服务/模型需高级设置；相同模型 ID 的代理不继承直连预设。当前覆盖的是部分 OpenAI/Claude/Gemini/DeepSeek 型号，并非所有最新型号。
- 设置界面显示简短 2,048 / 标准 8,192 / 较长 16,384 / 自定义回复上限。新设置默认标准；旧自定义输入/输出保留，50,000 会显示为自定义，不自动改配置、额度或密钥。原数值限制扩为输入 10M / 输出 1M，已知模型保存时另校验真实 output cap。旧 managed 文档的识别不套新增 output 校验，因此旧过大值仍可进入编辑修正。配置序列化形状未改。
- DeepSeek 官方直接 endpoint 的四个已核对模型 ID 接入 MIT `deepseek-recipe` / `deepseek-recipe-encoding` Rust 0.1.0（Cargo checksum 固定；published source `b60af4cf40768602e6928772f01eba451483a442`）。官方完整 conversation framing 的 UTF-8 byte 长度是已审核文本 ByteLevel BPE 的保守上界，包含 role/BOS/thinking prefix；不声称精确 Token 数。重用官方 converter/renderer，没有独立写模板或字数比例估算。V4/V4.1 元数据核对来自官方仓库参考 `8cadfede7063c896b944e7bae05daa3549ae97ea`；官方 compare API 对发布提交返回 404，未据此声称两个提交完全相同。详见 [复用/上界依据](docs/research/2026-09-28-model-capacity-request-bounds.md)。
- 同一 `ProviderRequestUsageBounder` 注入 chat preflight、每个 routed physical attempt/retry/fallback 与 Budget Guard。当前只有已核对的 DeepSeek 直接文本调用使用逐请求上界；其他提供商、代理、structured/streaming/image、缺 helper、转换失败、超时等继续 full-model trusted fallback。额度硬约束、单次 claim、accounting START、未知 dispatch hold、禁止自动重放和知识过滤都保留。没有上下文自动压缩/截断、官方 count endpoint 或其他提供商逐请求计数适配；这是明确未完成项。
- Helper 只通过 stdin 获取无密钥请求 body，4 MiB / 5 秒边界；只输出数值或固定错误，Core 丢弃 stderr；最多缓存 64 个 SHA256 digest→数值，不缓存 prompt。打包脚本先编译 helper，PyInstaller 将其放入 `_internal/request-bound/`。随包附带 MIT notices、195 个锁定 Windows 依赖的版本/下载链接/registry checksum inventory 与 123 组许可证文本。许可证网络获取遇到超时/Windows revocation 离线，jsonschema exact revision license 成功取得，number_prefix 使用已获取官方 exact-revision MIT 原文；不把网络错误描述为项目功能错误。
- Ruff lint/format、ESLint/TypeScript、Git diff 静态检查通过；helper Rust release、Vite 197 模块/Rust desktop release 和 Core PyInstaller 构建成功。源与包内三个 Python 文件、JSON、helper 二进制 SHA256 一致。按照 AGENTS 未新增/修改/运行自动测试、smoke、GUI 验收、provider calls，未读取密钥、修改用户 DB、已保存配置或重放消息。既有 UI 测试仍描述旧必填字段/静默 disabled 行为，需用户后续授权维护；构建不能证明 API 回复验收通过。首次 spec lint 因非提升模式无法写 Ruff cache，改为只读 --no-cache 后通过。既有 PyInstaller optional imports 警告保留。
- 新包独立路径 `D:\LivingWorld\artifacts\portable\model-autoconfig\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\model-autoconfig\dreamtalk.zip`，42,570,087 bytes / SHA256 `61A46CFBBEB9BB8128146F9CF33F10CF18C3C1567E7206C034433532F4BB8EBC`。helper 4,700,160 bytes。默认/旧版本目录均未覆盖；没有启动应用或终止用户进程，没有 push/release。编译日志 `artifacts/model-autoconfig-desktop-build.log` / `artifacts/model-autoconfig-core-build.log`。
- 用户下一步：关闭旧窗口并使用上述新目录，保留已有 API；建议回复长度选“标准”。已保存聊天额度不变；原 200,000 可在已核对 DeepSeek 短上下文下按新上界准入，但不是任意长上下文/群聊/fallback 全轮的完成保证。发送一条新消息验收，历史 pending 不自动重放。
- 工程下一步：优先统一提供商的输入预检能力，调查/复用 OpenAI、Anthropic、Google 的官方计数接口或成熟库，分别核对保证语义，再接入同一 admission/ledger，不按每个模型复制模板。未知服务继续可手动配置；上下文管理估算与 HARD 授权上界必须区分。用户这轮质疑应影响后续范围控制，不能继续无限扩大单提供商实现。

## 前序切片：2026-09-28 聊天未开始的额度准入修复

- 从干净 `7170c0e` 接续；正式目录 `D:\LivingWorld` / `codex/chat-feedback`。用户两条“你是谁”已保存，检查状态为 pending。前序截图输入上界 1,000,000、输出 50,000、聊天额度 200,000；当前聊天源码在 claim/provider 前预留整份模型输入上界，因此该组合必定拒绝。没有把短消息估算当作可信硬界限。
- 发现 UI 的确定冲突：聊天额度输入、应用与持久值恢复均硬限制 <=1,000,000，但模型输入可配置 1,000,000，无法留至少 1 Token 回复空间。解除该 UI 限制至 JavaScript safe integer，保留 Core 既有 int64 ceiling 和整轮 hard budget；未自动提高用户额度或调整模型参数。按上述设置，1,000,001 是首次调用的最小门槛；1,050,000 可预留一次完整 50,000 输出，不保证群聊/fallback 全轮完成。
- 复用已有 registry/bounder/HTTP/feedback：可用性查询返回 route-wide 输入预留及输出上界，私聊和群聊在发送前给出具体额度提示。真正授权仍由原 gateway/bounder 执行；字段仅是 UI guidance。费用准入、可信上界不可得、整轮 Token 不足不再全部混成一个模糊的 422。
- 检查状态时保留当前会话已知失败说明；通用 pending 不再提示无条件反复发送。没有新增失败持久化或新 migration；重启后不猜历史失败原因。已有两轮消息及其 ceiling 不改写、不自动重放；改好全局额度后需发送新消息。
- 官方 DeepSeek recipe 0.1.1/MIT 与 Token 文档调查见 [本轮复用记录](docs/research/2026-09-28-chat-admission-reuse.md)。当前无 Windows wheel，逐请求编码的 hard guarantee 尚未证实，本轮未加入新依赖；更精确预留留待后续，不可声称 200,000 已能容纳 1,000,000 配置上界。
- 本轮没有修改用户数据库、读取 API 密钥、调用付费 API、重放消息或调整已保存配置。读取本机 ready/shutdown 日志未见 llm completion；磁盘配置/DB 视图曾落后于运行实例，不能用它断言用户 DB 损坏或配置未保存。Python Ruff lint/format、ESLint/TypeScript 与代码 `git diff --check` 通过；未新增、修改或运行自动测试、smoke、GUI 验收。
- 打包脚本两次在自动审批超时而未启动，改为新目录中的分步 PyInstaller + release 桌面编译；不覆盖旧包。Core 冻结与 Vite 195 模块 / Rust release 均完成；独立新版启动路径 `D:\LivingWorld\artifacts\portable\chat-admission-fix\dreamtalk\dreamtalk-desktop.exe`，完整 ZIP `D:\LivingWorld\artifacts\portable\chat-admission-fix\dreamtalk.zip`，40,648,147 bytes，SHA256 `383193D730D3ADC1491F01C2E86BF5F38DBDA6D0F5B49AE0B9A86A4C9C2855C5`。包内四个改动 Python 文件和原生 authoring 文件哈希均与源码一致。PyInstaller 既有 tzdata/pysqlite2/MySQLdb 缺少 hidden import 警告仍存在，未运行验收其影响。默认目录与 preview-constructor-fix 均保留旧包；必须打开本轮新路径。用户旧窗口已关闭，助手未终止其进程。
- 用户后续操作：使用本轮新版目录的 exe，在设置把聊天额度改为 1,050,000 并点击“应用”（前提仍为截图的输入/输出设置），然后发送一条新消息。实际回复由用户验收。下面原生预览修复与旧产物记录为历史；不要误拿旧 default/preview 包验收本轮变化。

## 前序切片：2026-09-28 修复原生草稿构造错误

- 用户使用上轮反馈版后，预览显示“未能连接核心”。从干净 `61ee710` 接续，正式目录仍为 `D:\LivingWorld` / `codex/chat-feedback`。没有远程、发布或 push。
- 找到确定的代码错误：`application/content_authoring.py::authored_graph` 末尾使用 `ContentDraft(contents, tuple(assets), tuple(raws))`，但 `application/content.py::ContentDraft` 是 `@dataclass(..., kw_only=True)`，只能使用命名参数。该调用会抛 TypeError，影响手动/生成创建与编辑角色卡、世界书，不是特定 AI 字段或用户模型配置导致。上轮改善反馈位置，却漏查了这个构造调用；本节补足并替代“预览根因尚未知”的结论。
- 新调用为 `ContentDraft(contents=contents, assets=tuple(assets), raw_imports=tuple(raws))`。静态 AST 核对生产代码全部六个 ContentDraft 构造点，均为零位置参数；其他现有导入/包服务本来使用命名参数。
- 当前 Core 在日志 12:30:13 UTC ready、凭据同步完成，仍在运行。原 TypeError 未由 authoring route 处理；检查已安装 Starlette middleware 顺序可见 ServerErrorMiddleware 位于用户 CORS middleware 外层，异常 500 返回路径绕过 CORS，浏览器可把它表现为 fetch 失败。前端此前把非 CoreRequestError 都称为连接失败。这里的浏览器原因是基于源码和界面推断，未捕获用户原始网络响应或执行浏览器验收。
- 复用现有 HTTPException/CORS 与 StructuredLogger：authoring preview 未预期异常返回固定 `editor_preview_failed` / 500，并写入固定 `content_editor / preview_failed` ERROR 事件；不回传异常文本、草稿、用户输入或模型数据。Core composition 传入已有 logger；前端明确显示核心处理预览的内部错误。已知字段/版本/生成依据错误保持原分类；Draft → Preview → 明确哈希确认 → Commit 和 CAS 未改变。
- 本轮没有读取/操作用户数据库、读取 API 凭据、重复生成或修改 API 设置。未新增、修改或执行自动测试、GUI/browser smoke、真实搜索/模型调用；同类构造调用检查为源代码 AST 分析。Python Ruff lint/format、ESLint/TypeScript 及 `git diff --check` 通过。
- 用户旧包仍运行，未由助手终止或替换其目录。本轮复用既有 PyInstaller + release 桌面构建与随包许可步骤，跳过所有 smoke；Core 冻结、Vite 195 模块、Rust release 完成，日志 `artifacts/preview-constructor-fix-build.log`。独立新版 ZIP `D:\LivingWorld\artifacts\portable\preview-constructor-fix\dreamtalk.zip`，40,645,038 bytes / 2026-09-28 12:37:05 UTC，SHA256 `F9E7671819D089B0A0FF96E1B0F09102CCEAD4F5D1896134A1A34D0F7B518814`。desktop exe 12,391,936 bytes / 12:37:01 UTC；Core exe 13,723,248 bytes / 12:36:34 UTC。包内三个改动 Python 源文件哈希均与本轮源码一致。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在，未验收其运行影响。启动新版 `artifacts/portable/preview-constructor-fix/dreamtalk/dreamtalk-desktop.exe`，需要整个目录；默认 `artifacts/portable/dreamtalk/` 保留上轮旧包，不可拿其启动验证此修复。
- 用户接续：关闭旧窗口，再启动上述独立目录的新 exe；进入新建角色卡，使用“检查生成结果”恢复艾莲已有回执，再预览并明确确认保存。实际 UI/保存效果仍由用户验收；不需要重做付费生成。之后处理用户具体反馈，聊天大输入的整轮预留门槛仍未解决。

## 前序切片：2026-09-28 预览与保存的可见反馈

- 用户确认改用正确模型 ID 后实际生成成功，随后反馈长草稿底部“预览并保存”点击无反应。从干净 `5b35137` 接续，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback`；没有远程、发布或 push。
- 核对点击 handler、API client、authoring router、authored graph、现有预览容量/哈希确认/CAS 保存。按钮本来已连接 POST preview；错误仅显示编辑器顶部，预览也在顶部展开，没有滚动定位，长生成依据会掩盖结果。现有前端还会因缺少必填字段静默禁用。日志在 11:55:10 UTC 记录 `chat_completed`，没有记录用户本次 preview 的具体 HTTP 状态，不能将某个接口错误臆断为已复现根因。
- 编辑器现在对预览/保存错误与预览标题执行原生 scrollIntoView + focus；预览显示“尚未保存”状态，确认/返回编辑动作放在内容上下两处。正在准备时在原按钮旁显示状态；名称或条目必填错误改为点击后明确说明。确认成功后父级保存通知自动定位。复用现有 React refs/effects、CoreClient 和 Preview/Commit，不增加表单库、持久机制或依赖。
- 预览错误区分连接失效、不存在/版本冲突、预览容量、生成依据暂不可用、字段校验及 HTTP 状态。router 把 BuilderError 明确映射为 `builder_result_unavailable`，避免与普通字段错误混淆。失败保留编辑器草稿；没有删除生成回执、重复调用模型、绕过来源/哈希确认或直接写运行世界事实。
- 用户应用在检查期间自行正常关闭（日志 12:17:32 UTC），未由助手终止。尝试只读核对 app-data 存储时，运行期间的可见数据库/WAL 组合无法读取；停止后可见基库仍为 0014 且没有 builder 表，与本次成功生成和源码 0023 不对应。未用该可见副本判断用户存档已损坏，未修复/迁移/删除真实数据库；未取得此次预览失败的存储层证据。应以用户后续具体界面状态、正确运行环境日志为准。
- 本轮 ESLint/TypeScript、改动 Python Ruff lint/format 和 `git diff --check` 通过。未新增、修改或执行测试，未启动应用、执行浏览器/桌面 smoke、搜索或模型调用。既有 ContentEditor 测试含“必填缺失按钮 disabled”的旧预期，保留至用户授权测试维护。
- build-only Core 冻结、Vite 195 模块与 Rust release 完成，日志 `artifacts/preview-save-feedback-build.log`。最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,644,878 bytes / 2026-09-28 12:24:41 UTC，SHA256 `32C6383B6ED20F55C6F682752736689B8C6B709026E52FB78996BB4BCDA9FEBB`。desktop exe 12,391,936 bytes / 12:24:36 UTC；Core exe 13,723,086 bytes / 12:24:08 UTC。包内 router 源文件哈希与本轮源码一致。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在，未验收其运行影响。整个目录交付，下方产物为历史版本，构建不等于实际预览/保存成功。
- 用户接续：启动新版本，新建相应类型编辑器后点击“检查生成结果”恢复持久回执，再“预览并保存” → “确认加入当前世界”；不需要重新付费生成。若预览仍被拒绝，新版会定位并显示明确错误，不能宣称未取得的本次接口根因已全部解决。之后继续处理具体反馈，聊天整轮大输入预留门槛仍未解决。

## 前序切片：2026-09-28 资料生成与聊天额度分离

- 用户反馈 150,000/200,000 仍无法生成艾莲角色卡，并明确要求解决为什么资料生成关联聊天每轮额度。从干净 `c1e9730` 接续，正式目录仍为 `D:\LivingWorld`，沿用 `codex/chat-feedback`；没有远程，没有发布或 push。
- 原链路把聊天 ceiling 传入 Builder，再减整个可信模型输入上界；当输入上界较大时，用户提高聊天额度也无法留下输出预算。截图 150,000/200,000 的状态差异来自输入值还没有应用，但这不是预留逻辑的解决方案。
- 删除 ProductApp → WorldImports → ContentEditor → API client 的资料生成聊天额度参数。HTTP 旧 `token_ceiling` 可选/deprecated，兼容旧请求和单次 claim fingerprint，仅影响 receipt identity，不传入生成预算。新客户端只发送 kind/query 与 request ID，恢复/GET 和防重复调用不变。
- 生成请求单次输出 cap 仍为模型限制与 8,192 的较小值；现有 hard bounder 为所有路由候选预留，独立任务容量为最大候选 input+output。继续复用现有 ChatTurnTokenBudget 算术和 governed gateway，retry/fallback 共用一个有限任务 budget；逐调用可信上界、账本/金额 guard、未知结果不重放和 Draft/Preview/Commit 均保留。没有将本地分词估值假定为可信计费上界，也没有真的向模型输入百万 Token。
- 界面明确资料生成独立于聊天，不要求用户提高聊天额度。聊天区显示已应用值与未应用提示。旧失败回执改为明确提示点击“联网生成”开始新请求，“检查生成结果”只读旧请求，不自动付费重试。
- 实现前核对 DeepSeek 官方输出限制协议、tiktoken 官方示例和 LiteLLM token_counter 能力；选择直接复用既有预算/账本，不增加依赖。具体证据、推断和排除方案见[复用决定](docs/research/2026-09-28-generation-budget-reuse.md)。更新原 Builder 复用记录和 PRODUCT_SPEC，同时修正模型设置默认折叠的旧文档。
- 本轮 Python Ruff lint/format、ESLint/TypeScript 和 `git diff --check` 通过；Core/Vite 195 模块/Rust release build-only 成功，日志 `artifacts/independent-generation-budget-build.log`。没有新增/修改/执行测试、browser/desktop smoke、读取用户凭据或调用提供商/搜索。旧 Builder quota 行为与 ModelSetup disabled 行为测试预期待用户授权后同步；没有删除或弱化测试。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,643,073 bytes / 2026-09-28 11:23:35 UTC，SHA256 `1AC7E4D0B58AA87F670704163C897D82C398ED7E04BD917CB99BE6A80819B0DE`。desktop exe 12,391,424 bytes / 11:23:31 UTC；Core exe 13,723,061 bytes / 11:23:05 UTC。整个目录交付，启动入口 `artifacts/portable/dreamtalk/dreamtalk-desktop.exe`。
- 接下来用户启动新版，用新的“联网生成”请求验收实际搜索、API 响应及草稿质量；读取旧失败请求仍返回旧结果。此次资料生成修复不等于聊天自身的大上下文 Token 预留门槛已经解决；该问题仍保留后续。下方上轮关联每轮 ceiling 的描述以本节和实际代码为准。

## 前序切片：2026-09-28 模型保存按钮反馈修复

- 用户反馈“保存模型设置”点击无反应，截图中模型名称为 `deep seek`。从干净 `75108ac` 接续，正式目录仍为 `D:\LivingWorld`，分支 `codex/chat-feedback`；没有远程，没有发布或 push。
- 实际原因是名称含空格未通过已有 frontend/Rust 校验，旧按钮因 `disabled={!valid || saving}` 被静默禁用。截图上方的 Token 额度警告是独立聊天 preflight 限制，本身不阻止保存；没有证据表明这次点击已经发起保存或提供商调用。
- 保存按钮现在只在保存过程中禁用。点击后在表单及具体字段给出有界中文校验反馈，`aria-invalid`/`aria-describedby` 标注对应输入，并将焦点放到第一项错误；不合格字段不会调用 Rust IPC。校验覆盖模型名空白/控制字符/128 UTF-8 字节、密钥必填/4096 字节、完整服务地址和两个整数 Token 上限。服务地址与既有 host 规则对齐：HTTPS 或本机 HTTP，无 userinfo/query/fragment/空白/反斜线。
- 必填输入/输出 Token 上限直接显示，移除高级折叠。说明区分官方可信输入上界与本应用允许的输出 cap，未知值不猜；额度提示明确“模型设置仍可保存”。沿用 React/原生 HTML 表单和现有保存/安全凭据/回滚流程，没有增加表单库、模型预设或自动查询密钥的流程。
- 另核对 [DeepSeek 官方模型文档](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)（2026-09-28）：当前列出的模型 ID 为 `deepseek-flash` 与 `deepseek-v4-pro`，服务地址为 `https://api.deepseek.com`。仅作为用户填写指导，不静默替换模型，也不沿用过期名称或按品牌名猜 API ID。
- 本轮 `npm run lint`（ESLint/TypeScript）和 `git diff --check` 通过；`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功生成 Core/Vite/Rust release，日志 `artifacts/model-setup-feedback-build.log`。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在。未新增/修改/执行测试、浏览器/桌面 smoke 或提供商调用，没有读写用户真实模型配置/凭据。既有 ModelSetup 测试的“invalid 按钮 disabled”断言与新交互不同，按用户测试责任保留，需之后授权再维护。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,642,550 bytes / 2026-09-28 10:52:16 UTC，SHA256 `B057B11B11A6E1F89B30AAE54137BD366DF3B48E05074A5D23DC77C2D7938C9E`。desktop exe 12,391,424 bytes / 10:52:12 UTC；Core exe 13,723,075 bytes / 10:51:46 UTC。整个目录交付，旧截图中的折叠区/禁用行为由本节替代；桌面实际保存/重启与聊天仍由用户验收。
- 接下来优先处理可信输入上界与每轮额度的体验门槛。当前规则始终保留整个模型最大计费输入上界，即使短提示也可能超出 50,000 默认额度；输入上限与每轮上限均最多 1,000,000，因此可信输入上界为 1,000,000 的模型无法预留至少一个输出 Token。官方当前 DeepSeek 文档的上下文为 1M；不能只指导用户提高到 1,000,000 或虚填更小上界来声称解决。此次窄范围修复不调整预算/请求边界；应先调查可信逐请求计数/上界与服务端可执行限制的成熟实现，再提出保持整轮硬上限、重试/账本一致性的具体方案。

## 前序切片：2026-09-28 修复核心连接失败

- 用户反馈新版启动显示“核心连接失败”。从干净 `ed5f260` 接续，正式目录仍为 `D:\LivingWorld`，分支 `codex/chat-feedback`；没有远程，没有发布或 push。
- 两次真实失败日志均记录 `migration / alembic_schema_shape_mismatch`。只读检查实际用户数据库游标为 `0014_episodic_memory`；在一次性副本执行同一升级入口后定位为 `content_builder_jobs.created_at`：0023 迁移建成 `TEXT`，但 `UTCTimestampStorage`/ORM 及严格结构校验要求 `VARCHAR(32)`。错误发生在升级后的校验，事务回滚；不是 API 连通性或凭据问题。
- 修正 0023 新表时间列为 `sa.String(32)`，与现有存储类型一致；没有跳过校验、删库、重置存档或改变 API 配置。失败版本没有成功提交 0023，此次修复现有新增迁移即可，无需操作真实库或新建破坏性修复迁移。
- 下方上轮“0023 迁移兼容”描述需要补充：当时仅编译打包，没有执行迁移，实际新表类型不一致导致核心无法启动。上轮构建成功不能作为迁移运行成功的证据；本节取代旧产物信息。
- 本轮按用户故障诊断请求做了有界检查：存档一次性副本从 0014 升级到 0023，严格结构校验通过；修复后冻结 Core 使用另一份隔离副本和空模型配置启动，本地认证 `/system/health` 返回 200 / ready=true，`/system/shutdown` 返回 200，Core 退出码 0，副本最终游标 0023。真实数据库前后 SHA256 一致，临时副本已清理；没有读取真实凭据、调用提供商、执行 DDGS 搜索、自动测试套件或桌面/浏览器验收。
- 初次诊断辅助脚本的 SQLite 连接未及时关闭导致临时目录清理报文件占用；已修正辅助连接关闭并清理旧临时目录，随后有界启动诊断及清理正常完成。该辅助脚本位于聊天工作目录，未进入正式业务源码或测试。
- 改动迁移的 Ruff lint/format 和 `git diff --check` 通过。便携包通过 `uv run --frozen --group packaging python scripts/build-portable.py --build-only` 重新生成，Core/Vite/Rust release 构建成功；日志 `artifacts/core-startup-fix-build.log`。既有 PyInstaller 可选模块警告仍存在，隔离 Core 启动已通过，本轮没有验收聊天/生成效果。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,642,257 bytes / 2026-09-28 10:25:43 UTC，SHA256 `F87CF89CC24A91C70EF8AC820D4305A6B64F8D572806E309B5F4C4793B4DD4F8`。desktop exe 12,390,400 bytes / 10:25:39 UTC；Core exe 13,723,075 bytes / 10:25:12 UTC。直接运行 `artifacts/portable/dreamtalk/dreamtalk-desktop.exe`，或重新解压整个最新 ZIP，保留 Core 子目录；现有 app-data 会由程序正常升级。
- 接下来由用户重新打开新版，继续角色卡/世界书编辑与联网生成体验。实际桌面启动与提供商功能验收仍由用户完成；无需重新填写 API，也不需要删除现有数据库。若仍报错，优先检查新日志时间与是否启动了旧解压包。

## 前序切片：2026-09-28 内容编辑与联网生成

- 用户要求在界面新建/编辑角色卡和世界书，并输入自然语言后调用 API 联网辅助填写。本轮从干净 `d55d31f` 接续，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback`；未配置远程，没有发布或 push。
- 实现前调查 SillyTavern 1.19.0 的公开表单/条目规则、DDGS 9.16.0 与独立 Character Card Generator。选择直接复用 MIT DDGS；沿用既有 Pydantic、模型配置/凭据、governed routing/账本/硬 Token 上限和 ContentDraft/Preview/Commit。未复制 AGPL 酒馆源码，也未增加另一套模型或 agent runtime。具体版本、blob、许可证和决定见[本轮复用记录](docs/research/2026-09-28-content-builder-reuse.md)。
- 设置增加“角色卡与世界书 → 新建角色卡 / 新建世界书”，已有条目有“编辑 / 从文件更新”，原文件导入折叠在“从文件导入”。角色支持名称、描述、性格、背景、情境、说话方式、开场白、示例、标签与备注；世界书支持增删条目、主/次关键词、四种次级逻辑、常驻、启用及排序。手动填写不要求 API。
- 原生草稿直接构造 canonical graph，不伪造文件导入；更新保留兼容扩展、未开放条件、素材和角色内嵌世界书。独立内容身份从初始 revision 开始，既有快照保留；当前编辑器支持单角色卡/单世界书，字段总量最多 256 KiB、最多 128 条，特殊/过大原文件仍可导入。
- 联网只发送用户显式填写的需求，不读取其他世界或隐藏剧情。DDGS 固定 bing/brave/duckduckgo、单引擎 8 秒超时，最多八条去重检索摘要、每条最多 1,000 字符。没有自动请求结果页面。现有模型在一个 content_builder 请求里填入草稿、claims、冲突与待核对项；单次输出最多模型限制与 8,192 Token，物理 retry/fallback 共享用户设置的整轮硬上限。
- 程序验证结构、kind、长度和来源编号；出处支持/冲突判断由模型提出，不能当作全文事实核验。缺少字段依据显示待核对，情境/开场白/示例标记创作建议。源摘要、链接、检索时间和原始生成稿进入 authored preview；用户编辑后明确提示依据对应原始稿。
- 新增独立 `0023_content_builder_jobs` 迁移，兼容校验保留 0022 历史形状。World/request ID/fingerprint 有原子单次 claim，ready/failed 回执持久化。同一 ID 不再次 dispatch；重启遗留请求报告 interrupted，不自动重放。界面保留最近 request ID，“检查生成结果”只 GET；可结束等待继续手动填写。新生成是新的模型调用。
- 保存仍需要确切哈希确认与 replacement CAS，不创建 WorldTruth/Observation/Belief/Knowledge/Memory。角色首次打开聊天才实例化；世界书仍默认隐藏，保存/更新后逐条确认公共背景。
- 本轮静态检查：全 Core Python 源码和构建脚本 Ruff lint 通过，新模块 format check 通过；spec 仅排除 PyInstaller 执行全局名 F821；ESLint/TypeScript、`git diff --check` 通过。没有新增、修改或执行测试，没有启动应用、调用提供商或执行真实 DDGS 搜索验收。旧测试的硬编码 schema head 等预期留待用户授权维护。
- 最终 `uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功，冻结 Core、Vite 195 模块及 Rust release 均完成。构建日志 `artifacts/content-builder-build.log`。Analysis 和包文件包含新 authoring/builder/research 模块、0023 迁移、DDGS 动态搜索引擎、primp.pyd、lxml etree/objectify；MIT/BSD 上游 notices 和 primp SBOM 随包分发。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,643,420 bytes / 2026-09-28 10:01:39 UTC；SHA256 `758CEED6E3206AAEAD730AA3F97E0DBDB4431EF888FE801B014A0F44FCC552B3`。desktop exe 12,390,400 bytes / 2026-09-28 10:01:36 UTC；Core exe 13,723,081 bytes / 2026-09-28 10:01:08 UTC。整个目录供用户验收，编译/打包不能证明真实联网/资料质量/隔离或迁移运行验收已通过。
- 构建仍有 jieba 三处 regex SyntaxWarning，以及 tzdata/pysqlite2/MySQLdb hidden-import 警告。当前 179 个 missing-module、2 个 excluded-module 分析项，没有以 livingworld/ddgs/primp/lxml 命名的缺失模块项；新增部分为 lxml 可选/旧兼容分支。跨盘 uv hardlink→copy 和 Git 行尾提示仍存在。原始模块警告在 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，未进行运行验收其影响。
- 接下来由用户按新版入口验收：手动创建/编辑、艾莲角色卡生成、世界书条目生成、预览确认、公开范围与聊天使用、生成结果恢复；优先处理真实反馈。联网依据目前为摘要；未实现头像生成、网页全文核验、来源持续更新或创建完整运行 World 的 Builder。聊天流式输出继续是后续任务。
- 下方较早聊天召回及其他记录保留为历史切片，旧产物信息和“仅导入/Builder 未实现”的表述以本节及实际代码为准。

## 前序切片：2026-09-28 较早聊天原文召回

- 接续起点 `903cf10`，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback`；开始时工作区干净。
- 实现前调查 SQLite FTS5、jieba、Mem0 Python 和 BM25S；选择已有 SQLite FTS5 + 固定 jieba 0.42.1。具体来源、依赖代价和排除方案见[复用记录](docs/research/2026-09-28-chat-recall-reuse.md)。jieba 字典、finalseg 资源和 MIT 许可证纳入冻结/便携包。
- 新增应用层 EarlierChatRecall 和基础设施 Fts5ChatRecallRanker，生产私聊/群聊角色回复已接线。先确认当前角色有权看到当前会话，再用已有 World/Player/Conversation SQL 分页读取更早记录；只在授权候选的临时内存索引上用 BM25 排序。
- 当前玩家文本末尾最多 1,024 字符、24 个分词；最多扫描三页/300 条、512 KiB 原文；最多召回四条、8 KiB 原文及其消息/发送者身份类型与当前显示名/位置/时间出处。角色已有最近上下文的 turn 不重复召回。原文作为 lower-trust 数据，不写入 WorldTruth/Observation/Knowledge/EpisodicMemory。
- 没有额外模型调用、embedding、迁移或持久检索索引；群选人器和公共世界书激活窗口不变，既有 Token 硬上限仍检查最终提示词。本轮不是完整语义检索或自动长期记忆形成。
- 本轮静态检查：改动 Python 源码、构建脚本及 jieba hook 的 Ruff lint/format 通过，`git diff --check` 通过；spec 仅对 PyInstaller 提供的执行全局名排除 F821，实际 spec 编译/打包成功。没有新增、修改或运行测试，没有启动应用或调用提供商。此前世界书测试的历史预期仍待用户授权后维护。
- 本轮 `uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功：冻结 Core、Vite 194 模块和 Rust release 编译完成。清单包含两个新检索模块及 HMM Python 模块；包内只包含 jieba 的 dict.txt/finalseg 数据，没有 lac_small/Paddle 数据。词典 5,071,852 bytes，附完整 MIT 许可证且其随包副本哈希与源文件一致。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，30,493,996 bytes，2026-09-28 08:31:53 UTC，SHA256 `EA5A3511905B177D358C8E450A397F9CC5783E08159DB2064AEAC76CF039C9D7`。desktop exe 12,386,816 bytes / 2026-09-28 08:31:50 UTC；Core exe 13,325,902 bytes / 2026-09-28 08:31:24 UTC。整个解压目录供用户验收，构建不能替代长对话效果/延迟/隔离验收。
- 构建警告：新增 jieba 三处正则转义 SyntaxWarning（Python 3.13）；原有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在。Analysis 记录 166 个 missing-module、2 个 excluded-module 项，无以 livingworld 命名的缺失项。jieba 的可选 pkg_resources 在源码中有 ImportError 文件读取 fallback；本切片明确排除未使用的 lac_small/Paddle。原始记录 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，未运行验收其影响。依赖安装还有跨盘 hardlink→copy 性能提示，Git 有 LF→CRLF 提示，均已记录。
- 下一步先调查并接通现有 provider stream 到聊天界面的可靠呈现，解决 terminal 校验、一次性 claim 和账本一致性；同时优先处理用户验收反馈。召回的同义表达/更远历史及自动记忆形成分别保留后续任务，不把当前词法结果宣称为完整长期记忆。
- 下方世界书基础激活和聊天反馈保留为历史切片；产物以本节完成后的最新记录为准。

## 前序切片：2026-09-28 世界书基础激活

- 接续起点为 `f5dce91`，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback` 分支。开始时工作区干净；没有创建新的旧工作克隆。
- 已完成成熟方案调查：SillyTavern 1.19.0 的公开基础规则、Character Foundry 0.5.0 的格式能力；后者没有运行时激活器。本轮复用现有权限读取、规范化字段与聊天上下文，未新增依赖、模型调用、持久字段或数据库迁移。见[复用记录](docs/research/2026-09-28-lore-activation-reuse.md)。
- 公共世界书从“命中优先、未命中可填充”改为基础条件激活：常驻、主关键词、四种次级逻辑、大小写、完整单词及有界会话历史扫描。公开是访问权限，不等于本轮必定注入。私聊和群聊共享同一规则；群内前面的已保存台词可触发后面的角色背景。
- 来源扫描深度通过同一 accepted 快照的 LoreCollection 读取，默认两条，最多 32 条/16,384 个原始字符。仍限制 16 条背景及 12 KiB，保留 lower-trust 数据和世界隔离。
- 未支持的正则/模板、概率、时序、互斥组、角色筛选等条件不会被忽略后照常注入；条目详情显示具体支持范围/暂不参与原因和次级关键词。向量、完整递归、源插入位置及隐藏角色专属授权未接入。
- 现有测试的“公共条目无条件进入提示词”预期需要在用户授权测试维护后同步；本轮没有改动或运行测试，不以旧测试证明新激活规则。构建与静态检查结果在本节补充。
- 本轮静态检查：改动 Python 文件 Ruff lint 通过，新增激活模块/持久读取格式检查通过；`npm run lint`（ESLint + TypeScript）及 `git diff --check` 通过。没有新增、修改或运行测试，没有启动应用或调用提供商。
- 本轮交付：`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功，冻结 Core、Vite 生产构建与 Rust release 均完成；PyInstaller Analysis 清单含 `livingworld.application.lore_activation`。最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，27824584 bytes，2026-09-28 07:27:52 UTC，SHA256 `E5E264F85AB4A73359DCBCBCC09784D3E7429A4B2B6224C425978EDD8C9258A2`。整个解压目录供用户验收，构建不能替代运行效果确认。
- 构建仍有 `tzdata`、`pysqlite2`、`MySQLdb` hidden-import 警告及 162 项平台/可选库/静态符号等 missing-module 分析项；无以 `livingworld` 命名的缺失模块项。原始记录 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，本轮未验证其运行影响。
- 下方聊天状态反馈及其他旧记录是历史切片；旧产物哈希以本节后续记录为准。

## 前序切片：2026-09-28 聊天状态反馈

- 用户已授权自行选择技术方案并继续开发；每个新功能实现前先调查成熟项目，记录具体复用决定。规则已写入 AGENTS.md。
- 正式工作目录为 `D:\LivingWorld`，本地分支 `codex/chat-feedback`；不再使用旧工作克隆。开始接续时仍须核对实际 Git 状态。
- API client 接通现有 FastAPI `detail` 的有界机器标签；私聊/群聊区分保存、等待回复和检查状态，提供中文的模型、预算、校验、生成、账本异常提示。
- “检查回复状态”读取当前会话最近玩家消息的已有 GET，重新打开会话后仍可操作；不重放模型。群聊生成等待期间串行读取有界消息页，每次读取结束后间隔两秒，让已经保存的发言陆续出现；连续两次读取失败后暂停，手动刷新可恢复；离开会话或请求结束后停止读取。
- 尚未接通 Token 流式输出，尚未持久记录群轮停止原因；`completed` 只表示本轮终结，不能推断是自然停止。未增加依赖、数据库迁移或测试；未运行运行时/提供商验收。
- 本轮验证：`npm run lint`（ESLint + TypeScript）和 `git diff --check` 通过；`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功生成前端、Rust 发布版与冻结 Core。没有运行测试、便携包 smoke 或提供商调用；实际效果由用户带自己的 API 验收。
- 最新便携包：`D:\LivingWorld\artifacts\portable\dreamtalk.zip`，27,814,276 bytes，2026-09-28 06:55:33 UTC；SHA256 `59B1076CDBFF2D6AEEA0AAF020E464B1604E3BDF4094D16A08A34002F3C103E3`。解压后运行 `dreamtalk\dreamtalk-desktop.exe`。此产物信息覆盖下方历史产物哈希。
- PyInstaller 分析仍产生平台分支、可选依赖及属性符号等 missing-module 警告，未出现以 `livingworld` 命名的缺失模块项。原始记录：`artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`。构建成功不能替代运行验收，不宣称运行无警告。
- 复用调查和边界见 [本轮决定](docs/research/2026-09-28-chat-feedback-reuse.md)。下方“本轮仅文档交接”及基线描述保留为上次交接的历史记录，以此最新接续和实际代码为准。

## 1. 当前目标与上下文

用户要求先把核心聊天体验、导入、世界隔离和设置的真实效果完善到可亲自验收，然后会带自己的 API、角色卡、世界书试用。项目还没有最终验收，不应宣布完工。当前优先级是可用的沉浸聊天，而不是继续堆架构或准备 GitHub 发布。

最近讨论集中在两点：

- 世界书如何真正参与聊天，同时排除默认隐藏的暗线；群聊中所有参与角色应能参考已经发出的消息。
- 不重复造轮子。已取消“必须独立实现”的限制，允许评估成熟项目/组件；现有适配器没有因此被删除，也没有引入 SillyTavern 运行依赖。

本轮是**文档交接任务**，只更新 AGENTS.md 并创建 HANDOFF.md，没有修改业务代码。完成后新对话应继续产品开发，不再向用户索取已明确的四标签布局、群聊 Token 规则或世界隔离要求。

## 2. 仓库与代码基线

本轮写入前已实际检查两处 Git 仓库，它们均为 `master`，工作树和暂存区干净，HEAD 一致：

```text
1e7843cd71f557a0db2b5a4ecfa01bb9ccaaf17d
feat: prioritize relevant public lore in chat context
```

这是本次交接的**业务代码基线**；本轮后续文档提交不改变业务实现。

| 位置 | 本轮实际用途 |
| --- | --- |
| `D:\LivingWorld` | 用户的正式交付仓库；本轮检查时没有配置 Git remote，未连接 GitHub。 |
| `C:\Users\zhang\.codex\visualizations\2026\09\15\01a0a4e1-d243-7fc2-86dc-5a29a37df3ce\livingworld-work` | 本次受限环境允许写入的工作克隆；`origin` 指向 `D:\LivingWorld`。不是云端仓库。 |

若新对话可直接写 D 盘，优先在那里工作。若权限仍限制 D 盘写入，沿用工作克隆，先核对两边状态/哈希，在工作克隆提交后通过明确路径的 `git pull --ff-only` 同步 D 盘；不要覆盖 D 盘的新修改、强推或重写历史。构建产物属于 ignored 文件，Git 同步不会自动复制它们。

开始接续时执行：

```powershell
Set-Location D:\LivingWorld
git status --short
git log --oneline -8
git diff --stat
git diff --cached --stat
```

检查是否有另一任务正在修改相同文件，不把用户/其他任务的修改混入自己的提交。不要根据本文件推测活动进程已经退出；本轮没有启动或关闭应用。

## 3. 已完成到什么程度

以下“已实现”依据本轮源码读取，**不等于本轮实际运行或用户验收通过**。

| 能力 | 实际实现与当前界限 |
| --- | --- |
| 运行底座 | React/TypeScript/Vite、Tauri v2 Windows 壳、Python/FastAPI Core、随机 loopback 端口、认证发现与启停、SQLite/Alembic、日志、既有 CI 均存在。 |
| 普通界面 | PC 宽度的中文聊天 / 通讯录 / 设置 / 我；创建切换世界、暂停恢复、倍率、可用/忙碌、个人资料、当前世界导入和已知事件入口已接入 API。 |
| 身份与内容 | 每世界绑定本地 Player；默认从“家”进入；角色卡/世界书预览确认与独立更新；当前世界通讯录；首次打开聊天才创建/复用运行时 Character。 |
| 私聊 | 持久 Conversation、Player Message、turn、一次性 dispatch claim、角色生成与受控持久回复；页面发送、读取和错误提示已接线。 |
| 群聊 | 选择两个或以上角色建群；固定成员、共享持久记录、独立选人器、`@` 首位指定、逐条角色回复、整轮共享 Token 上限、完成标记。不是永久自主角色聊天。 |
| 聊天阅读 | `react-markdown` 安全渲染、回车发送/Shift+回车换行及输入法保护、自动滚动/历史位置处理、最近消息分页和“加载更早消息”。 |
| 世界书背景 | 世界书条目默认隐藏；当前世界逐条设为公共后，还须满足常驻或支持的关键词条件才进入聊天。已有次级条件及有界历史扫描，未实现完整酒馆激活。详见最新接续及第 5 节。 |
| 群聊知情 | 群成员即使没发言，也能在之后的私聊/其他群聊上下文读取自身参与群的有界消息窗口。不是自动 Knowledge/Truth/Memory 写入。 |
| 角色记忆 | C-007A 的 owner-scoped、Observation 证据支持的 EpisodicMemory 已存在，私聊/群聊回复读取本角色的有界记忆；另有当前会话的有界较早原文词法召回；尚未实现 EpisodicMemory 长期整理、语义检索或自动聊天记忆形成。 |
| LLM 底座 | OpenAI-compatible Chat、OpenAI Responses、Anthropic Messages、Gemini Interactions 四种 adapter；非流式/流式基础契约、structured validation、retry、routing、usage/pricing、financial budget、session credentials 已有。 |
| 内容兼容 | Character Card V2/V3、PNG/JSON 读取，Lorebook 标准化，原始兼容数据保留，外部 JSON 导出和 `.lwcontent` authored-content package 已有。并非完整酒馆兼容。 |
| 世界运行底座 | 确定性命令、行动、Scene、事件、Observation、tickless scheduler、sparse activation、clock reconciliation/catch-up、账本/回放和 CAS 已有；正式行动 registry 目前只有 `move_player` v1。 |
| 开发者工具 | `?developer=1` 可选择 Inspector 页面；相关 Core 开发 API 仍需显式 developer mode。它不是普通界面或自动 Activation consumer。 |
| 本地交付 | 已有随附冻结 Python Core 的 Windows 便携目录与 ZIP；无需使用者安装开发语言。没有签名安装包、自动更新或 GitHub 发布。 |

**明确未完成：** 完整自主 Character Agent、Director 批量计划/Event Reservoir 的生产执行与主动剧情、Activation consumer、自动知识传播、长期记忆整理/语义检索、完整 AI World Builder（当前角色卡/世界书摘要生成已实现）、Checkpoint/Timeline Branch 产品能力、`.lworld` 运行世界包、cloud sync/marketplace、完整模型管理、普通聊天页的流式输出，以及完整酒馆世界书激活行为。不要因为 docs 说 Stage 2–5 已冻结，就推断这些产品功能也已完成。

## 4. 本轮与紧邻前序工作的文件变化

### 本轮只改两份文档

| 文件 | 修改 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 同步最新优先级、自主推进/局部跳过、用户负责测试、三段式汇报、成熟组件复用、PC 聊天规则及验收前不发布；删除旧的“一切不确定立即停”与强制逐任务停止/自动测试冲突规则。 |
| [HANDOFF.md](HANDOFF.md) | 当前现场、入口、限制、近期改动、构建证据、继续顺序与易误解处。 |

没有业务、数据库迁移、测试或构建脚本变更。本轮没有重建便携版。

### 前序已提交的最近切片

下面来自实际 `git show`，不是本轮未提交工作：

| 提交 | 文件与用途 |
| --- | --- |
| `1e7843c` | `application/chat_context.py`：公共 lore 相关性排序，私聊传入本轮玩家文本；`application/group_chat_context.py`：群聊角色回复复用该排序；`docs/architecture/CHAT_MODEL.md`：记录真实范围和限制。 |
| `309719c` | `apps/web/src/GroupChat.tsx`：点击唯一命名群成员插入 `@名字`，保留光标位置并检查输入长度；`apps/web/src/product.css`：简洁样式；`CHAT_MODEL.md`：记录交互。不改服务端选人语义。 |
| `1b57f6b` | `AGENTS.md` 及 `docs/architecture/ADR/0001_reuse_mature_projects.md`：允许评估成熟组件；ADR 索引及 `ARCHITECTURE_REVIEW_001.md`：保留历史、标注被替代的独立实现限制。 |
| `7009288` | `scripts/build-portable.py` 和 `README.md`：加入 `--build-only`，允许构建而不隐式运行 smoke。默认脚本仍含自检。 |
| `6bfbb06` | HTTP CORS 修正为允许 `PUT`，否则桌面公共世界书开关的预检请求会失败。不要退回只有 GET/POST 的配置。 |

更早的 `64b6413` 已建立公共 lore 与群消息可见性；`5980f92`、`d7ca0b8` 已建立有界上下文读取/消息分页。继续前用 Git 查看需要修改的具体文件，不重新实现这些切片。

## 5. 接续工作需要知道的实际实现

### 5.1 从前端到 Core

```text
apps/web/src/main.tsx → App.tsx
  → connection.ts / CoreClient
  → ProductApp.tsx
    → WorldContent.tsx / ProfileEditor.tsx / ModelSetup.tsx
    → ChatTranscript.tsx / GroupChat.tsx
  → adapters/http/{worlds,profiles,world_content,player_events,chat_conversations,chat_messages}.py
  → application services
  → infrastructure/persistence adapters
```

- 桌面连接通过 Tauri `core_connection` 返回 endpoint/token/generation，浏览器开发连接通过 `virtual:core-connection`；UI 不硬编码 Core 端口。
- `App.tsx` health 成功后调用 `report_ui_ready`。Tauri 主窗口初始隐藏，不能把 Core ready 与 UI ready 混为一谈。
- API 协议从 `domain/api_contract.json` 集中读取，目前 `api_protocol = 1`。Tauri 的 dev UI 端口 1420 不是 Core 端口。
- `ProductApp.tsx` 默认整轮额度为 50,000，可设置 1–1,000,000；沿用 `livingworld.chat.turnTokenCeiling` 和 `livingworld.lastWorldId` localStorage 键。
- 模型配置 UI 在 `ModelSetup.tsx`；Rust IPC/config/credential 操作在 `src-tauri/src/lib.rs`、`llm_config.rs`、`credentials.rs`、`supervisor.rs`，不存在独立 `model_setup.rs`。

### 5.2 消息、claim 与角色生成

```text
打开联系人 → ChatConversationService → 世界内稳定 Character/Conversation
保存玩家消息 → ChatMessageService → SqlAlchemyChatMessageStore → pending turn
请求回复 → DirectChatReplyService / GroupChatReplyService
  → 上下文与 route/token preflight
  → 持久一次性 claim
  → governed gateway.generate(..., turn_budget=同一对象)
  → 校验 → durable reply / group completion
```

- HTTP 前缀为 `/api/v1/worlds/{world_id}/conversations`，需 bearer；发送还需 `X-Request-Id`。
- 私聊保存：`POST /{conversation_id}/messages`；群聊保存：`POST /{conversation_id}/group-messages`。二者返回 202 pending，不等于模型已经发言。
- 生成分别使用 `POST /{conversation_id}/turns/{turn_id}/reply` 和 `/group-turns/{turn_id}/reply`；对应 GET 可读 pending/claimed/completed。已完成结果读取不再次付费生成。
- UI 使用 `GET /{conversation_id}/messages/page`，默认 50、最大 100，游标 `before_position`；旧的完整消息读接口仍保留，不能让普通页面退回每次读全部历史。
- claim **不可重新领取**。模型失败、HTTP timeout 或重启后的 claimed turn 不自动 replay。UI 可查询一次状态，不自动再次生成。部分群回复已经持久提交时保留它们。
- 私聊及角色群回复只接受匹配 invocation 的非空、有界文本，finish 为 STOP 或 REFUSAL；截断不是成功回复。群选择器只接受合法成员 ID，已有回复后可返回 STOP。
- 群回复当前另外有 32 条安全上限；选择请求输出上限为 64 Token。`@` 只绕过首次选人调用，不禁止本轮随后选择其他人。
- 当前回复服务用 **`generate()`**，不是 `stream()`。基础 SSE adapters 已有，不代表 UI 已逐字流式显示。接通流式时不能破坏一次性 claim、终端校验、账本和未知用量处理。

### 5.3 聊天上下文

直接入口为 `application/chat_context.py::DirectChatContextBuilder`；群入口为 `group_chat_context.py::GroupChatContextBuilder`，共享公共背景、记忆及历史窗口工具。

- 角色人格从当前世界 accepted import replacement lineage 解析；更新卡片不换 runtime Character 或丢失聊天。
- 本地通用/世界资料都提供给角色，system 明确世界专属描述优先。没有自动语义冲突合并器。
- `private_chat_memories` 当前最多 12 条、内容累计 8 KiB；按 Character owner 读取，不是 RAG。
- prompt transcript 按完整 turn 截取，最多 32 条消息/96 KiB，不裁掉当前 turn；持久层有有界读取，不为 prompt 加载全部历史。
- `application/chat_recall.py` / `infrastructure/chat_retrieval.py` 在最近窗口之外召回当前会话原文；先授权、三页/300 条/512 KiB 扫描、最多四条/8 KiB 注入。FTS5 + jieba 词法排序，带出处、无新证据记忆或持久索引，详细范围见最新接续。
- 本角色曾参与的群消息读取默认最多 32 条，再受 8 KiB 内容预算约束；另一个群回复时排除当前群以避免重复输入。群选人器不拿任何角色私有记忆。
- 角色卡 `first_mes` 仅作有界语气示例（8 KiB），不是自动发出的开场消息。
- 导入文本、背景、个人资料、消息都是 lower-trust data。世界书/角色卡中的作者指令不是新增 privileged system instruction。

### 5.4 公共世界书为有界基础激活

- `SqlAlchemyWorldContentStore.list_common_lore` 先限定指定世界、当前 accepted 版本及明确公开的条目；匹配不能授予隐藏条目权限。`CommonLoreEntry` 可附带同快照的所属 LoreCollection 供读取扫描深度。
- `application/lore_activation.py` 消费已规范化的常驻、主/次级关键词、大小写、完整单词和扫描深度。`common_chat_lore` 私聊使用当前可见 transcript，群聊使用包含已保存发言的当前群 transcript；不扫描另一个会话或背景正文。
- 默认最近两条消息，条目 scanDepth 覆盖书 scan_depth，最多 32 条/16,384 个原始字符。零深度不触发普通关键词；常驻不依赖关键词。四种已识别次级模式生效，空次级列表不附加条件；未知模式不猜测。
- 未命中条目不再填入剩余背景。关键词命中优先于常驻，其后 priority 降序、order 升序、稳定 ID 排序；最多 16 条、title/content 共 12 KiB，超预算跳过。ignoreBudget 不绕开限制。
- 正则/模板关键词及尚未支持的概率、时序、互斥组、角色筛选等条件使条目暂不参与聊天，界面解释原因。向量检索、递归扩展、源插入位置及脚本不执行；不是完整 ST World Info 兼容。
- 内容 GET/预览增加只读 activation_summary、secondary_keywords；无数据库迁移。公共标记仍按 `(world_id, import_id, entry_id)` 保存，替换导入后需要对新版本显式开放。

### 5.5 Token、预算和模型配置

- `ChatTurnTokenBudget` 是本轮串行使用的内存预留对象；玩家 Message/turn 保存原始额度、claim 防止重启重新开始。同一群轮中的选人和回复共享一个对象，并传入底层物理 retry/fallback。
- 必须有 `HARD_UPPER_BOUND`。当前按配置的整个模型输入上界保守预留，不是按短 prompt 猜输入长度；额度小于可信输入上界时，即使一句话也可能不能发。
- usage 不完整时保守消耗预留并关闭本轮；超过上界时报告完整性问题，不把事实用量改小。
- `bootstrap/llm_runtime.py::_chat_reply_configuration` 只选唯一合格模型或显式 `character_dialogue` 的 BALANCED route；多模型无路由时不猜。每个候选都需可信 limits；可用性还依 route policy 检查 session credential。
- 桌面简化模型设置面向 managed single configuration，可创建/更新并通过 supervisor 重启 Core；不会在保存配置时测试 key 或生成回复。高级配置不能被简化表单默默覆盖。
- 四种 adapter 的“有实现”不保证任意代理地址/模型都兼容。浏览器没有桌面的 OS credential IPC，不能把桌面设置能力宣传成浏览器完全相同。
- 已有 financial Budget Guard/usage ledger 和聊天 Token 上限是两种不同约束。预算按 requested ModelRef 归属，reported model 可用于实际定价。不要改成 requested OR reported budget matching。
- 账本 START 失败不得调用模型；模型执行后 FINALIZE 失败不能重放模型、不能伪造零费用，持久 START 保持 INCOMPLETE。routing 已有 invocation 级共享 monotonic deadline，fallback 不重置。

### 5.6 Canonical state、记忆与迁移

- `WorldTime` 是逻辑 epoch 的整数微秒；真实时间用 UTC-aware datetime。两者不可隐式互换。前端显示用 BigInt/字符串，不经过浮点微秒。
- Alembic 是唯一迁移 authority，当前源码 head 为 `0022_world_common_lore`。legacy `schema_version`/`migration_history` 是兼容审计，不是另一套 runner；ambiguous legacy 状态 fail closed。
- `0017` 世界快照、`0018` conversations、`0019` messages、`0020` dispatch、`0021` group completion、`0022` common lore 已存在。不要重新创建同名机制或凭旧 Stage 文档猜 schema head。
- 普通移动唯一入口为 `ActionResolutionService`；兼容 `MovePlayer` 适配进去。初始化放置与玩家行动不是同一语义。
- CreateWorld commit 后经 lifecycle port 注册 WorldSimulationRuntime；运行时失败标 degraded，不把已提交世界谎称 rolled back。
- `RecordEpisodicMemory` 要求真实、同世界且该 Character 获准的 Observation 证据。普通聊天目前不生成这些证据，不自动写 EpisodicMemory。不能为实现“独立记忆”伪造 Observation 或自动把消息断言为事实。
- Player 的置顶事件 feed 先按绑定 Player 的 event Observation 授权；安全标题能力有限。无已知事件时为空，禁止用假剧情填补。

## 6. 已确认决策与理由：避免重新询问

长期约束见 AGENTS；这里记录接续实现时最易误判的决定：

| 决策 | 原因/实现影响 |
| --- | --- |
| 世界专属内容是确认快照 | 同卡/同书在多个世界使用不能串改；替换沿 lineage 保留身份与历史。 |
| 首次开聊才建 Character | 导入只是创作内容；通讯录先可见，不触发后台角色或付费活动。 |
| 群聊独立选人 | Director 的 batch-planner contract 不能被逐句选人调用改变；`@` 确定首位。 |
| 输入+输出整轮硬上限，可信保守预留 | 防止多角色、选人、retry/fallback 累计爆量；用户接受宁可提前停。 |
| 公共背景可共知，暗线默认禁止 | 导入不等于授予角色所有知识；关键词 relevance 排在权限过滤之后。 |
| 所有固定群成员看到消息 | 沉默成员不会因没回复就遗漏群消息；消息内容仍可能是假话。 |
| 台词直接发送，持久创作预览确认 | 避免聊天逐条确认，保留 authored content 的审查边界。 |
| 不再要求独立实现 | 优先效果和维护成本；[ADR-0001](docs/architecture/ADR/0001_reuse_mature_projects.md) 已替代旧 review 的该限制，未更改 Apache-2.0。 |

## 7. 不应重复的路径与历史问题

- 不能把 `cargo test` 留下的桌面 executable 当作正式 custom-protocol 产物。历史曾出现 Core/supervisor ready 但无 ui_ready；正确正式命令在第 10 节。本轮没有再次 smoke，也不声称历史原因已再次验证。
- 不反复启动窗口/点击/第三次无新证据重试同一失败。保留 artifact 路径、修改时间、安全 stdout/stderr 与实际等待条件后再判断。
- `uv` 默认 cache 访问曾在本受限会话被拒绝，最近打包改用已有 `.venv\Scripts\python.exe` 调用同一脚本。不要把 cache 权限问题误判为项目代码坏了或循环重装依赖。
- 默认 `build:portable` 含 standalone smoke 和 Rust supervisor test；“只打包”需 `--build-only`，不要绕过用户负责测试的决定。
- 不沿用 legacy MovePlayer 独立写 PlayerMoved，不添加自动 Activation→action 或 Observation→Memory 来拼演示链路。[CODEBASE_AUDIT.md](docs/architecture/CODEBASE_AUDIT.md) 的 Q-001A disposition 已记录原因和修复。
- 对未知/缺少模型 bounds、含糊的 `@`、未知 provider usage，不能用“看起来够用”放行。
- 不把原始 ST world-info regex、脚本、私有字段直接执行，不把 raw compatibility 数据当 privileged prompt，也不为“完全兼容”破坏 canonical invariant。
- 不直接粘贴需要不同许可义务的代码后仍宣称全部 Apache-2.0；目前实际复用的是公开行为/规范及适合的既有依赖，如 `react-markdown`，不是一个已嵌入的 ST runtime。

## 8. 尚未完成、风险与技术债

### 用户体验缺口

1. **长期独立记忆尚不完整。** 已有 owner-scoped EpisodicMemory、有界近期窗口及当前会话较早原文词法召回；普通聊天尚未形成长期证据记忆。召回仅扫描窗口前最多三页，不支持同义/指代和无限历史；别将持久 Message 与完整记忆系统混为一谈。
2. **世界书与酒馆能力仍有差距。** 当前支持有界基础条件激活，向量、递归、概率/时序和源注入位置尚未接入；隐藏背景没有角色专属授权传播路径。不能宣称已实现 ST 的所有功能。
3. **Director 和主动事件尚未生产接通。** 现有世界时间、scheduler 和事件账本不能自己生成丰富剧情；event feed 当前只有有限安全标题。
4. **聊天仍是整段生成后出现。** 缺少普通界面流式输出；群聊可能有多次选人和生成耗时。
5. **保守 bounds 配置对普通用户仍有门槛。** managed model UI 要手填核实过的上界；不能为了降低门槛随意估值，丰富 Model Registry/安全候选预设仍需推进。
6. **未知结果/claimed turn 缺少完整恢复 UX。** 当前不重放可防重复付费，但用户可能看到已存玩家消息却没回复；完善明确状态说明，不能偷偷清除 claim。
7. **模型设置仅有简化管理。** 多 provider/route 高级管理、tools、真实代理兼容验收、云端/多用户身份不完整。

### 文档和维护风险

- `docs/architecture/PRODUCT_SURFACE.md` 个人资料部分仍有旧阶段“未实现 prompt assembly”句子；现在 `chat_context.py`/`group_chat_context.py` 已组装资料。后续可局部修正文档，别因此再写一套上下文。
- `CHAT_MODEL.md` 的少量早期段落仍写“API opens/lists only”，后文已描述 send/reply。以真实 endpoint、当前服务和后续段落为准。
- `CODEBASE_AUDIT.md` 保留旧 A-001～A-005 的 FIX_NOW 文字供审计历史，顶部 disposition 已解决；Q-001B Inspector 已在代码中，不应重新宣告阻塞。DEFER 中的大 command handler、广 UoW、schema compatibility matrix、provider pipelines、全 ledger replay、large ORM/supervisor 等债务仍不能说已全消除。
- 便携版未签名/无自动更新；本机历史 `livingworld_core` wheel 文件比最近业务代码旧，不能当最新 dreamtalk wheel 分发。
- 本轮未确认新的可复现业务 bug；“尚未运行验证”不是“已知无 bug”。旧 Python 应用错误弹窗的本机原因没有本轮证据，不应编造已修好或已复现的结论。

需要用户判断但**尚未在当前切片解决**的边界，应在有具体设计时汇总：新 chat-memory evidence/形成路径、隐藏设定如何授权到特定角色、World Plan/event narration 的详细产品语义。先推进其他确定工作，不重新询问第 6 节已确认项。

## 9. 验证与现存产物

### 本轮实际完成的核对

- Git status/log/diff/cached diff；D 盘与工作克隆业务基线一致且写入前 clean。
- 阅读主要 UI、API、chat/context/reply/budget、bootstrap、public lore persistence/migration、memory、Tauri 配置/入口和构建脚本。
- 核对现存 ZIP 的 SHA-256、exe 修改时间及开发依赖目录存在。
- 本轮仅文档编辑，不跑 Python/前端/Rust 测试、smoke、付费 API，不启动应用，不重新构建。文档写入后的 `git diff --check` 无问题；链接脚本检查 535 个本地目标，0 broken（111 个外部 URL 仅计数，未在线验证）。

前序对话曾报告最近的 Web build 与 `build-portable.py --build-only` 成功；本轮重新确认了产物存在，但未复跑构建、未取得本轮运行验收证据。不要引用旧测试数量作为当前代码全部通过的证明，也不要把“配置可保存”当作“API 真实调用成功”。

现存可供用户试用的文件（2026-09-28 核对）：

```text
D:\LivingWorld\artifacts\portable\dreamtalk.zip
D:\LivingWorld\artifacts\portable\dreamtalk\dreamtalk-desktop.exe
D:\LivingWorld\artifacts\portable\dreamtalk\core\dreamtalk-core.exe

ZIP SHA256:
4B186D95477E26F97DF8652AC5CC3400BC9FC6FB98F5A55ACCA434F7CF5638D8

desktop exe LastWriteTimeUtc: 2026-09-27 15:54:43Z
core exe LastWriteTimeUtc:    2026-09-27 15:54:17Z
```

该 ZIP 没有在本轮确认到一个内嵌源码 commit marker；不能仅由时间戳保证可执行文件与任意后续 HEAD 完全一致。两份文档的本轮更新不需要重打包。运行时需整个解压目录及 WebView2，不能只复制桌面 exe。

用户尚需自行验收：自己的 provider/key/model 的实际聊天，角色卡/世界书导入与公共开关效果，群聊选人和整轮上限，切换世界隔离，重启后数据，暂停/倍率/availability 和设置更新。没有授权因此自动发送付费验证调用。

## 10. 关键命令与调试入口

开发依赖见 README：Python 3.12+、uv、Node 24+、Rust/MSVC/WebView2。缺依赖才安装；本轮 D 盘 `.venv` 与 `node_modules` 存在。

在实际开发仓库根目录：

```powershell
# 启动选一个，不同时抢占 UI dev 端口
npm run dev:desktop
npm run dev:web
npm run dev:core

# 必要时构建；这些不是用户验收结果
npm run build:web
npm run build:desktop
npm run build:portable -- --build-only

# 若 uv cache 权限仍阻塞，且现有 venv 含 PyInstaller
.\.venv\Scripts\python.exe scripts\build-portable.py --build-only

# 文档/差异静态检查，不是业务测试
.\.venv\Scripts\python.exe scripts\check-doc-links.py
git diff --check
```

`build:desktop` 已在 package.json 中带 `--debug --no-bundle --features custom-protocol`；不要手拼替代命令。portable 脚本依次冻结 Core、正式 release 构建桌面、复制 `core/` 并 ZIP；`--build-only` 跳过生命周期检查。

认证/bootstrap/runtime 入口：`bootstrap/cli.py`、`bootstrap/reader.py`、`application/runtime.py`、`infrastructure/database.py`；Rust `supervisor.rs`；React `connection.ts`。排查 Core→Supervisor→UI 时区分 `core_ready`、`supervisor_ready`、`ui_ready` 和 shutdown，记录实际启动的 artifact，不泄露 bootstrap secret/bearer/API key。

应用数据保存到 Tauri app-data（identifier 仍为 `app.livingworld.desktop`）；独立 Core/browser 开发 launcher 使用历史 `%LOCALAPPDATA%/LivingWorld/development`。不要把数据库放到源码/安装/便携目录，不因改名自行迁移数据。

相关架构阅读顺序：

1. [CHAT_MODEL.md](docs/architecture/CHAT_MODEL.md) 与 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md) 已确认补充。
2. [PRODUCT_SURFACE.md](docs/architecture/PRODUCT_SURFACE.md)、[PRODUCT.md](PRODUCT.md)、[LLM_PRODUCTION_COMPOSITION.md](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)。
3. 按当前改动选择 [EPISODIC_MEMORY.md](docs/architecture/EPISODIC_MEMORY.md)、[LLM_ROUTING.md](docs/architecture/LLM_ROUTING.md)、[LLM_BUDGET_GUARD.md](docs/architecture/LLM_BUDGET_GUARD.md)、[LLM_ACCOUNTING.md](docs/architecture/LLM_ACCOUNTING.md)、[PERSISTENCE_MODEL.md](docs/architecture/PERSISTENCE_MODEL.md)。
4. 借鉴世界书时查 ADR-0001 中的官方 ST World Info 来源；要引用具体源码/依赖时重新核对项目版本与许可，而不是相信聊天记忆中的“它可以复制”。

## 11. 下一步优先顺序

以下是基于当前缺口的接续建议，不是额外冻结的架构方案；每个新功能仍先调查成熟实现：

1. **接通聊天流式呈现。** 复用已有 provider stream adapter/contracts，先解决 terminal 校验、claim、预算账本、未知 usage 和取消的一致性；半截台词不成为 durable success。同时优先处理用户已复现的验收问题，不替用户运行测试。
2. **完善整轮结束说明。** 目前群聊可显示已保存的逐条发言，但 completed 不能区分自然 STOP、Token 不足和安全条数上限；先形成具体有界持久/接口方案再实现，不能只凭状态猜原因。
3. **评估召回效果和更远历史。** 当前词法原文召回已接线，用户真实长对话反馈到来后再评估噪声、同义词和三页之外历史；优先成熟可控方案，保持授权先于排序。聊天自动形成 EpisodicMemory 的 Observation 证据路径须单独给出具体设计，不改变 C-007A。
4. **改善模型设置和世界书体验。** 复用现有 ModelSetup/registry 和基础 lore 激活；补 route/bounds 说明，未知模型上界不猜。世界书向量、递归、时序和隐藏角色授权先明确范围，不重复已实现的基础关键词能力。
5. **之后再补世界话题生产。** Director 在 batch-plan/reservoir 边界内推进，借助已有 scheduler/Kernel 提交合法事件；群选人器仍独立，hidden facts 不泄漏。
6. **持续提供最新便携产物。** 有可编译业务变更时使用 build-only，明确未验证处；完整验收通过并获用户明确批准后才进行 GitHub push/release。

## 12. 最容易破坏的地方

- `livingworld` 模块、Tauri identifier、storage keys、协议 derivation 和格式后缀是兼容标识，不能搜索替换成 dreamtalk。
- 公开 lore、群消息可见和角色私有 Memory 是三类输入，不能做一个“全世界上下文”查询绕过授权。
- accepted 卡片、runtime Character、Conversation、WorldTruth 是不同生命周期；不能靠导入就创建所有后台角色/事件。
- Input+output 的 Token ceiling 是**整轮**，不是每人/每次调用；重新建 budget 或重置 fallback deadline 会破坏约束。
- Message 的普通幂等保存与模型的不可重领 claim 是不同保护；“重试保存”不能变成“再次请求模型”。
- `LLMResponse` 是非流式完整结果；`TextDelta` 是流式内容；`LLMStreamCompletion` 只含 terminal accounting metadata，不能把整段文本塞回 completion。
- 长期记忆未完成不代表可以读取别人的记忆补齐；历史消息已持久化也不代表每轮都读全量。
- 旧文档的阶段限制、FIX_NOW 描述、独立实现限制需结合后续确认与当前代码，不把已解除的历史条件重新当作阻塞。
- 没跑测试就写“未测试”，只有 build 就写“构建成功”；不要把可执行文件存在、health ready 或旧测试通过说成用户体验已验收。
