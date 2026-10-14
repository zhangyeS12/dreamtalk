# SillyTavern本地配音接法与dreamtalk差异

日期：2026-10-13。用户要求查看酒馆如何调用本地模型及本项目反复出现配音问题的原因；按当前对话的本地配音范围审查。仅查看公开源码和本项目代码，未安装酒馆或新模型、运行声音／测试、读取真实聊天或音频、修改应用行为／版本、重打包或发布。

## 固定来源与复用边界

| 来源 | 本轮核对的版本／提交 | 许可及取舍 |
| --- | --- | --- |
| [SillyTavern官方release源码](https://github.com/SillyTavern/SillyTavern/tree/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/extensions/tts) | package.json 1.19.0；06bde939fb1e9c4c8d8641d810f0a916b5bce127 | AGPL-3.0；只参考协议和职责边界，不复制适配器／播放器源码进本仓库 |
| [官方XTTS文档](https://docs.sillytavern.app/extensions/xtts/)链接的[XTTS API Server](https://github.com/daswer123/xtts-api-server/tree/5e8bc93d674fed0f5849e03db28f5e5216320d99) | pyproject.toml 0.9.0；5e8bc93d674fed0f5849e03db28f5e5216320d99 | 服务代码MIT；只研究调用／音色编码缓存，没有集成或安装。XTTS-v2权重另有[Coqui Public Model License](https://huggingface.co/coqui/XTTS-v2)，不与服务许可混同 |
| [当前IndexTTS官方推理](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/indextts/infer_v2_5.py) | 本机已部署d9e41aac89fd00b3d71497fddb287b7f24613712 | 沿原Bilibili Model Use License独立环境，本轮不改官方代码／权重 |

只读资料放在Git忽略的`artifacts/research-tavern-tts/`，snapshot.json记录提交、来源URL和摘要；本轮未执行下载代码，也未把它们加入产品依赖或打包载荷。

## 酒馆实际怎样调用

[官方TTS说明](https://docs.sillytavern.app/extensions/tts/)将配音视为可选provider。当前内置列表没有专门的IndexTTS2.5适配器，但有OpenAI-compatible／TTS-WebUI及其他后端接法；不能据此说酒馆无法使用第三方IndexTTS服务，也不能把XTTS表现当成IndexTTS对照实测。

[XTTS适配器](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/extensions/tts/xtts.js)将台词、speaker_wav音色标识和语言POST到独立服务的`/tts_to_audio/`；推理参数通过`/set_tts_settings`交给服务，默认enable_text_splitting=true。可选流式模式改用`/tts_stream`，不是所有路线默认流式。

[AllTalk适配器](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/extensions/tts/alltalk.js)提交文本／音色／语言到`/api/tts-generate`，然后读取返回的音频URL；可选流式有另一个入口。酒馆本身不在这些适配器中运行Torch或设定IndexTTS的文本／语音Token容量。

[配音入口](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/extensions/tts/index.js)区分生成队列与播放队列，接收音频Response、URL或异步音频块；有可选按段落排队，不能说默认按每个句号切分。收到音频时检查MIME，播放完成按原生ended推进；不检查IndexTTS的结束Token或台词语义完整性。重置前端队列本身也不能证明外部服务的推理已取消。

## 能解释现有问题的具体差异

| 项目 | 代码中的实际差异 | 可作出的判断 |
| --- | --- | --- |
| 参考音色缓存 | XTTS服务[按speaker_name缓存参考编码](https://github.com/daswer123/xtts-api-server/blob/5e8bc93d674fed0f5849e03db28f5e5216320d99/xtts_api_server/tts_funcs.py#L257)。本项目`serve-indextts.py`每次创建新的TemporaryDirectory和参考路径；IndexTTS原生缓存用参考路径判断是否复用 | 同一音色在本项目每次新生成时会重复做参考编码，原生说话人／情绪参考缓存未有效复用。这是确定的效率缺口；未测量耗时占比，不把它当成缺句的根因 |
| 分段与推理 | XTTS默认允许服务分句；本项目按用户确认的3候选／文本实际容量内整段合并，覆盖IndexTTS split_text_by_tokens并绕过低显存infer外层40字符切分 | 本地调用已非原样官方入口。输入600／输出1815是不同容量；但两种模型不同、63字符也可能在XTTS里只是一段，不能证明单靠缩段就能修复本次异常 |
| 首音等待 | 酒馆生成／播放队列独立，部分服务可以流式；本项目依次等待全音频生成、下载、校验、缓存保存再播放，当前队列也等本条播放结束后继续下一条 | 当前首音和多消息等待的边界较长。流式只改善可用时间，不能保证解码完整；本轮未开启流式或增加并行推理 |
| 接入生命周期 | 酒馆通常连接用户预先启动的独立服务；本项目增加Tauri监督、桥接版本／端口核对、Core任务和缓存候选事务 | 有更多状态边界需要治理。此前旧服务／端口、桌面Blob播放权限属于本项目接线问题；六小时缓存、费用回执和明确替换是已批准功能，不能为简化删掉 |

### 确定的参考缓存缺口

当前`IndexTTS2`在`cache_spk_audio_prompt != spk_audio_prompt`时重新计算说话人条件、声学参考和风格；情绪参考也按路径判断。桥接每次成功／失败尝试使用不同临时路径，即使参考音频内容未变，也不会命中上一请求缓存。模型实例确实跨任务保留，但保留实例不等于复用了音色编码。此结论来自源码，无需读取用户音频；音色缓存与六小时输出声音缓存是两种不同缓存。

## 对当前故障的结论

此前Blob权限缺口已有[独立修复证据](../maintenance/2026-10-12-speech-playback-fix.md)；旧配音服务处理见[已授权处理记录](../maintenance/2026-10-12-legacy-speech-service-stop.md)。这些集成问题应由本项目承担，不能笼统归因硬件。

当前speech_audio_incomplete仍是IndexTTS语音解码末尾没有正常结束Token后的长度警告→桥接失败→原缓存保留，见[本轮审查](../maintenance/2026-10-13-speech-incomplete-review.md)。为何未结束尚未通过本次任务的输入／输出Token计数和音频证据确认。泛用酒馆前端不会改变同一个后端的解码行为，也不能仅靠音频可播放判断全部台词完整。

本轮确认可参考成熟服务的稳定音色身份、条件编码缓存、生成／播放职责分离与协议适配；没有决定更换模型、加入酒馆运行依赖、复制AGPL代码、改变已确认整段策略或新增自动重试。当前先按已定位缺口及获准诊断继续，不把未验证参数调整写成已解决。

## 核对范围

本项目仍为源码／本地包0.1.65、API协议1、迁移0047及桥接revision 5；公开0.1.53与Git HEAD a3f2183保持。本轮仅源码研究与当前文档更新，未提交／发布，既有未提交改动保留；0.1.65包内仍为2026-10-12构建快照。文档链接、Git差异格式与已知隐私特征检查另记本轮实际结果；源码比较不等于声音／性能实测。

本轮文档链接1036个本地目标／0断链，Git差异格式通过；源码隐私门禁862份文件／0已知特征命中。没有运行自动测试、服务或声音，没有实测缓存节省时间，也没有进行两种模型同录音／同台词的声音比较。

## 后续已授权实现

用户随后要求按本研究优化，0.1.66落实参考编码缓存身份、解码数值日志和失败操作提示，见[实施记录](../maintenance/2026-10-13-speech-reference-cache-fix.md)。上面的0.1.65差异和检查属于研究时快照；后续实现不表示已测得声音／性能效果。
