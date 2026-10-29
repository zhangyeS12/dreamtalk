# Core 原生检索库启动顺序

本页维护当前启动约束。版本、工程检查和用户验收见[状态清单](PROJECT_STATUS.md)；早期 Windows 卡顿证据见[历史研究](research/2026-10-03-windows-native-import-hang.md)。

## 当前实现

`services/core/src/livingworld/bootstrap/cli.py` 在数据库／工作线程及桌面 stdin 监听器启动前，调用 `infrastructure/semantic_chat_retrieval.py` 的 `prepare_native_recall`，在启动线程准备 NumPy 和 FastEmbed 原生库。此处只导入库，不加载模型、不推理、不读取聊天或缓存、不联网；输出固定事件 `native_runtime_ready` 或 `native_runtime_unavailable`，不记录私密正文。

原生导入失败时本次 Core 使用关键词检索，不在控制管道启动后重新尝试原生导入。模型仍在首次需要时按需创建，语义工作保持3秒等待和关键词回退；超时不强杀原生线程，迟到结果不进入已结束请求。

桌面 `supervisor.rs` 的 Core 启动发现超时为30秒，属于宿主启动等待，不改变聊天模型超时或收费请求的重试策略。启动书架、开屏和更新流程另见[开屏](CELESTIAL_STARTUP.md)与[更新](WINDOWS_UPDATES.md)。

## 排错边界

历史线程栈提示 Windows 管道读取线程与首次原生库导入的时序风险，不代表已直接证实所有后续无响应都来自同一个锁。新问题先区分 Core 健康、启动日志、读取超时和模型任务，再在当前授权范围内诊断，不删除存档、拆换 Core 或自动重放付费请求。

使用当前完整包或规范本机入口，不再指定旧体验包目录。真实存档、进程栈、凭据或模型诊断仍需当前具体授权；历史诊断许可不复用。
