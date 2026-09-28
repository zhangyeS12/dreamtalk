# 2026-09-28 内容编辑与联网生成的复用决定

用户验收反馈：角色卡、世界书只能导入，缺少界面创建/编辑。新增直接填写与“描述需求 → 联网检索 → 模型整理 → 可修改草稿 → 预览 → 用户确认”的产品入口。

## 调查与选择

| 来源 | 已核对版本/定位 | 许可证与决定 |
| --- | --- | --- |
| [SillyTavern](https://github.com/SillyTavern/SillyTavern/tree/1.19.0)、[Character Design](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)、[World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/) | 1.19.0，package.json blob `ea41cec0158fc2678f16d587d7bcf880be3fc302`；角色描述/性格/情境/开场白/示例与逐条关键词编辑的公开行为 | AGPL-3.0；采用公开交互与格式经验，未复制源码，未引入整个 Node 运行时 |
| [DDGS](https://github.com/deedy5/ddgs/tree/v9.16.0) | 固定 9.16.0；pyproject blob `19f93dc8d90cb055ee7ed1f8878a5c5ec9f229cb`、ddgs.py blob `004c7da9486db1bf352943f66b5db6af2153ec6f`；安装后核对 dist-info 和源码版本 | MIT；直接复用多引擎搜索、传输、去重与排序，不另写搜索爬虫。只调用 text，不使用 extract 任意页面读取 |
| [SillyTavern Character Card Generator](https://github.com/shadowtheimpure/SillyTavern-Character-Card-Generator) | README main blob `c083efe64c0cc395885ab9d29ba37d2666280f97`；角色表单、AI 生成和预览工具 | GitHub 仓库 metadata 未声明许可证；没有复用源码。它是独立 Node 应用，文档没有本项目所需的来源/冲突链路；再引入其模型设置与 runtime 会重复既有能力 |
| 本项目 governed LLM、Pydantic、ContentDraft/ImportPreview、WorldContentService、SQLite/Alembic | 当前仓库既有实现 | 复用模型凭据、路由、Token 硬上限、retry/fallback 预算、账本和确切预览哈希；未增加另一套模型 SDK、向量库或 agent runtime |

DDGS 9.16.0 依赖 click（已经存在）、primp 和 lxml；uv.lock 本次解析为 primp 2.0.1（MIT）、lxml 6.1.3（BSD 及上游 notices）。primp LICENSE 核对 v2.0.1 blob `16e546952e854e7c7aed06eb3eb1f4e14be98943`。完整许可证/上游 notices 放在 docs/licenses 并随包分发。该版本代码不是 P2P/DHT 搜索，没有引入此类节点或额外搜索 API 密钥。

## 最终实现

- 设置增加新建角色卡、新建世界书和编辑已有内容。文件导入仍可用；手动创建不要求模型或密钥。
- 角色表单：名称、描述、性格、背景、情境、说话方式、开场白、示例、标签、备注。世界书：名称、简介、增删条目、正文、主/次关键词、四种次级逻辑、常驻、启用与排序。高级兼容条件仍保留，其当前支持范围由既有激活摘要解释。
- 原生内容直接构造 canonical ContentDraft，使用 NATIVE/BUILDER provenance，不伪造文件导入时间或 RawImportEnvelope。编辑复制独立 graph，保留原导入扩展、未开放字段、素材和角色内嵌世界书；旧快照保持不变。
- 检索只发送用户显式填写的需求；不读取其他世界、隐藏剧情、聊天或玩家资料。固定 bing/brave/duckduckgo 后端与 8 秒单引擎超时，最多八条去重摘要，每条最多 1,000 字符。仅保留 HTTP(S) 公网出处链接，不自动请求搜索结果页面或执行其中的指令。
- 模型通过现有 runtime 的 content_builder 用途和 BALANCED/唯一可用模型配置生成一份 JSON；同一次请求的 input+output、物理 retry/fallback 共享设置中的 Token 硬上限。输出上限不超过模型限制与 8,192 Token；没有模型修稿、联网规划的额外调用。
- 本地验证字段结构、类型、长度、kind、条目身份和出处编号。缺少字段依据标记为待核对，开场白/情境/示例统一标记创作建议。冲突识别与事实支持判断由模型提出，不能当作独立事实核验。
- 0023 新增独立 content_builder_jobs 表，原子单次 claim 与持久 ready/failed receipt。复用同一 request ID 只读取状态，World 或输入不一致拒绝。进程重启遗留 running 请求报告 interrupted；不自动重放。UI 保存最近 request ID，可重新进入编辑器检查结果；检查是 GET，不产生模型调用。
- 搜索证据、原始生成稿、claims、冲突和待核对项进入当前 World 的 authored preview。编辑后的字段与原稿不同时明确标注。现有 reviewed hash、15 分钟预览有效期、replacement CAS 和幂等确认负责保存。
- 保存不会写 WorldTruth/Observation/CharacterBelief/PlayerKnowledge/EpisodicMemory。角色首次打开聊天才实例化；世界书仍默认隐藏，保存后逐条明确公开；更新重新确认可见范围。

## 本切片的实际边界

联网依据是搜索摘要，不是已阅读完整页面或已核实全部原作事实。网络封锁/搜索引擎限流可能导致检索失败；不会静默改用无出处的模型记忆补全。需要用户在预览时核对原网页和创作建议。

当前编辑支持标准化单角色卡、单世界书；角色内嵌世界书保留，未在角色表单展开编辑。新建内容的结构化字段总量最多 256 KiB、最多 128 个条目；大量/特殊导入仍可以走既有文件路径。未添加画像/头像生成、网页全文抓取、来源持续更新或创建完整可运行 World 的 Builder。

本次没有新增、修改或执行测试，没有启动应用、调用模型或执行 DDGS 搜索验收。Ruff、ESLint/TypeScript 与生产编译/打包是静态/构建证据，不替代用户真实联网、资料质量和世界隔离验收。现有硬编码旧 schema head 的测试预期需在用户授权维护后同步。
