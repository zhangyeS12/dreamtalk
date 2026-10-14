# IndexTTS 2.5 本机部署

日期：2026-10-12。用户要求本地部署，并补充已下载 PyTorch 安装包。本轮安装独立模型环境、获取官方资源及启动本机服务。公开版仍为 v0.1.53，本地应用仍为 0.1.54；没有 GitHub 发布授权。

> 本文记录部署时的0.1.54现场，旧入口和手动启动描述为历史证据。当前应用0.1.58已实现默认地址服务随应用启动；用户最新反馈合成等待68秒，当前交接见[说明](2026-10-12-speech-latency-handoff.md)。本轮只加当前导航，不改原轮安装／检查结论。

## 已完成

- 独立目录为 Git 忽略的 `artifacts/voice-runtime/index-tts`，Python 3.11.9，PyTorch／torchaudio 2.8.0+cu128。没有向 Core 的 `.venv` 安装模型依赖。其余官方锁定依赖先同步，再安装已核对摘要的本地 Torch；最终 `uv pip check` 检查 152 个包，兼容性通过。
- 官方代码固定 `d9e41aac89fd00b3d71497fddb287b7f24613712`，主模型固定 `c39ce5ba981572cb187443877ff559dfb246ce63`。主模型与 w2v-bert、CAMPPlus、BigVGAN 共 31 份文件，逐个检查大小与 SHA256／Git blob SHA1，记录在 `models-verified.json`，没有按预分配大小认定下载完成。
- 用户下载的 `torch-2.8.0+cu128-cp311-cp311-win_amd64.whl` SHA256 为 `34c55443aafd31046a7963b63d30bc3b628ee4a704f826796c865fdfd05bb596`，与官方锁文件一致。原下载保留，复制到模型安装目录使用。
- 没有更改系统代理或 Clash 节点，没有关闭 TLS 校验。部分模型大文件从官方 ModelScope 获取，最终字节以固定 Hugging Face 版本摘要为准。aria2 1.37.0 仅为本地独立下载工具，不进入应用包。
- NLTK 发音资源已预取。启动脚本设置离线模型读取并关闭 HF token 隐式读取；访问密钥在 Git 忽略目录，不打印、不写入文档或音色卡。
- `start-local.cmd`／`stop-local.cmd` 提供入口；Windows 虚拟环境会生成实际解释器子进程，PID 记录指向已核对的实际服务进程，避免只停启动器而残留服务。辅助 PowerShell 脚本经语法解析，修改后的进程记录逻辑没有重启／停止实测。
- 服务已实际启动；日志显示 application startup complete，仅监听 `127.0.0.1:7861`，进程身份与桥接脚本匹配。服务启动不加载模型，第一次实际配音才加载。
- 桥接使用 BF16、标准 PyTorch GPU 路径，明确关闭可选自定义 CUDA 内核编译，本机不必为此安装完整 Toolkit。源码与部署副本摘要一致。

## 来源与复用

安装沿用 [IndexTTS 官方说明](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/docs/README_zh.md)及锁文件，没有修改上游推理算法。模型使用 [Bilibili Model Use License](https://github.com/index-tts/index-tts/blob/d9e41aac89fd00b3d71497fddb287b7f24613712/LICENSE)，仅独立部署，权重和环境不进入 dreamtalk 包。aria2 使用 GPL-2.0，也不进入应用包。没有向 Core 新增 Torch／CUDA 依赖或引入新应用框架。

## 使用与证据边界

本机说明为 `artifacts/voice-runtime/README.md`；安装收尾记录 `deployment-ready.json`，启动日志和 PID 在同目录。本地 0.1.54 入口仍为 `artifacts/portable/voices-0154/dreamtalk/dreamtalk-desktop.exe`。此次未重构建应用或替换公开附件，包内手册仍是原构建快照。

在世界“设置 → 角色配音”选择本地方式，地址填写 `http://127.0.0.1:7861`，复制本机密钥后开启并保存；在“通讯录 → 角色资料 → 角色音色”导入／绑定参考人声。制卡流程及同音源同参数的等效关系见[配音手册](../CHARACTER_VOICES.md)。

RTX 5070 Ti Laptop GPU 约 12 GB 显存及驱动通过硬件信息核对，不证明实际推理、显存峰值或性能。没有加载模型、生成音频、上传参考人声、运行 dreamtalk／自动测试／smoke、调用远程或付费模型、执行真实存档迁移。声音、角色映射、播放和 GPU 实际表现由用户验收。没有更改系统启动、快捷方式、驱动或代理；源码未提交或发布。

安装曾遇沙箱 Windows PE 权限限制，已在授权环境中完成；官方完整锁同步要求重新下载同版本 Torch，因为手动文件来源记录不同，改为先同步其余锁条目再安装经摘要核对的本地文件。没有放宽依赖版本、模型摘要或验收边界。

最终静态检查：桥接 Ruff／格式通过，3个辅助脚本在 Windows PowerShell 中语法解析通过；952个本地文档目标0断链，源码隐私门禁841文件0发现，Git差异格式核对通过。已核对的模型和密钥路径被Git忽略。静态工具仍出现原Core环境的既有Python路径提示，不影响本轮退出结果，未因此修改Core环境。核对模型完成后移除3份废弃下载碎片，释放1,457,520,640字节；用户下载的完整Torch文件保持原样。
