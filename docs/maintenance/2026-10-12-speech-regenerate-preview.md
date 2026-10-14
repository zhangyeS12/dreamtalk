# 重新配音、试听与替换（2026-10-12）

用户明确要求在“播放配音”旁新增“重新配音”，调用模型重新生成，完成后在消息下方播放；播放结束必须选择是否替换此前配音。本轮源码Desktop 0.1.65，API协议1、本地桥接revision 5；新增Alembic head `0047_speech_preview`。公开版本仍为0.1.53，Git HEAD仍a3f2183；本轮未提交或发布。

## 已实现

- 私聊和群聊角色消息旁并列“播放配音 / 重新配音”。播放沿用有效缓存；重新配音明确创建独立新请求，使用原持久台词、当前音色和所选路线。每次新生成计入既有次数／额度／费用，保持远程与付费同意门禁、单任务生成、字数与内存容量限制，没有自动切换路线或重试。
- 重新生成的声音是待确认候选，不参与普通缓存查找。原缓存不在生成或试听时被覆盖；新声音完成后在消息下方提供“试听新配音”，播放器实际播放结束后才出现“替换之前的配音 / 保留之前的配音”。中途停止、失焦、切页或播放错误不产生试听完成确认。
- 替换和保留由认证API与短数据库事务处理，检查当前世界、玩家、原消息、候选状态、试听完成回执及缓存版本。替换仅改变对应台词／音色／路线的缓存并清除原音频；保留则清除候选音频。两个决定都保留独立调用回执；相同决定的重复提交幂等，相反或过时决定拒绝覆盖。
- 候选和原缓存都从各自成功保存时起保留6小时，重播和确认不续期。未选择不会自动替换；返回会话时只查询已保存候选，不重新调用模型。过期或失败后可以人工再次重新配音。模型任务未知／中断仍不自动重放。
- 256MiB缓存治理保护尚在生成／待确认的候选及其原缓存；无法腾出空间时新声音保存失败，不抢先覆盖原声音。自然六小时过期仍执行。每次候选查询最多128条消息，只返回元数据；前端候选元数据最多256条，音频播放器仍使用并及时释放单个Blob。

“播放结束”是浏览器原生`ended`事件及客户端完成回执，不是语义完整性或用户确实听到全部台词的认证。生成声音本身是否缺句仍需诊断；本功能不把此前“第一句后无声”登记为已解决。保持3个解码候选、模型容量内合并完整句及超容量在最近句号拆分，不改模型／权重／精度／系统入口。

## 接线与持久化

UI：`apps/web/src/SpeechPlayback.tsx`共享生成／播放队列、候选状态与选择；`ChatTranscript.tsx`和`GroupChat.tsx`加载可见消息候选，沿用`speech.css`与当前深蓝灰主题。

API client：`packages/api-client/src/index.ts`新增重新生成、候选元数据查询、试听完成与选择接口。HTTP：`adapters/http/speech.py`新增对应认证路由；Core：`application/speech.py`继续验证持久角色消息和音色，仅人工重新生成跳过正常缓存复用。

Store：`infrastructure/persistence/speech.py`区分普通／已接纳缓存与pending候选，原子检查基准job、试听回执与决定；`speech_models.py`增加`review_state/base_job_id/previewed_at`与有界查找索引。0047只新增可空列和索引，0046及更早存档的预迁移形状核对随线性迁移链更新，旧音频／时间／请求回执不改写。本轮没有对真实存档执行迁移。

## 成熟实现取舍

参考[WHATWG媒体事件标准](https://html.spec.whatwg.org/multipage/media.html#event-media-ended)（2026-10-12 Living Standard，版权条款见[官方IPR政策](https://whatwg.org/ipr-policy#copyrights)），复用现有HTMLAudioElement及`ended`行为，不复制或分发标准／第三方播放器代码。候选采用现有产品Draft → Preview → Commit的显式确认思路；音频仍走已有Blob播放与CSP修复，不新增播放器框架。

沿用锁定SQLAlchemy 2.0.54／Alembic 1.20.0（MIT），参考[Alembic可空列增量迁移](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.add_column)。复用现有持久任务、幂等请求和费用回执；不引入新的存储服务、依赖或音频处理库。

## 交付与验收

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；完整构建退出0；EXE文件／产品版本0.1.65，包内285份Core源码及桥接逐字节一致。已交付入口 `artifacts/portable/voices-0165/dreamtalk/dreamtalk-desktop.exe`，打包用既有`--build-only`；没有启动应用、读取真实配音正文、试听、转写、调用模型、运行测试／smoke或执行真实迁移。未提交／发布。

根目录文档链接1025处、包内655处均无断链；根源码隐私门禁860份文件、最终载荷1294份文件均无已知特征命中。日志`artifacts/build-voices-0165.log`和摘要`artifacts/voices-0165-delivery.json`可复核本轮构建。保留既有环境／构建警告：Python真实位置提示、jieba转义、可选tzdata／pysqlite2／MySQLdb隐藏导入缺失、Vite大分块及Tauri STATIC_VCRUNTIME弃用；构建退出0，不据此宣称运行通过。工作区既有未提交改动保持，本轮没有提交、推送或发布。

待用户验收：有原缓存时重新生成确实调用一次，普通播放仍读原声音；新声音下方完整试听后出现选择；保留后仍播放原声音，替换后普通播放使用新声音；失败／中断保留原缓存；切页／重开找回待确认状态；确认不延长六小时期限。此前完整声音及性能问题仍待用户诊断。
