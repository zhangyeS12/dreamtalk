# 世界独立模型配置与兼容服务调查

调查日期：2026-10-08；实施前基线`85f8035`／Desktop0.1.42。用户要求书架保存默认模型、世界内修改只用于该世界，并询问Kimi／GLM是否可接入。只读官方公开资料，不调用模型或探测密钥。

## 成熟行为与复用决定

| 来源与版本 | 已核对内容 | 本项目决定与许可边界 |
| --- | --- | --- |
| [SillyTavern Connection Profiles](https://docs.sillytavern.app/usage/core-concepts/connection-profiles/)，文档说明自1.12.6内置；网页核对于2026-10-08 | 连接配置可以保存API、模型、地址和凭据选择，修改后显式保存，避免不同用途共享当前连接状态。 | 参考配置隔离与显式保存行为；不复制AGPL-3.0源码，不引入完整profile管理器。当前只需要默认配置和世界覆盖，继续使用已有React、Tauri、keyring和Core组装，Apache-2.0仓库无新增依赖。 |
| [Kimi迁移指南](https://platform.kimi.ai/docs/guide/migrating-from-openai-to-kimi)，Chat Completions兼容协议，网页核对于2026-10-08 | 官方示例替换OpenAI客户端的base URL/API Key，示例地址为`https://api.moonshot.ai/v1`；支持`/v1/chat/completions`。流式用量扩展为`stream_options.include_usage`。部分参数／型号能力有差异。 | 复用已有OpenAI-compatible adapter，不增加按品牌猜测的路由。实际地址按用户地区／控制台核对，完整模型ID、容量、流式与原生schema按型号确认。调用公开API不等于复用SDK源码或模型权重，无新增分发许可。 |
| [GLM官方文档索引](https://docs.bigmodel.cn/llms.txt)、[OpenAI兼容指南](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)、[官方SDK使用示例](https://docs.bigmodel.cn/cn/best-practice/case/ai-search-engine)，核对于2026-10-08 | 索引包含OpenAI API兼容指南；官方示例使用`https://open.bigmodel.cn/api/paas/v4`及`client.chat.completions.create`。本次兼容指南正文抓取超时，未据此宣称全部参数／模型已核实。 | 复用兼容Chat Completions入口。完整型号和可信容量由提供商资料／控制台核对，流式用量与JSON Schema分别声明。没有复制SDK／模型代码，无新依赖。 |

以上协议资料说明接入路径，不证明任意型号／代理已通过本应用验收。本轮不添加Kimi／GLM容量预设，不把品牌名当模型ID，不用估算绕过已有严格Token上限。

## 实施选择

保留`config/llm.json`和Windows安全凭据存储。旧v1配置成为书架默认；首次保存世界独立配置时生成v2容器，包含一个默认v1快照和按稳定WorldId索引的独立v1快照。没有覆盖的世界继承默认；显式保存后隔离，再通过按钮恢复继承。所有生成任务使用请求／任务自身的世界身份选模型，不根据UI当前选中的世界猜测。

每个配置继续通过相同注册表、协议adapter、路由、保守预留和账本；不增加调用、自动重放或私密内容外发。实际实现和本轮证据见[维护记录](../maintenance/2026-10-08-world-model-config.md)。
