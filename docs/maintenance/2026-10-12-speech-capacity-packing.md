# 本地配音按模型容量合并整句（0.1.63）

日期：2026-10-12。用户在dreamtalk内对比本地与官方免费云端后，明确要求本地恢复3个解码候选，Token段容量使用模型最大值；整段可容纳时一次生成，超出时向前找到最近的句号，只有单句本身超容量才继续拆分。本轮仅实现与build-only交付，不运行模型、声音或自动测试，不操作真实存档／当前服务，不改官方权重、精度、系统入口或发布。

## 缺口与规则

0.1.62已取消40Token／40字符的小段阈值，但每个句号都会形成独立生成段，解码候选仍为1，不能满足本轮整段合并要求。前轮只读对照官方公开Demo源码与实际/config，确认其默认候选3、分段120Token，情绪模式仍沿参考人声；没有进行声音对比或测量新效果。

- 本地候选恢复为3。保留既有温度0.8、top_p 0.8、top_k 30、随机采样、参考人声情绪、语速与BF16；不额外启用文本情绪分析。
- 段容量取已加载模型声明的文本容量与位置嵌入可用容量的较小值，保留语言前缀和终止位置。使用官方Tokenizer实际计数，不按字符数估算；本机声明文本600、语音输出1815Token。
- 官方文本标准化、发音标记与语言处理完成后才合并。整段在容量内直接一次生成，即使有多个句号也不拆。
- 超容量时依原顺序合并完整句子，累计到容量内最后一个句号处切分，再处理剩余文本；逗号、分号或换行不提前拆开可容纳的完整句子。
- 单句本身超出实际容量才复用官方Tokenizer兜底，保留受保护发音标记；不可安全容纳则报告既有容量错误。小数点、句末闭引号／括号和无句号尾句沿用0.1.62处理。
- 非流式桥接直接复用官方完整音频生成器，避免低显存infer外层先按原始40字符拆分；内层使用同一容量策略，仍由官方生成器按段合成、保存WAV，段间默认200毫秒保持。
- 语音输出使用模型自身最大容量，不扩充权重或位置嵌入。输入可容纳不保证语音输出也可容纳；较长生成仍可能触及1815上限。长度警告继续明确失败，不保存残缺声音、不自动重试。

6小时缓存、重播不续期、人工新尝试、回执／次数／费用／权限保持。旧有效缓存照常播放，不因升级清空或重新生成；新任务采用本轮策略。3个候选可能增加推理耗时；减少段数也可能减少衔接，但未测量整体效果或性能。

## 实现与复用

[桥接](../../scripts/serve-indextts.py)复用0.1.62句号扫描器，新增容量内整段直通和顺序合并，超长单句调用官方split_text_by_tokens。只为本地桥接实例复用官方infer_generator，不复制推理模型实现，不修改独立官方WebUI／indextts源码。数值日志标记full_stop_packed及实际容量、候选数，不记录台词或参考音频。

桥接修订5与[Core检查](../../services/core/src/livingworld/infrastructure/speech_providers.py)、[Tauri检查](../../apps/desktop/src-tauri/src/local_speech.rs)一致；旧修订不承接新生成。本轮同步已核对的本项目部署脚本，不热更新／结束现有进程。Desktop及对应锁文件0.1.63，API协议1和迁移head0046_speech_cache_attempts保持，没有新数据库或持久格式。

复用官方代码d9e41aac89fd00b3d71497fddb287b7f24613712和已部署IndexTTS2.5权重c39ce5ba981572cb187443877ff559dfb246ce63，不增加依赖。独立适配不分发权重，官方代码／模型沿用Bilibili Model Use License。来源：[官方推理与容量计算](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/indextts/infer_v2_5.py)、[模型配置](https://huggingface.co/IndexTeam/IndexTTS-2.5/blob/main/config.yaml)、[官方Demo默认参数](https://huggingface.co/spaces/IndexTeam/IndexTTS-2.5-Demo/blob/a2b37aada1fe3fad15036051a5594005e445146a/webui.py)。容量结论同时依据实际安装配置；复用官方Tokenizer／生成器优于另写计数与合成框架。

## 检查与交付

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；完整构建退出0；EXE文件／产品版本0.1.63，包内283份Core源码及桥接逐字节一致。工程端不添加／运行测试、模型、音频播放或真实迁移；未提交／发布。

构建保留既有Python解释器定位提示、Git换行提示、Vite大分包、STATIC_VCRUNTIME弃用、jieba转义及PyInstaller可选hidden import tzdata／pysqlite2／MySQLdb告警；实际日志见交付入口。这些告警没有作为声音或兼容验收通过的证据。

已交付入口 `artifacts/portable/voices-0163/dreamtalk/dreamtalk-desktop.exe`、同级dreamtalk.zip，日志／摘要为artifacts/build-voices-0163.log及artifacts/voices-0163-delivery.json。本地完整目录可直接打开程序，ZIP用于搬移。用户需从托盘退出旧dreamtalk后打开新版，应用与服务不会热更新；旧有效声音仍按6小时规则重播。

待用户验收：多个句号但总量可容纳的台词报告1段并连续生成；超容量在容量内最后一个句号切分，不跳过尾句；单句超容量才兜底，发音标记不硬切；实际声音完整性、语气衔接、3候选耗时与缓存行为。静态与构建检查不替代这些运行验收。
