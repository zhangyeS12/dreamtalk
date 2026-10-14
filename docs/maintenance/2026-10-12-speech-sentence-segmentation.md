# 本地配音按句号保留整句（0.1.62）

日期：2026-10-12。用户反馈语句中间割裂，明确要求“按照句号进行分割，一个句号算一句话，尽量不分割一个完整的话”，并补充不要额外设置Token限制。本轮只修改dreamtalk本地模型调用的分段适配、必要兼容标记与说明，build-only交付；工程端不生成声音、运行测试、操作真实存档或启动／停止当前服务。

## 缺口与已确认规则

0.1.60～0.1.61的桥接按40Token分段。核对已安装官方IndexTTS2.5后另发现低显存infer路径会先按40字符及逗号等标点拆分；因此仅把Token参数调大不足以保证整句生成。此前的截断修复确实缩短了段，用户随后报告割裂；本轮静态证据不能替代实际音频对比，也不直接证明唯一原因。

- 中文句号“。”及普通英文句点“.”形成句子边界；句号与紧随的闭引号／闭括号保留在前句。小数点不当作句号，末尾没有句号的台词也保留。
- 不再用40Token或40字符拆碎能被模型容纳的完整句子；不因逗号、分号、换行或任意较小Token数提前拆分普通句子。
- 只有完整单句超过已加载模型的实际文本位置容量，才复用官方按Token及标点的兜底拆分；受保护的发音标记不硬切。不可安全容纳时明确报告失败。
- 取消桥接额外较小的文本段阈值；不修改模型位置嵌入或伪称无限上下文。语音输出长度使用已加载模型自身声明的最大容量，覆盖原较小的1500默认值。本机配置当前声明文本600／语音1815Token，这些不是新自定门槛。
- 长度警告仍转为不完整音频失败，不保存／播放部分结果、不额外自动重试。模型自然停止也不保证每句话绝不漏读，仍需用户验收。

6小时缓存、手动新尝试、次数／字数／容量／远程费用授权、任务顺序及文字记忆边界继承0.1.61。旧有效音频缓存照常重播，不清缓存或强制重新生成；新生成音频采用本轮分段。官方WebUI及独立安装的indextts源码保持原安装版本，本轮适配只作用于dreamtalk启动的桥接实例；远程路线的内部分段由提供方管理。

## 实现与复用

[serve-indextts.py](../../scripts/serve-indextts.py)新增SentenceSegmentation适配，通过子类覆盖官方低显存字符拆分与文本Token拆分入口，保留官方显存调度、参考人声、Tokenizer、生成器、声学与声码器流程；超容量单句复用原方法，不复制模型实现。固定版本的受保护发音片段与Token长度接口继续使用。

桥接修订4与[Core适配](../../services/core/src/livingworld/infrastructure/speech_providers.py)、[Tauri检查](../../apps/desktop/src-tauri/src/local_speech.rs)同步；旧修订不承接新任务，不擅自结束外部／在途服务。单句容量失败传给[播放界面](../../apps/web/src/SpeechPlayback.tsx)，不输出台词或异常正文。数值日志标明full_stop分段、实际文本／语音容量，解码搜索仍为1，BF16、模型与权重保持。

复用官方IndexTTS代码d9e41aac89fd00b3d71497fddb287b7f24613712与本机已部署模型、标准Python子类及既有桥接；不引入新依赖。官方模型／代码继续遵守Bilibili Model Use License，项目独立适配不分发权重或复制上游实现。来源：[官方推理入口及两层拆分](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/indextts/infer_v2_5.py)、[官方模型配置](https://huggingface.co/IndexTeam/IndexTTS-2.5/blob/main/config.yaml)。固定模型版本配置页本轮网页读取失败，容量结论同时依据实际安装的config.yaml，不以网页失败推定模型不可用。

本轮同步已核对部署目录中本项目自有的serve-indextts.py，参考环境、官方WebUI／模型源码及权重保持原样；运行中的旧进程不热更新，没有启动／停止服务。

## 检查与交付

当前源码Desktop0.1.62，API协议1、迁移head0046_speech_cache_attempts保持，无数据库或持久格式改动。两份Python Ruff／格式／AST、前端ESLint／TypeScript、Rust格式已通过；构建脚本已核对采用--build-only，完整构建退出0；EXE文件／产品版本0.1.62，包内283份Core源码及桥接逐字节一致。保留既有解释器定位提示，Rust只读格式检查沿已核对的D盘权限方式完成。没有添加或运行测试、模型、声音播放或真实迁移；未提交／发布。

完整构建继承既有Vite大分包、STATIC_VCRUNTIME弃用、jieba转义及可选hidden import tzdata／pysqlite2／MySQLdb告警；这些不作为声音／兼容验收通过的证据。

已交付入口 `artifacts/portable/voices-0162/dreamtalk/dreamtalk-desktop.exe`、同级 `dreamtalk.zip`，日志／摘要为artifacts/build-voices-0162.log及artifacts/voices-0162-delivery.json。用户从托盘退出旧dreamtalk后打开新入口，旧服务不会热更新。本地目录由构建生成，可直接打开程序；ZIP用于完整搬移。

待用户验收：含多个逗号的一整句不被拆碎，多个句号逐句生成；长句只有实际超容量才进一步拆分；小数及闭引号、尾句保留，实际发音与语气衔接改善；长输出若达到真实容量仍明确失败。源码与构建不代表上述声音效果通过验收。
