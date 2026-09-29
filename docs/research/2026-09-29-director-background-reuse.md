# Director 公共世界书背景：复用调查与实现范围

2026-09-29；基线2a44262。用户授权继续推进，本轮将已经接受且逐条公开的世界书接到日常规划，不扩展角色动作或模型费用授权。

## 已核对成熟实现

- [SillyTavern 1.19.0 package.json](https://raw.githubusercontent.com/SillyTavern/SillyTavern/1.19.0/package.json)，版本1.19.0、AGPL-3.0；[官方World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)提供常驻/关键词、次级条件、上下文容量与生成类型限制。quiet 表示后台生成，不能把仅normal触发的条目随意用于后台任务。它的完整扫描器依赖酒馆宿主，上一轮已核对；本轮直接复用当前Python激活器，新增quiet参数，保留normal默认。没有复制酒馆源码或部署另一套宿主。
- [Generative Agents plan.py](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/reverie/backend_server/persona/cognitive_modules/plan.py)，当日main、未固定发行版；[Apache-2.0](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/LICENSE)。它依据persona与环境生成日程，但依赖maze、scratch和多次模型分解。参考已有背景参与规划的思路，不引入完整模拟器，不增加逐条模型调用。
- 现有SQLite JSON1/SQLAlchemy能够先按World、accepted当前版本和逐条公开记录筛选，再投影所需字段；现有激活/排序/容量逻辑可以直接提取为共享函数。不增加依赖、数据库表、迁移、provider客户端、RAG或另一套运行时。

用户随后明确授权：把当前世界已确认、逐条公开的世界书标题与正文发送给当前配置模型服务，用于已开启的Director日常规划；隐藏条目、私聊、私人记忆不发送。此前自动审批两次拒绝这项数据流，具体授权后继续，未绕过审批。

## 具体切片

1. 本世界当前accepted的lorebook条目，明确公开且enabled后才投影。只读title/content、关键词、排序与激活条件；不材料化整本snapshot、原始source_book、角色内嵌暗线或私聊/记忆。
2. planner用一段角色名称和各自当前地点名称作为扫描上下文，无聊天历史扫描、persona文本扫描、递归或向量调用。常驻无需命中；关键词/次级条件、大小写/完整单词、scanDepth零和未支持配置仍由同一激活器决定。明确triggers时必须包含quiet；聊天仍要求normal。
3. 复用聊天已有排序与最多16条、title/content共12KiB的选择上限。规划授权候选元数据有界：最多512条公开启用条目，每条关键词/条件等投影16KiB；超过停止并显示容量错误，模型不dispatch。过大正文按既有背景预算跳过，必要角色/地点资料不被省略，完整planner输入仍限制64KiB。
4. 选入背景以lower-trust USER数据参与下一次常规批量规划；来源ID保留用于检查。读取/公开切换不触发新模型调用，不改变6小时/至少2条且50%失效的规则。已经开始的计划不重写历史；新公开内容等到下一批。
5. dispatch之前和接纳返回计划之前复核选入条目的公开授权及当前accepted版本；已隐藏/更新则停止该任务，不自动重放付费请求。已经提交的基础动作不因后来隐藏背景撤销。
6. 世界书素材仍不成为WorldTruth，不自动创建地点、事件、关系或角色知识；候选只能提交原有rest/work/leisure及已存在地点。真实质量由用户体验验收。
