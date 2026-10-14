# 本地 0.1.54 角色配音实现

日期：2026-10-11。起点为公开 v0.1.53／a3f2183 的 codex/world-archive 工作区，保留 2026-10-09 已批准但未提交的维护改动。本轮新增角色配音，没有 GitHub 发布授权，没有修改公开下载／更新频道、真实存档、当前安装或系统启动入口。

## 已实现

- 当前世界“设置 → 角色配音”：默认关闭，三种 IndexTTS 2.5 服务、密钥、字数／每日次数、动作清理、远程及费用确认。
- “通讯录 → 角色资料 → 角色音色”：WAV／MP3／.voicecard 导入、预览确认、绑定／解除、参考试听、导出、删除。绑定使用稳定卡 root UUID。
- 私聊／群聊只在流中的持久 message 事件后自动排入配音队列；流式文字片段不配音，历史加载不触发。群聊顺序播放、手动重播／停止、离开与隐藏停止、Blob URL 回收。
- 一次性持久准入回执，缓存重播不生成；失败／中断／未知状态不重放，文字流程与配音独立。全机声音缓存最多 256 MB、生成结果最大 32 MB，每条最大 2,000 字，队列 8 条。
- 原有本机凭据 vault 与私有 Core provisioning 复用。按世界登记不透明引用，禁止覆盖不属于此世界配音的既有引用；删除旧密钥成功后才移除登记，失败保留清理线索。世界删除接入配音凭据清理。
- 云端上传成功的音色按世界／凭据引用／音频 digest 复用；云副本不随本地卡或世界删除，界面告知。免费路线不接受可能使用 credits 的 PRO Token。
- 可选本地服务脚本独立运行官方模型，不打包 Torch、CUDA、权重；新增 TinyTag==2.2.1（MIT）元数据读取及许可副本。
- Alembic0045 仅追加配音表，当前迁移 head0045_character_speech；旧0044及前序 schema 校验仍按原版本范围，未执行真实迁移。

## 入口与接线

UI：SpeechSettings.tsx／CharacterVoice.tsx／SpeechPlayback.tsx；ProductApp、WorldContent、useChatReplyWorkflow、ChatTranscript、GroupChat 接线。API client 增加严格世界路径和认证请求。HTTP speech.py → application/speech.py → speech_cards／speech_providers 及 persistence/speech.py；bootstrap 创建服务并把中断任务标为未知，不派发生成。

Tauri speech_credentials.rs 使用原生安全凭据及引用登记，supervisor 启动时重新注入引用；file_exports.rs 复用受控文件选择／原子导出。scripts/serve-indextts.py 只监听 loopback、有独立 Bearer 密钥、串行加载与推理。本地使用方式见[配音手册](../CHARACTER_VOICES.md)，来源、版本与复用理由见[调查](../research/2026-10-11-character-speech.md)。

## 检查与交付口径

已完成前端 ESLint／TypeScript、网页构建、Python Ruff／字节编译及桌面 cargo check。完整便携包由 scripts/build-portable.py --build-only --output-name voices-0154 构建成功；该模式跳过原有Core smoke和cargo测试。源码隐私门禁840文件、载荷门禁1274文件均0发现，文档链接946本地目标0损坏，Git差异格式核对通过。官方演示只读公共配置核对通过。

本地入口为 artifacts/portable/voices-0154/dreamtalk/dreamtalk-desktop.exe，完整压缩包为同目录上级dreamtalk.zip；保留公开0.1.53，不清理未知在用旧程序。构建日志见Git忽略的artifacts/build-voices-0154.log。网页大chunk、STATIC_VCRUNTIME弃用、旧jieba语法、Python路径提示，以及打包器未找到可选tzdata／pysqlite2／MySQLdb的警告未导致构建失败；当前项目源码没有使用后三项。未据此推定运行速度或内存结论。最终交付同步手册后重新生成包清单和ZIP，未重新运行产品。

没有添加或运行自动测试、应用／浏览器 smoke、安装器、临时或真实数据库迁移、参考音频上传、HF／本地／付费模型生成。曾同步开发依赖时被工具移除的原有额外包，已恢复其原精确版本，没有删弱测试或 CI。

本轮源码尚未提交；版本标为本地 0.1.54，公开仍0.1.53。实际自动播放、浏览器播放许可、服务计价／配额、音色效果、迁移／跨世界与升级安全均待用户验收；新卡 JSON 格式兼容不代表旧 .voicecard 或其他平台音色包兼容。

## 后续验收

用户分别给三个角色绑定不同人声，保存配音设置后进行一次私聊和群聊，检查先有完整文字再播放、角色映射及顺序；再核对关闭／停止／切换、导出重新导入、服务失败时文字继续、缓存重播与世界隔离。工程端不会自行执行这些操作或消费额度。
