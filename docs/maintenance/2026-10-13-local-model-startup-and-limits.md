# 0.1.71本机图片服务自动启动与本地不限次数

日期：2026-10-13。用户明确要求图片服务与配音一样随启动运行、开机自动启动，并去掉两类本地模型的次数限制。源码0.1.71、API1、迁移head0049_local_model_limits；公开基线仍0.1.53／a3f2183，未提交／发布。

## 本轮行为

- 配音provider=local及图片分析caption_route=ollama不再核验每日调用上限，设置页隐藏本地每日次数输入。缓存／幂等回执、并发与文件容量等原规则保持；这次只取消次数限制。
- 0049仅给两张计次回执表追加可空is_local标记，不改旧回执。新的本地回执不消耗云端上限；云端保留原次数、授权与费用规则。旧版无法分类的回执继续保守计入当日云端准入，不依据当前设置倒推历史调用来源；下一UTC日期自然不再影响新日额度。
- Tauri监督独立Ollama服务，启动后仅按已配置本机图片模型、默认回环地址的需求启动；保存本机设置时登记目录并检查／启动，设置中也提供检查及目录选择入口。图片分析开关不触发下载或推理。
- 复用已有dreamtalk开机后台启动；开启并保存“开机后台启动”后，隐藏启动也会启动所需图片服务。没有单独新增模型的注册表启动项，移到新版便携目录后沿已有“保存并更新启动位置”操作更新程序入口。
- 标准独立目录自动发现范围仅为程序附近的image-runtime／artifacts/image-runtime，也可由用户明确选择。只监听127.0.0.1:11434，Ollama云功能关闭，模型首次图片请求才加载；退出只结束由当前host启动的子进程。已有外部Ollama实例复用，未知占用不关闭。独立目录／模型不进入应用包。

## 成熟实现与接线

复用仓库现有local_speech.rs的Tokio子进程生命周期及Tauri autostart=2.6.0，不引入依赖或更换架构。[Tauri官方Autostart](https://v2.tauri.app/plugin/autostart/)用于Windows后台入口；[Ollama Windows独立部署](https://docs.ollama.com/windows)及[配置说明](https://docs.ollama.com/faq)用于serve、模型目录、回环地址与禁用云服务。沿用已部署Ollama0.40.3（MIT）与Qwen3-VL4B Instruct Q4_K_M（Apache-2.0），不复制酒馆代码。

入口：`apps/desktop/src-tauri/src/local_images.rs`、`lib.rs`、`apps/web/src/ChatMedia.tsx`、`SpeechSettings.tsx`及`SpeechPlayback.tsx`；Core的`/system/media/local-demand`、两个persistence计次准入、0049迁移及旧形状核对。

## 实际检查与限制

Ruff／Python格式及前端ESLint／TypeScript已通过。前轮Rust工具在普通沙箱拒绝访问、两次自动审批审核超时，实际工具及隔离副本替代也未完成格式／编译；这是前轮现场。用户随后明确要求保持原呈现并重新编译，本轮必要编译及Rust格式已获工具执行并完成，0.1.71直接体验EXE见[入口记录](2026-10-13-source-experience-entry.md)。没有生成分发包或运行应用验收。

遵守AGENTS第20节，不添加／运行测试、smoke、应用、模型推理或真实迁移；不读取聊天／音频／图片，不改变当前进程和系统自启动登记。源码已实现不代表真实登录启动、目录移动、退出及不限次数已经验收。

用户随后明确要求：从现在起，除发布到GitHub外，不再在本机打包。本轮打包计划取消，不再等待此前本机格式／build-only合并请求的批准；按[AGENTS第20节](../../AGENTS.md#20-current-verification-responsibility)完成已允许的必要编译并提供直接EXE。已有分发包仍为0.1.70，不能据0.1.71源码推定旧程序已具备新行为；未来明确获准发布时再打包。

新版实际使用时需在“后台运行”保存更新启动位置；图片设置保存本机服务地址／完整模型名称即可。实际Windows登录、后台启动、关闭／托盘、本地超过原次数上限及云端额度隔离仍由用户验收。

补充已完成检查：292份Python AST、两个新增Boolean列及两条排除本地的计数SQL均离线编译通过；没有连接数据库或执行SQL。工作流规则更新前，文档1077个本地目标、0断链；源码隐私885个文件、0发现；Git差异空白核对通过。此前格式及build-only合并请求的打包分支已取消；本轮Rust格式及直接EXE必要编译结果另见入口记录。项目Python仍有既有真实路径定位警告，相关命令退出0；不将它写为模型故障。
