# Roleplay Chat Model

Status: approved product and architecture decisions; implementation is incremental.

Related concepts: [Conversation and Message](DOMAIN_MODEL.md#21-conversation),
[system responsibilities](SYSTEM_OVERVIEW.md#组成与权威边界), and
[confirmed product decisions](../product/PRODUCT_SPEC.md#已确认的产品补充决策).

## Purpose

Chat is the main player experience. A Conversation is a durable communication
history between the current world's bound Player and one or more runtime
Characters. Chat messages provide roleplay and topics; they are not WorldEvents,
WorldTruth, CharacterKnowledge, or PlayerKnowledge by themselves.

## 角色扮演优先与开场

私聊和群聊以扮演为主要任务，通信入口不预设远程或同场。角色卡是人物、性格、关系设定与语气的首要依据；题材、内容尺度和整体叙事风格优先采用当前世界已确认的世界风格。当前获准世界书、记忆、身份及活动资料用于补充背景，不把角色变成活动记录播报员。回复可包含台词、动作、神态、心理和场景描写；只有补充的系统记录需要按其主体、来源与时间解释，缺少后台记录不禁止当下场景表演。

`application/chat_roleplay.py`供私聊与群聊共用。完整描述、性格、背景、情境、表达指导以独立文字段落进入SYSTEM；非空`system_prompt`替换默认的写作主提示，不只是JSON字段，也不替换数据权限、玩家自主、传输或预算边界。补充USER资料只留角色ID／名称引用，不重复发送整卡。`{{char}}`／`{{user}}`按当前角色名、世界优先的玩家名作单次字面替换；只有卡内主提示和后置指令另外支持`{{original}}`引用相应默认写作要求。替换结果不递归求值，未知宏保持字面，不执行脚本、表达式或插件；creator_notes仍是元数据。

对话示例按`<START>`分块，仅识别当前角色／玩家名称及其冒号前缀，生成明确标记的USER／ASSISTANT示范；未识别说话者的文本保留为文风示例，不升级为SYSTEM指令。完整`first_mes`在真实历史前以ASSISTANT场景示范提供，并有独立标记说明它来自卡片。初次互动承接开场，已有对话以最新进展衔接，不重演或覆盖后续变化；不创建、补写或修改持久消息，也不认证世界事件。开场每轮完整提供，仍无单独8 KiB省略规则，不参与可选背景裁剪；这与酒馆将开场持久化为新聊天第一条消息的行为不同。

`post_history_instructions`在容量打包后附于真实历史末尾：最后为USER时增加独立文字块，否则增加标记为卡内写作要求的末尾USER消息。使用此统一形式是因为现有Anthropic／Gemini接口不接受历史后的SYSTEM，不能为了位置而放宽adapter门禁。四类路径都保持末尾位置，不使用assistant prefill，不把它保存为玩家新消息。打包后的实际请求包含全部示例、完整开场与后置要求，再做可信输入／输出预留；无法容纳必要内容时明确拒绝，不静默截卡或额外付费重试。

群聊回复将裁剪后保留的历史按USER／ASSISTANT分别发送。当前角色的历史直接提供正文，其他角色用姓名和本次成员编号标明来源；编号按身份排序，在同一成员集合内稳定，用于区分同名角色，不把UUID嵌进可模仿的历史台词前缀。补充资料的`group_speakers`标明当前角色；稳定身份仍用于程序权限和独立selector，不改变角色身份。历史不再重复出现在补充JSON的`transcript`中。selector继续使用其有界JSON资料、选人与整轮费用规则，不接收开场示范。其他角色的私人信息仍在输入前过滤，开场不代表群内成员看过私聊。

活动、长期记忆、摘要、身份及社交来源解释只在输入具有相应资料时提供；基础知情、来源与玩家自主边界始终存在。移除事件／记忆／媒体指令里的通用寒暄、购物、咖啡及表情台词示例，避免与卡片文风竞争。同次辅助提取及普通正文兼容保持，不增加第二次模型调用；输出不是世界事实，Kernel及持久化校验保持。

本次依据用户2026-10-20“取长补短，优化聊天”的决定，参考酒馆**1.19.0**的[提示排序实现](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/public/scripts/PromptManager.js)、[角色字段与开场](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/public/script.js)、[示例编排](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/public/scripts/openai.js)及[Prompt Manager说明](https://docs.sillytavern.app/usage/prompts/prompt-manager/)。酒馆为AGPL-3.0；本项目以现有Python 3.13标准库独立实现，不复制其代码、不新增依赖。复用理由是分离人物写作、示范和历史位置，同时保留当前供应商及世界权限边界。未引入完整酒馆宏、世界书深度注入或插件，也未更改模型配置、温度、采样或思考参数。实现、工程检查与用户验收分别见[状态清单](../PROJECT_STATUS.md)。

## 动态角色卡词条

导入后的角色卡快照保持不变。动态记录以世界、角色卡根导入 ID、字段和范围为边界，字段只允许角色描述、性格、背景、情境和说话方式。每条记录保留创建时间、来源、启用状态、当前选择和锁定状态；同一字段与范围最多有一个当前选中版本。用户通过原有“编辑角色卡”入口修改基础卡片；模型提出的动态版本直接显示在原卡对应字段下方，历史内容不会被覆盖。点击标记内容展开时间线后，可以采用、恢复、停用和锁定版本。当前版本显示为横线，新建内容显示为波浪线，停用版本显示为灰色；这些标记只属于界面，不进入模型正文。

角色回复的同次可选辅助 JSON 可以提出最多四条角色卡成长建议。建议必须引用本次回复中的原文、置信度至少为 0.6，并经过字段、范围、长度和来源校验；程序把它们连同逐字引用和置信度保存为 `model` 来源的未启用草稿，时间线可回看建议依据，不自动改变当前扮演，用户采用后才成为提示词输入。锁定的当前版本拒绝新增、切换、恢复和停用，避免后续聊天间接覆盖用户决定。

提示词只读取当前世界、角色卡和玩家范围内 `active + selected` 的词条，历史、停用和未确认模型建议不发送。系统仍先发送世界风格、角色卡扮演规则、原始角色卡字段和当前动态覆盖，再发送经权限过滤的世界书、记忆、身份和活动资料；动态词条用于补充或覆盖对应字段，不创建 WorldTruth、不改变玩家自主权，也不把模型建议当作事实。

## 实际发送的消息顺序

私聊／群聊回复共用以下内部结构；供应商适配器转换到对应API的system／messages字段，不把世界风格降为普通资料或擅自重排对话：

1. 首个SYSTEM：世界风格全文（非空时最前）→基础扮演／知情／玩家自主边界与台词排版→当前NPC卡内主提示及人物段落→实际出现的补充资料来源说明。随后在同一个SYSTEM追加同次事件／记忆辅助格式、适用的媒体／表情要求。
2. USER补充资料：当前玩家公开身份、仅当前发言角色获准的初始认识、授权世界书／记忆及其他有效上下文。玩家专用卡仅作身份来源，不在这里执行其卡内系统提示。
3. USER／ASSISTANT卡片示例；随后是明确标记的完整开场示范。两者都不冒充已经保存的真实历史。
4. 经容量整理保留的真实USER／ASSISTANT历史。私聊的当前活动快照紧邻本轮玩家消息；群聊保留各角色的发言身份与顺序。
5. 历史末尾的写作要求：只扮演当前角色、台词排版、存在世界风格时的一句遵循提醒，以及卡内后置要求。最后为USER时附加，否则新增USER写作块，不新增世界事件或持久聊天消息。

世界风格不属于可选资料裁剪项，整段计入最终请求的可信预算；必要内容放不下时明确报容量问题。它在题材、内容尺度与文风上的“最高”是应用提供给模型的明确文字约定，不是供应商API中的独立强制权限层，也不能保证模型每次遵循或覆盖服务方自身约束。真实效果仍须以实际模型表现验收；位置核对不能代替模型对照。在线／离线联系沿各自较短的任务请求，在首个SYSTEM以同一风格写作块开头；群聊选人与离线规划不接收这项写作要求。

## 世界风格与台词显示

通讯录内的“世界风格”按当前世界独立编辑，先预览再明确确认；留空关闭。用户可约定题材、内容尺度、叙事方式，包括成年角色之间自愿的亲密关系题材；不内置强制成人预设。风格在这些写作维度高于卡内主提示、示例和后置要求，人物身份、性格、偏好仍来自角色卡，关系发展衔接真实对话。允许某类情节不代表角色必须答应；不覆盖服务方规则，不授予秘密、工具、程序权限，不改变玩家自主、WorldTruth或预算。

CoreClient的风格预览和确认请求均明确声明`Content-Type: application/json`，与身份编辑采用同一传输约定。检查不能只用自动补充请求头的Python `json=`调用或模拟成功的客户端方法；应覆盖真实客户端请求、后端解析及临时库写入后重读。

`application/world_style.py`负责校验、世界／修订绑定的预览摘要及写作块；`persistence/world_style.py`以CAS保存，Alembic增量建立`world_styles`，旧世界缺行时为空。输入最多4000字符，JSON转义后的UTF-8字符串最多16000字节，超限明确拒绝，草稿保留。私聊／群聊SYSTEM完整放入一份风格，参与既有最终请求预留，不静默裁剪；selector不接收写作风格。在线／离线联系的冻结快照包含风格与修订，写作阶段使用同一写作块，投递事务再核对当前修订；旧快照缺字段按修订0处理。变更后迟到结果取消，沿原去重回执，不自动重试可能收费的调用；离线的上下文变化记为跳过，不伪报生成失败。

消息显示参考酒馆**1.19.0**的[messageFormatting](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/public/script.js)引号分色行为（AGPL-3.0，仅参考行为）。本项目使用已有react-markdown生成的语法树和React安全节点独立实现，无新增依赖或AGPL源码。新回复要求台词用“”包围；显示兼容英文双引号、中文双引号、直角引号、双直角引号、法式引号和全角双引号。明确台词黄色，其余文字默认颜色；斜体动作、行内代码和代码块不着台词色。不对无标记旧文字猜测语义，不改存储原文，不额外调用模型。私聊、群聊、流式与来源原文共用显示器；玩家消息不着色。跨粗体／链接保留引号状态，未闭合引号只延伸到本段末；仍禁用原始HTML、危险／本地链接和外部图片自动请求。

## 回复正文与辅助格式容错

私聊／群聊的同次辅助提取允许直接输出完整角色正文；需要事件、记忆或媒体时才使用带`reply`的JSON。普通`[动作]`、`{动作}`、Markdown及正文中提到字段名均不能单独触发JSON校验。解析只在明确JSON代码块或对象／封装结构开头生效，不把损坏的封装原样展示为台词。

正常JSON保留通过校验的辅助字段。若只有JSON语法损坏，且位于开头的`reply`字符串已经完整关闭、合法并无第二个`reply`歧义，可以保留该正文并丢弃全部事件、记忆和媒体；正文缺失、空白、残缺、重复键、非有限数或非法Unicode仍拒绝。输出到达长度上限时也仅允许保留能够证明已关闭的`reply`正文，不把截断的普通文本猜作完整回复。既有64 KiB响应边界、整轮Token硬上限及严格结构化调用保持。

流式普通正文可逐步显示；可能是封装的前缀先等待识别。预览解码发生分歧时停止后续预览，最终校验并持久化的消息替换预览，不因此丢弃有效正文，也不额外调用模型。失败只记录固定原因类别，不保留或输出被拒绝的原始正文；格式失败提示不指向模型设置。一次性dispatch、账本结算、人工恢复和无自动重试契约保持。

恢复使用现有Python **3.13**标准库[`JSONDecoder.raw_decode`](https://docs.python.org/3.13/library/json.html#json.JSONDecoder.raw_decode)判定字符串结束，流式沿用已有pydantic-core **2.46.5**的[部分JSON解析](https://docs.pydantic.dev/latest/concepts/json/#partial-json-parsing)。前者沿PSF许可，后者沿现有MIT许可；不新增依赖，不手写引号／转义解析器。选择理由是精确区分已完整的正文与损坏的辅助字段。具体隔离检查及真实模型验收边界统一见[状态清单](../PROJECT_STATUS.md)。

### 群聊内部标签与正文

`application/chat_speaker_labels.py`只识别回复开头、与本次角色姓名及身份完全匹配的旧格式“姓名（发言者标识：UUID）：”。普通UUID、正文中的标签引用、其他角色标签及Markdown保持原样，不做全局替换。`reply_speaker_name`是群聊请求的本地解码提示，不加入供应商消息正文。流式可能的前缀先暂存，含UUID或CR/LF分片时不逐字露出；完成后仅正文进入消息保存、配音及后续提取。仅有完整或未完成的内部前缀时拒绝为空回复，不自动补调用。正文清理后重新过滤失去逐字依据的事件和reply来源记忆，玩家来源记忆保留。

历史中的旧标签只在准备模型历史的临时副本中去除，并核对原发送者身份；旧名称的识别不跨越引号、叙述标点或Markdown。持久聊天、旧导出和用户手工编辑的原文均不批量改写。当前角色历史不再带内部前缀，可减少模型模仿，但真实模型行为仍由用户验收；工程检查范围见状态清单。

## Runtime character identity

An accepted CharacterDefinition (imported, manually authored, or generated and
confirmed) is a world-scoped contact, not a runtime
Character. The first time a player opens a conversation with that contact, Core
creates or reuses its runtime Character identity. Importing a card alone does
not create a runtime Character. A character may be contacted remotely; opening
or sending a chat message does not move the Player or Character.

The link from an accepted world-content lineage to a runtime Character is
world-scoped. Replacing a card in one world does not replace another world's
snapshot or identity. A confirmed update supplies the current authored persona
for later generation while preserving the existing runtime Character and
conversation history.

The current implementation can open and list durable direct-conversation
identities for the selected local Player. Opening a current accepted character
contact follows its replacement lineage back to the first accepted import, then
uses stable world-scoped IDs for one runtime Character and one direct
Conversation per Player/contact pair. The existing `CreateCharacter` command
owns the canonical `CharacterCreated` event; opening a Conversation does not
itself emit a WorldEvent, move either participant, or create an Observation.
Replacing an accepted card preserves that runtime identity. An unselected
Player, cross-world import, or stale import cannot open a conversation.

The schema has a separate participant relation so group conversations can share
the same durable identity boundary. An authenticated group-create endpoint now
accepts two or more distinct current Character Card imports from the selected
Player's world. It resolves replacement roots, reuses the same lazy runtime
Character creation path as direct chat, and atomically stores one group
Conversation and its participants. The request ID identifies a retried create;
it cannot be reused for a different participant set. A separate owner-scoped
group-list endpoint reads these records. The ordinary Chat tab now lists the
selected Player's direct and group conversations separately, lets the Player
select current-world Character Card contacts to create a group, and displays
its persisted members. An uncertain create can be retried with the same request
ID and member set. Group messages use a separate authenticated send endpoint;
the legacy direct-message POST remains direct-only. Creating a group does not
move anyone, create an Observation, or
invent a WorldEvent beyond the existing canonical CharacterCreated events for
newly opened contacts.

An internal group transcript path now persists one idempotent Player send and
allows one durable dispatch claim. Under that claim, Character replies are
appended in zero-based reply order. A repeated append at the same ordinal must
match the committed Character and text; gaps and conflicting retries fail. The
claim fixes the eligible participant set, and a restart cannot acquire it
again. A terminal completion timestamp on the dispatch distinguishes a
finished group turn from a claimed but uncertain one; it can be set only after
at least one durable reply, and no new reply can follow completion. The 0021
additive migration preserves existing 0020 dispatch rows with an unset
completion timestamp. These records are Conversation messages, not WorldEvents
or Observations.
The group send endpoint stores the Player message and ceiling before generation.
The group reply endpoint reads that durable turn, preflights a trusted model
route and input/output bound, claims it once, then selects and generates
speakers under one shared token budget. A completed turn is read back without
another provider call. An interrupted claimed group turn
is not automatically replayed, because an earlier provider outcome might be
unknown.

The internal group-context builder resolves every participant through the
current accepted card in that world's replacement lineage while keeping the
same runtime Character identity. Speaker-selection input contains accepted
public persona fields and a bounded owner-scoped group transcript, but no
private Character memories. A selected Character's reply input adds only that
Character's own bounded EpisodicMemory view and the local Player's general and
current-world descriptions. Accepted card instructions guide character writing;
neither cards nor transcript text grant program or knowledge authority.
An exact `@display-name` in the Player message can identify
one participant; ambiguous names or multiple addressed participants fail
closed. The group composer offers one-click `@display-name` insertion for
uniquely named members; it does not change the server-side selection rule.
This builder prepares input only: it does not select a speaker,
dispatch a model. It accepts an owner-scoped pending
Player send before the one-time dispatch claim, so the group runner can perform
model and Token preflight without consuming the claim. After claiming, it also
checks the fixed participant set before preparing further replies.

The independent group runner chooses an eligible Character ID from the public
persona and group transcript. An exact unique `@display-name` bypasses the
first selection call; otherwise the selector chooses the first speaker. After
each durable reply it may select another speaker or stop. The selected
Character's prompt contains only that Character's permitted memory and
current accepted persona. It cannot access another member's private memory.
The group runner does not commit WorldEvents, infer Knowledge, or replace the
world Director. A model/transport failure after a claim leaves the turn
claimed and unreplayed; replies already committed remain visible. The UI
queries an uncertain turn once and never automatically repeats generation.

The current direct-conversation API opens/lists identities only. An authenticated POST endpoint now persists a Player
message and its pending turn through the application service, returning the same
result for a repeated request ID. It returns `202 pending`; it does not dispatch
a model or promise a Character reply. The ordinary UI opens a contact and
shows the durable conversation in the Chat tab. Message sending is enabled only
when a suitable production chat model and session credential are available.

An authenticated transcript read endpoint now returns stored messages in their
Conversation order for the currently selected local Player only. Missing Player
selection and cross-world/foreign Conversations fail closed. This read path does
not create a Message, Observation, KnowledgeAssertion, or WorldEvent. The Chat tab reads
this endpoint when a Conversation is opened and renders the durable ordered
transcript. Switching worlds or Conversations discards a late response from the
previous selection. The Chat tab sends through the authenticated player-send
endpoint and asks for a direct reply only when one text-capable production model
or an explicit `character_dialogue` BALANCED route has trusted billable-token
bounds and a session credential. No model is chosen implicitly when several are
configured. Every candidate in that route must have a trusted bound; preflight
uses the largest candidate input bound before claiming the turn. The per-turn token ceiling is
saved locally in the UI and persisted with each player send; later setting changes
cannot alter an existing turn. An unavailable model disables sending.

The player-send POST endpoint requires bearer authorization and `X-Request-Id`. It rejects
an unselected Player, a foreign/world-mismatched Conversation, blank or oversized
text, invalid token ceiling, and a request ID reused for different semantics.
It creates no WorldEvent, Observation, or KnowledgeAssertion. A pending turn is
not retried or completed by process startup.

The authenticated direct-turn read returns `pending`, `claimed`, or `completed`
from the dispatch and reply records, always under selected-Player authorization.
The direct-reply POST reads the original PlayerSend and ceiling from persistence;
it accepts no client-supplied message or model output. It returns an already
committed reply without a new provider call. A claimed turn cannot be replayed,
including after an HTTP timeout or restart. The UI may query its state once but
does not resend the uncertain model request. Provider and validation failures
are presented with bounded error labels rather than prompt/output data.

## Direct and group conversations

- A direct conversation has one Player and one Character.
- A group conversation has one Player and the explicitly selected Characters.
- Group participants share one ordered transcript.
- One player message starts one bounded group turn. It does not start autonomous
  character-to-character chatter outside that turn.
- A group-turn scheduler chooses one speaker at a time from the conversation's
  accepted character personas and shared transcript. If the player explicitly
  addresses a participant with `@`, that participant speaks next. The scheduler
  is separate from the world Director; it does not plan the world, commit events,
  or write final character dialogue.
- The selected speaker's final dialogue comes from that character's agent,
  passes system validation, and is sent without per-message user preview.

## Shared token ceiling

The local chat setting is a hard maximum for one player-initiated turn. It counts
provider-reported input and output tokens for speaker selection and every
character response, including physical retries and route fallbacks. Before each
physical provider attempt, the system must reserve a conservative input-token
upper bound and the allowed output-token maximum against the same turn budget.
If the input bound is unavailable or cannot fit, no provider call starts. When
usage is reported, only the unused reservation is released. When usage is
missing or incomplete, the reservation remains consumed conservatively and no
further generation starts for that turn. No next speaker starts after the
remaining budget reaches zero.

The configured ceiling limits LLM token use; it does not estimate price. The
existing LLM usage ledger remains authoritative for factual usage and cost.

`ChatTurnTokenBudget` implements sequential reservation/settlement arithmetic.
The LLM execution/routing gateway now accepts the same turn budget across
invocations. Before each physical attempt it uses the selected candidate's
explicit trusted `ModelUsageLimits` to reserve the maximum billable input and
allowed output; a missing or estimate-only bound rejects before accounting
START or provider dispatch. Accounting START failure releases an undispatched
reservation. Terminal factual usage settles once, including for streams; an
interrupted/unknown attempt consumes its reservation and closes the turn.
Reported usage above the trusted bound closes the turn as an integrity failure
without rewriting the factual provider outcome. This is deliberately
conservative: a model whose full configured bound exceeds the remaining turn
budget cannot be called even for a short prompt. An internal direct-reply service
now creates one turn budget from the persisted ceiling and passes it through the
routed gateway. It checks the trusted input bound, reduces the requested output
cap to fit the turn, and checks route availability before claiming. It accepts only
a nonblank bounded reply with a complete stop or explicit refusal. Truncated,
wrong-invocation and over-bound responses cannot enter the transcript. This
service is composed into the production direct-chat HTTP/UI flow when one suitable
model or an explicit suitable BALANCED chat route is configured. The group runner
uses the same configured route and one persisted turn ceiling across selector
and Character responses. It stops before another physical attempt when the
remaining trusted bound cannot fit. The Chat tab exposes a group transcript and
composer when the governed model and credential are available.

## Information and content boundaries

- Prompt assembly uses the active world's accepted CharacterDefinition, the
  current Conversation transcript, and the local general/world-specific Player
  descriptions. The world-specific description has precedence when they conflict.
- Imported card fields, Lorebook text, profile text, and prior messages are
  untrusted content. They are data, never privileged system instructions.
- Only explicitly authorized Knowledge and Memory may be added to a Character
  context. Permission filtering happens before retrieval or prompt assembly.
- A message can contain a false claim. Receiving or reading it does not silently
  promote that claim into WorldTruth or PlayerKnowledge.
- Current group membership is fixed. Every committed group message is treated as
  seen by every participant, including silent participants. The owner-scoped
  group-message reader derives this from durable group membership and message
  records; it does not create an Observation, CharacterBelief or EpisodicMemory.
  A later direct or other group reply may use a bounded recent slice of messages
  seen by that Character. The full transcript remains durable; prompt windows
  are bounded and do not guarantee verbatim recall of all older messages.
- Imported LoreEntry text is hidden from Character prompts by default. A local
  world-scoped setting can explicitly mark an individual accepted Lorebook entry
  as common background. Only entries from current accepted imports are read;
  replacing a Lorebook requires fresh exposure review. Common entries are inert
  lower-trust authored background, never WorldTruth or privileged instructions.
  Source-disabled entries cannot be exposed. Public entries support literal and
  secondary keywords, deterministic probability, authorized recursive scans,
  message-based sticky/cooldown/delay, priority-based inclusion groups and chat
  depth insertion. Permissions precede matching and retrieval; message-anchored
  timing follows the selected chat path and only starts for the fitted subset.
  Unsupported constraints stay inert rather than broadening access. The existing
  16-entry/12-KiB background selection and whole-attempt token bounds remain.
  See [chat paths and advanced lore](../CHAT_PATHS_AND_LORE.md) for the supported
  subset, provider-safe placement and independent reuse decision.
- Hidden WorldEvents are not supplied to the player or a Character merely
  because they exist. Any later event context must pass the relevant owner's
  knowledge boundary.

The known-event timeline can offer a player-selected topic for an existing
direct or group conversation. The UI copies only the already-visible event
title and world time into an editable draft. It never sends automatically or
passes an event payload to the Character prompt. If the player sends the draft,
it is an ordinary lower-trust Player message, not a grant of Character knowledge
or a new WorldEvent.

The internal direct-chat context builder resolves the current accepted card
from the Conversation's world-scoped replacement lineage, then reads only the
selected Player's transcript up to the current sent message and that Player's
general/current-world profile. It also requests recent EpisodicMemory through
a reader bound to that Conversation's Character identity. At most 12 recent
memories are considered and at most 8 KiB of their UTF-8 content enters the
prompt; a larger individual memory is skipped. The builder verifies each returned
memory's owner again before assembly. Memory/profile content is serialized as
supplementary USER data; the reviewed card and complete opening enter the SYSTEM
roleplay block described above. Creator notes, raw import metadata, WorldTruth,
hidden events, other worlds, and other Characters' private memories are not added.
Knowledge assertions are not yet retrieved. The current-world profile is explicitly
given precedence over the general description. A confirmed card replacement updates
later roleplay input without rewriting conversation history or resetting the scene.
The builder prepares input only; it does not dispatch a model or authorize any
new knowledge.

The persisted transcript remains complete. Prompt assembly always includes the
current Player send, then retains the most recent complete prior turns while
staying within 32 messages and 96 KiB of message text. Delayed replies may
interleave with later sends; selection groups records by durable turn identity
and restores message position order in the prompt. The first older turn that
cannot fit ends the history window. This bounded window is only a prompt view;
it does not delete or summarize stored messages or weaken the physical-attempt
Token preflight.

The prompt reader scans backward by durable message position until it has the
current turn and at most 32 distinct previous turns. It then loads those complete
turns within the same visibility cutoff and applies the existing message/byte
window unchanged. For a group turn already in progress, its committed replies
remain visible even if newer unrelated messages have since been appended. Older
history is not materialized in Python merely to discard it during prompt assembly.

The player-facing direct and group transcript now reads bounded, owner-scoped
pages of at most 50 messages. The newest page is ordered by durable per-conversation
position, and `before_position` loads older records strictly before the oldest
displayed position. The `next_before_position` cursor is absent at the beginning
of history. This position cursor remains stable if new messages are appended
while older history is being read. The previous complete-list endpoint remains
available for compatibility; UI pagination does not change which turns the
Character sees or promote dialogue into WorldEvent/Knowledge/Memory.

## Earlier dialogue recall

Production direct/group reply builders also retrieve bounded older quotes from
their current authorized conversation. They resolve the selected World, Player
and Character/fixed group membership before invoking the shared recall service.
It reuses the existing owner-scoped SQL message pager strictly before the earliest
recent-window position. At most three pages of 100 records and 512 KiB of text
are processed. Oversized individual quotes and turns already represented in the
recent window are skipped; no future or another conversation's records are ranked.

The current Player text's last 1,024 characters supplies at most 24 jieba search
terms. SQLite FTS5 ranks an ephemeral, authorized-only corpus by its own BM25.
This is lexical recall, with no embedding, synonym expansion or global private
corpus statistics. Segmentation/ranking runs off the event loop, with two worker
slots. No durable retrieval index, chat-text cache or new database schema is added.

Up to four original messages, with at most 8 KiB of UTF-8 text combined, enter an
optional `earlier_dialogue_quotes` lower-trust USER field. Each carries its source
Message, Conversation, sender identity/type, position and UTC time. The builder
also labels the sender with the current accepted Character name or world-first
Player profile name, so earlier Player/Character statements are distinguishable.
Quotes can be incomplete,
contradictory or later corrected; fixed system guidance forbids inventing memories
or promoting quotes to facts. Selection does not form Observation, Knowledge or
EpisodicMemory, and does not expand worldbook activation. The existing complete
recent-turn window, group exposure window and physical-attempt Token preflight
remain in force. The group speaker selector does not use this additional recall.
See the [component decision](../research/2026-09-28-chat-recall-reuse.md).

## Chat request feedback

The client retains only bounded machine labels from the existing FastAPI `detail`
response and maps recognized failures to predefined Chinese messages. It does
not display arbitrary server detail. Saving, waiting for replies and checking
durable outcome are shown as distinct UI phases. A status-query failure does not
turn into a generation retry.

The player may check the recent player message's direct/group turn through the
existing owner-scoped GET, including after reopening the conversation. `pending`
means generation has not been claimed, `claimed` means completion is unconfirmed,
and `completed` reflects the durable outcome. These checks do not claim work or
replay an uncertain provider request. Direct/group UI now uses one streaming POST:
temporary deltas display immediately and committed message events merge by durable
identity into paged history. It does not poll or reconnect to regenerate. Refresh
and status checks remain owner-scoped reads. Leaving the conversation aborts the
current request; previously saved messages remain.

Group completion currently does not persist why a turn ended. Budget exhaustion,
the reply safety cap and natural speaker STOP can all produce `completed`. The UI
therefore reports only that the turn ended, without inventing a natural stop reason.
Durable termination reasons remain subsequent work; incremental delivery is implemented below.

## Persistence boundary

Conversation and Message are durable interaction records. They are not entries in
the canonical WorldEvent ledger. A durable player-send receipt prevents an HTTP
retry from appending the same user message or repeating a completed turn. A turn
whose provider outcome is uncertain is not silently regenerated; unresolved
usage remains subject to the normal LLM accounting integrity rules.

`ChatTurnId` and `MessageId` identify committed records independently of
`RequestId`. The request identity plus a fingerprint of the resolved Player,
Conversation, text, and turn token ceiling protects the atomic player send.
Retrying the same request returns the original turn/message identities and
position; reusing it for different semantics fails. New requests append in
per-Conversation order. The initial durable status is `pending` and does not
itself trigger provider generation. The current schema stores player messages;
the sender columns hold an explicit Character identity for the validated reply
path. The internal direct-reply boundary can claim a pending turn once in
a durable `chat_turn_dispatches` row before provider work. A second or restarted
claimant cannot generate it again. A caller-provided, bounded nonblank reply
can be appended in transcript order; repeating the same completion returns
the committed message, while conflicting content fails. Claim and reply writes
are separate transactions. An interrupted claim remains unresolved without a
fabricated reply or automatic provider replay, because the provider outcome may
be unknown. The legacy `chat_turns.status = pending` field records the initial
player-send receipt; the claim and Character message establish later execution
state. The public API cannot write arbitrary Character text. The internal
direct-reply service generates and validates a reply through the governed LLM
gateway before committing it. Group replies use the analogous one-time claim,
ordered reply append, and explicit terminal completion. Neither chat path
turns dialogue into canonical world facts.

## 2026-09-28 selector output allowance

The group selector now uses up to 8,192 generated tokens, limited by the configured output cap and remaining shared turn allowance, instead of a fixed 64-token cap that could truncate reasoning before the speaker ID. Initial and subsequent selection share one complete-response decoder and validate exactly one eligible Character or a permitted terminal STOP. Bounded scalar/one-field JSON/code-block wrapping is normalized; partial output and ambiguous/foreign IDs remain rejected. Safe UI errors distinguish selection from final dialogue validation. This adds no replay, retry, schema, Director or knowledge changes. See [reuse and diagnosis](../research/2026-09-28-group-selector-fix.md).

## 2026-09-29 native OpenAI input counts

Direct OpenAI Responses text requests can now reuse the official complete-input count endpoint before claiming/generating, instead of reserving the full model context for short messages. Optional async preparation precedes every governed physical attempt and stays outside the accounting transaction; synchronous budget/turn reservations share the prepared count. Existing invocation deadlines and unknown-dispatch handling are retained. Unsupported shapes/endpoints, count failure or stale cache revert to trusted model limits. Claude's estimated counter and Gemini Interactions mapping are not yet authorized hard bounds. See the [provider review](../research/2026-09-29-provider-input-preflight.md) for scope, privacy, continuity assumptions and verification limits.


## 2026-09-29 incremental dialogue delivery

Authenticated reply/stream POST routes supplement existing JSON generation. Temporary
speaker text is not persisted or exposed to other characters/memory. Governed terminal
settlement and dialogue validation precede commit. Internal group selection and every
reply share the same hard ceiling and financial guard. Failed streams never replay as
nonstream calls. Stop/unmount propagates cancellation with shielded iterator cleanup;
claimed interrupted turns stay unresolved, with read-only status reconciliation.

An explicit managed-model setting declares streaming capability/profile consistently;
old settings remain unchanged until saved. Actual DeepSeek framing and native OpenAI
input-count projection now include streaming. Other provider bounds retain fallback.
See [sources, event contract, limits and pending acceptance](../research/2026-09-29-chat-streaming-reuse.md).

## 2026-09-29 player-visible dialogue recall

Direct/group chat now offer local history keyword search, source timestamps/positions,
up to seven contextual messages, and quotation into the editable composer. The new
search route uses the same owner-authorized message page and FTS5/jieba ranker; it
never reads Character-private memories or initiates generation. Each batch processes
at most 100 messages/512 KiB and returns up to eight matches/32 KiB; the UI can scan
older pages, keeping at most 64 results. This is a bounded keyword recall browser,
not a trace of the last model's context or automatic episodic-memory formation.
Existing prompt recall limits, private owner binding, write semantics and financial
controls remain unchanged. See [sources, limits and acceptance](../research/2026-09-29-chat-recall-view-reuse.md).


## 2026-09-29 reviewed conversation summary

Direct/group chat has a separate, persistent conversation summary. It is a
Player-owned interaction record for the same fixed shared conversation, not a
Character's private EpisodicMemory or new Knowledge/WorldTruth. Summary prompts
use only the previous confirmed revision and the next contiguous source batch
(up to32 whole messages/96KiB body). Generation reuses the governed authoring
operation and existing configured model, independent of the chat-turn ceiling.

Manual Draft → editable Preview → hash-bound Commit uses durable single-dispatch
UUID claims and BEGIN IMMEDIATE CAS. Repeated acceptance returns its existing
revision; stale bases cannot overwrite current memory. Each new version keeps
its base and up to32 new source IDs. User corrections append versions without
model calls; raw dialogue and previous versions remain. Draft recovery reads
state without replay. Only the latest draft is shown by the ordinary UI; older
draft receipts are retained, not browsable as a draft history in this slice.

Only confirmed summaries whose covered position is strictly before the current
player message enter a character reply's lower-trust USER data. World, current
Player, Conversation and fixed membership are checked before reading summary
content. Group selection remains unchanged. Summary content is not proof of a
source claim; current dialogue/corrections take precedence. Context includes
8KiB at most for this summary in addition to existing bounded inputs, within the
same governed reply reservations. No cross-conversation propagation, automatic
memory formation/forgetting, private memory expansion or canonical writes.
See [reuse decision and acceptance limits](../research/2026-09-29-conversation-summary-reuse.md).


## 2026-09-29 character-owned event observations

Direct/group replies additionally read the speaking Character's own witnessed,
event_occurrence event-target Observations. SQL binds World + Character before
selecting supported v1 event references. Up to12 recent supported events/8KiB
serialized data enter lower-trust USER context; current world entity names are
bounded readable labels, not historic snapshots. No player's event feed or
other member's private observations enter this input. Group selection is unchanged.

PlayerMoved, PlayerPlaced, CharacterPlaced and CharacterRoutineStarted v1 have deterministic templates;
unknown versions, invalid references and ordinary/legacy observations do not
supply descriptions. This is event-time access, not automatic KnowledgeAssertion,
Memory, Truth, or proof that the Character already told the player. Snapshot is
read at prompt assembly, not reconstructed as-of a historical message. Normal
reply reservations/financial governance include this input; no extra model call.
See [reuse and limits](../research/2026-09-29-observed-events-reuse.md).

## 离线主动消息

0027增加ChatTurn.kind（旧数据默认player，主动消息为outreach）和可空ChatMessage.story_sent_at_utc。outreach没有伪造的Player消息，也不能由玩家reply/turn入口重新派发；独立恢复receipt控制一次生成，消息/完成记录原子提交。turn.token_ceiling记录两次有限任务的可信上界之和，实际费用仍来自独立LLMledger。created_at_utc永远真实，story字段仅呈现离线剧情时间。持久position和旧历史不重排；普通回复字段为空，兼容旧客户端。已读只改变恢复回执，不赋予WorldTruth/Knowledge。

## 角色自身活动进入聊天（2026-10-01）

私聊和群聊回复现在读取当前发言角色自己的最新真实活动开始，并结合现有有效WorldTime与自身状态快照区分：原定活动时段内、原定时段已过、自身状态已变化。来源必须是同世界、该角色自己的witnessed/event_occurrence观察，且事件主体是自己；从Kernel已提交的CharacterRoutineStarted v1取白名单标量，不读取Director输入、未来候选或其他角色状态。缺少来源不猜测活动。角色自己的最新开始独立读取，不会因12条近期观察全部被其他亲历事件占满而丢失。

当前活动判断要求自身revision与地点仍对应这次开始，并且当前WorldTime早于事件中的planned_until。结束时段只释放占用，不表示完成了任务、取得成果或改变关系；状态变化后不把旧开始当现在。经过时间是世界分钟，不转换成现实日期；暂停世界不按现实时间产生进度。

这段最多2KiB的临时情境只提供给该角色的回复，私聊放在当前问题前，群聊附在该发言者的资料中；群聊选人不读它。没有新的模型任务、UI全知活动面板、自动Memory/Knowledge写入或迁移。对话可以自然提及自己实际开始过的活动，但消息本身不把玩家标成目击者。现有亲历事件输入和“聊聊这件事”入口继续复用。

只做静态检查和编译打包，实际模型是否自然、准确使用这些信息仍由用户体验验收。见[调查与实现边界](../research/2026-10-01-activity-chat-context-reuse.md)。

## 活动回答的主体对应（2026-10-01，桌面0.1.4）

用户明确要求回答对应角色自身活动。本轮在现有已授权事件投影中增加内部subject身份；角色上下文标识实际主体subject_kind/subject_id，以及actor（本人行动）或witness（目击他人）。缺少可信标记时不能认定是自己的经历。角色名称相同、角色卡改名也不改变对应的主体ID。玩家事件HTTP仍手动返回原白名单字段，不新增内部身份字段或改变知情范围。

自身快照增加speaker_character_id、actor_character_id和受限RoutineActivity枚举，另复核事件subject等于当前发言者；缺少对应身份或合法活动类型时仅保留时钟，不把事件交作本人活动。已有阶段/revision/地点/时间判定继续保留。本人活动上限2KiB、观察上限12条/8KiB均包括新字段的实际序列化字节。

私聊角色资料也提供稳定ID；私聊/群聊共用同一段活动约束：近况以自身记录为依据，休息/工作/自由活动不能任意互换，不从角色卡惯常行为、公共背景或别人台词补造本人的任务、同行者、成果或地点。角色仍可自然表达感受与想法；世界暂停、时段已过、状态改变、无记录不能伪造进度。群聊selector不读取这些私人观察。

本轮加强的是受控输入的身份与活动类型对应和共用回复规则，既有回复校验仍只验证调用/完成/字节/预算等完整性。没有新增自然语言语义裁判或宣称完全消除幻觉，没有固定话术替换台词或按关键词拒绝回复。无新依赖、表/迁移、后台任务、额外模型调用。实际角色是否准确使用资料由用户体验验收。见[复用调查](../research/2026-10-01-activity-identity-reuse.md)。


## 长期聊天记忆与活动生命周期（2026-10-02，桌面0.1.7）

同次JSON在reply/events后附memories，本地最多4条且验证原句，无效元数据忽略、不额外付费修复。完成回复事务同时保存应用记忆，按参与者隔离；旧记忆明确更正形成superseded来源链。当前绑定玩家可查看自己的共同对话记忆，不开放私有EpisodicMemory。相关原句跨该角色固定参与过的会话有界召回；新store存在时替代提示中旧近三页召回，避免重复输入和停用旁路。selector不消费私人记忆。活动快照改为最多6KiB，加入终止阶段及6条本人近期经历；Witness仍不能说成Actor。时段结束不表示成果，既有completed/预算校验不充当自然语言语义裁判。详见[说明](../LONG_TERM_MEMORY.md)。

## 显式回复恢复与记忆可靠性（2026-10-03，桌面0.1.17）

用户批准latest/no-character-reply的独立付费新尝试，见[方案](../proposals/2026-10-03-reply-recovery.md)。pending保留原领取/原额度；已记录校验失败或可靠本地中断可由用户确认当前额度创建retry Turn，source_turn_id关联原Player Turn，不复制Player ChatMessage。每attempt仍一次claim，内部选人/路由/发言共享其预算；原用量不重置。running/unknown与部分群聊不重放，legacy claimed没有执行结束记录时按unknown。创建CAS与领取/完成都核对来源及当前attempt，HTTP认证与当前玩家绑定沿用。

0031新增chat_reply_executions与chat_reply_recoveries，不重写旧ChatTurn。执行失败只持久固定状态，保留原网关结算/预留；启动将仍running的本地工作标为interrupted，不自动调用模型、unknown不改。原源消息仍是真实来源，群聊仅在提示组装时把源问题归到当前尝试，事件/记忆落库继续本地原句和权限校验。前端幂等准备/读回与显式生成复用原stream路径；草稿保持，刷新只有GET。

长期记忆核心分桶、关键词多查询RRF、明确更新且同主题补充共存，16条/8KiB和4原句/8KiB上限不变。现有jieba/SQLite/SQLAlchemy直接复用；不增加embedding或模型调用。详见[复用记录](../research/2026-10-03-memory-recovery-reuse.md)及[用户体验](../CHAT_FUNCTIONAL_EXPERIENCE.md)。

恢复后的历史回复在提示层归到原问题，并有界补入其真实源问题，继续按完整回合裁剪，防止只留下回复。当前群聊尝试仍按当前尝试聚合；实际存档、消息ID、原句及时间不改，普通历史/原文读取保持真实attempt ID。


## 本地持久召回（2026-10-03，桌面0.1.20）

沿用现有FTS/FastEmbed/NumPy和角色权限边界，集成DiskCache5.6.3作为可重建派生缓存。每通道读取最多8192条SQL授权后的源ID/版本，使用已缓存向量排序，再读回命中正文及64条待编码历史页；最近与关键词候选仍独立保留。新候选每通道最多128条编码，只有显式聊天/搜索触发，外发上限、Kernel真值、主库及Alembic结构不变。

缓存键包括模型/编码规则、world/player/character、源ID和记忆版本；缓存不承载权限，失效或遗忘来源不得参与排名。向量和摘要存于app-data/data/cache/chat-recall-v2，目标256MiB，按写入顺序淘汰，不复制正文、不使用pickle；内存LRU4096条，查询向量只在内存中复用。磁盘失败回退内存且说明，模型失败回退关键词。大规模耗时与语义质量待验收。详见[复用调查](../research/2026-10-03-persistent-recall-reuse.md)及[体验说明](../CONTEXT_AND_RECALL.md)。

## Bounded original-message source view (0.1.27)

Authenticated GET `/worlds/{world_id}/conversations/{conversation_id}/messages/{message_id}/source` resolves a stable MessageId under the selected local Player and owned original conversation before reading text. It returns the existing message-page DTO, at most the target and three positions on each side, ordered by position, without a pagination cursor. The current local binding is included in both source and body queries. Foreign, missing or inaccessible sources have the same fixed 404 label; missing Player selection is 409. No history search, semantic model, message/knowledge/world write, model dispatch or read-mark mutation occurs. The UI cancels obsolete reads, preserves the saved quote and editing state, reuses ChatMessageBody/MessageTime, and reads the source conversation rather than the currently open conversation.


## Source-linked experience state recall (0.1.28)

Owner/world/event-time authorization still precedes projection and ranking. Within at most 128 authorized v1 observations, a unique terminal and its known start may group by stable start_event_id, event family, subjects, WorldTime and ledger order. The existing FTS ranker searches both descriptions but returns only the actual terminal projection, ID and time. Recent slots count distinct groups; the model receives at most12 actual events/8KiB. Missing/conflicting links remain separate, with no global/out-of-window completion lookup. HTTP DTOs, raw facts and migration0034 remain unchanged. See [guide](../EXPERIENCE_STATE_RECALL.md).
