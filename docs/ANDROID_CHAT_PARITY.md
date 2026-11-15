# 两端聊天一致性

本页维护行为与实现契约。工程检查、本机包和用户验收以[状态清单](PROJECT_STATUS.md)为准。

## 对齐目标

在相同世界状态、角色／玩家、历史、API 模型和设置下，两端沿用相同的权限过滤、近期时间线、世界书、长期记忆、提示组装、上下文预算、群聊选人、私密片段与回复恢复规则。生成模型具有随机性，不承诺多次生成逐字一致；手机与电脑的 CPU 浮点结果及耗时也可能存在差异。

## 固定检索后端

继续使用 Windows 固定的 BAAI/bge-small-zh-v1.5 及 Qdrant ONNX 导出 revision 46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59。模型 SHA-256 为 1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38。全部分词资源由 manifest 固定摘要；APK 门禁逐项核对。

Android 通过 Chaquopy 调用 Kotlin ONNX Runtime CPU，再回到 Python NumPy 完成与 FastEmbed 一致的 CLS／float32／L2 归一化。HuggingFace Rust tokenizer 与 Windows 使用相同版本、tokenizer.json、特殊词、512 token 截断和批内最长右侧补齐。没有网络嵌入服务或用户模型部署入口，不新增检索 API 费用。

共享 HybridChatRecallRanker 只增加模型工厂选择；排序、0.8 阈值、多查询权重、RRF、向量缓存版本、权限与有效性检查、三秒等待边界不变。原生后端失败或超时沿原有关键词回退。后台单工作任务不被反复排队或重复加载。

模型首次需要时从包资源核验并提取至 Android noBackupFilesDir，不进入用户存档或备份。推理固定 CPU、两条线程，不依赖 GPU／NNAPI。原生推理每小批最多四段，NumPy 计算限制一条线程，避免最长输入与大批次集中挤占手机内存／CPU；没有丢弃、缩短候选或改变共享三秒边界。模型约 95 MB，另需运行库与提取后的私有副本；实际内存、冷启动、长对话耗时及温度仍需验收。

源码入口为 infrastructure/mobile_recall.py、infrastructure/semantic_chat_retrieval.py、bootstrap/mobile_host.py、plugins/android/src/main/java/SemanticRecall.kt 和 apps/mobile/src-tauri/src/recall_tokens.rs。构建准备脚本只核验资源，不推理；分词对照样本不含用户数据。

## 复用与依赖决定

| 组件 | 固定版本／许可 | 理由与维护边界 |
| --- | --- | --- |
| ONNX Runtime Android | 1.23.2／MIT | 官方 Java CPU API，替代 Android 不可用的 Python ORT 轮子。随包检查 ARM64、ELF 16 KB 对齐和原生依赖。 |
| HuggingFace tokenizers | 0.23.2／Apache-2.0 | 与 Windows 使用相同分词实现，避免手写 Bert 规范化。关闭默认 Oniguruma、下载和训练加速依赖，仅启用 fancy-regex；锁定 Cargo.lock。 |
| Android NumPy | Chaquopy 2.3.2 build 1／BSD-3-Clause 及轮子第三方许可 | 保留共享 float32 排序和缓存。Windows 当前 NumPy 2.5.3 无同版本 Android 轮子；用合成向量核对归一化和载荷，真实跨 CPU 差异单独验证。 |
| BGE 检索资源 | 与 Windows 相同 revision／MIT | 已有产品资源，复用全部模型和分词摘要；无用户部署入口或新增 API。 |

官方来源：[ONNX Java API](https://onnxruntime.ai/docs/get-started/with-java)、[Android 构建／R8](https://onnxruntime.ai/docs/build/android.html)、[ORT 1.23.2](https://repo.maven.apache.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/1.23.2/)、[tokenizers 0.23.2](https://github.com/huggingface/tokenizers/tree/v0.23.2)、[Chaquopy NumPy](https://chaquo.com/pypi-upstream/numpy/)、[固定模型导出](https://huggingface.co/Qdrant/bge-small-zh-v1.5/tree/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59)。许可与来源摘要随 assets/third-party/ 分发，模型来源和摘要随 manifest.json 分发。

Android 运行库采用 1.23.2；Windows 当前为 1.30.0。选择依据是独立 ARM 转译沙盒的兼容性与实际向量对照，不要求为追求版本号一致而引入已观测到的加载崩溃。不同 CPU 浮点差异与最终证据查状态清单。
