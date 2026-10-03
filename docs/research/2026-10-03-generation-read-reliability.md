# 2026-10-03 生成与读取稳定性：成熟方案复用

本轮是修复已有功能，不引入新的技术栈或依赖。以实际安全日志中的schema_validation_failed和源码中的无界读取/工作等待为依据，不推断旧模型正文或已运行EXE路径。

## 直接复用

1. [DeepSeek JSON Output官方说明](https://api-docs.deepseek.com/guides/json_mode/)建议JSON输出任务在提示中使用JSON并提供实际示例。现有路由与jsonschema校验继续使用；事件提示补齐完整10条示例，生成约束中不需要模型决定的发布时间可使用系统默认值。JSON模式不替代应用的结构校验，不接受残缺批次、不追加付费格式修复。仅参考文档，没有复制SillyTavern或其他项目的实现。
2. [Python asyncio官方文档](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.wait_for)提供wait_for、shield、to_thread及持有task引用的标准组合。直接用于现有FastEmbed工作：3秒停止等待，仍保留单一真实工作直到完成，禁止并发冷加载和迟到结果注入。线程不能通过超时强制终止，关闭期间是否受原生线程影响仍待实际体验。
3. [MDN AbortSignal timeout](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static)及[AbortSignal.any](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static)说明网络超时和调用者取消的组合。本轮用已支持的AbortController、定时器和abort事件实现同样的读取生命周期，避免要求用户升级到支持新静态方法的WebView2。只限定GET读取，写入和付费请求维持原claim/结果核对机制。

复用现有React状态/effect清理、标准fetch/AbortController、Python标准库、jsonschema、FastEmbed和DiskCache；第三方许可和固定模型不变，无新依赖或对外资料范围扩展。本轮不运行测试、应用、模型推理或付费调用；实际格式成功率和读取响应仍待用户验收。
