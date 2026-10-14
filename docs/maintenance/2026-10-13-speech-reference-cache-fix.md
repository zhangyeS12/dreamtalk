# 参考酒馆接法改善本地配音（2026-10-13）

用户明确要求“参考酒馆的实现优化”。本轮Desktop源码0.1.66、API协议1、本地桥接revision 6，Alembic head保持0047_speech_preview；公开0.1.53／Git HEAD a3f2183保持，未提交或发布。

## 具体缺口与实现

1. 上轮[源码比较](../research/2026-10-13-sillytavern-local-tts-comparison.md)确认：每次生成创建新的临时参考路径，官方IndexTTS按路径识别说话人／情绪条件缓存，同一录音也重复编码。本轮用模型实例、参考字节SHA-256及格式识别连续相同参考；只有原生缓存路径仍对应上次请求、全部相关条件张量存在时，才将缓存身份绑定到本次临时路径。参考变化、模型变化、缓存不完整或上游字段不可用时沿原逻辑重新编码。没有新增磁盘音色缓存或额外张量缓存，录音／输出临时文件仍在每次调用结束后删除。哈希及文件路径不写日志。
2. 在官方GPT解码方法外加临时数值观察，原方法只调用一次、参数及返回值保持。记录每段实际归一化输入Token数、输出Token数、结束标记、解码耗时、候选数及配置容量；不记录Token值、台词、参考录音或声音。成功／失败均恢复原方法；诊断结果形状不兼容时保留原结果并输出固定不可用提示。未正常结束的官方长度警告仍阻止保存／播放，不靠删除判定把异常结果当成完整声音。
3. 全局及消息下方失败提示按操作区分。重新配音／候选失败建议点击“重新配音”，并说明原配音未替换；普通生成失败建议“播放配音”。候选过期提示也使用正确动作，避免原缓存有效时误导用户点击普通播放去重新生成。
4. Tauri与Core要求revision 6，避免新包继续复用缺少本轮优化的旧桥接。协议2、现有端口／凭据／单任务门禁及费用回执不变。官方模型代码、权重、精度、系统入口与真实存档未修改。

保持用户确认的3候选、归一化后按实际输入容量合并完整句、超过容量才向前寻找最近句号；仅单句超过物理容量使用原tokenizer回退。输出长度仍读取官方模型实际容量，无额外较低Token阈值。6小时输出缓存、手动重新生成、下方完整试听及明确替换／保留沿用0.1.65。

## 成熟实现来源、许可与取舍

参考SillyTavern 1.19.0固定提交06bde939fb1e9c4c8d8641d810f0a916b5bce127的[XTTS适配器](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/extensions/tts/xtts.js)，及其文档推荐的XTTS API Server 0.9.0固定提交5e8bc93d674fed0f5849e03db28f5e5216320d99的[按音色复用条件编码](https://github.com/daswer123/xtts-api-server/blob/5e8bc93d674fed0f5849e03db28f5e5216320d99/xtts_api_server/tts_funcs.py#L257)。酒馆AGPL-3.0、XTTS服务MIT、XTTS模型权重另有CPML；本轮参考稳定音色身份与职责边界，不复制／并入其源码或权重，不新增运行依赖。

实际复用已部署IndexTTS官方d9e41aac89fd00b3d71497fddb287b7f24613712的[原生单音色缓存与完整声音生成](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/indextts/infer_v2_5.py)。桥接只适配缓存身份和观察解码数值，维护成本限定在已有版本核对；不更换模型、调整已确认分段／候选策略、启用流式或并行模型调用。不同模型不能直接套用参数或据此宣称声音效果相同。

## 接手入口与完成条件

`scripts/serve-indextts.py`的ReferenceIdentity／decode_diagnostics及infer接线；`infrastructure/speech_providers.py`和Tauri `local_speech.rs`的桥接版本门禁；前端`SpeechPlayback.tsx`的按操作反馈。没有新迁移或API契约变更。

待用户在新版验收：连续使用同一参考时数值日志speaker_hit／emotion_hit为True；切换录音后不误用旧条件；任务日志包含实际输入／输出计数及ended；重新配音失败后提示正确、原缓存仍可播放。首次加载、参考编码、GPT解码和声学／声码器耗时需分别记录，缓存复用的实际节省尚未测量。“第一句后无声”及未正常结束的根因仍未确认，本轮不登记为已解决。

## 检查与交付

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；完整构建退出0；EXE文件／产品版本0.1.66，包内285份Core源码及桥接逐字节一致。已交付入口 `artifacts/portable/voices-0166/dreamtalk/dreamtalk-desktop.exe`；使用既有`--build-only`，日志为artifacts/build-voices-0166.log，交付摘要为artifacts/voices-0166-delivery.json。

没有运行测试／smoke、启动应用／服务、调用模型、读取用户台词／声音、操作真实存档或真实迁移。静态数值日志接线不代表已经取得新版任务数据；检查与构建不代表声音／性能验收。保留工作区既有未提交改动，未提交／推送／发布。

本轮构建保留可选tzdata／pysqlite2／MySQLdb隐藏导入缺失、Vite大分块和Tauri STATIC_VCRUNTIME弃用警告；不以这些警告推断配音故障。文档链接及源码／载荷已知隐私特征检查、清单哈希和源码一致性另记交付摘要。启动新版前由用户完全退出旧应用，让新版使用revision 6；工程端不终止外部进程或代为启动服务。
