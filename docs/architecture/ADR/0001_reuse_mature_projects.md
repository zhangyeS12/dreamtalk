# ADR-0001：优先评估成熟项目复用

状态：已接受  
日期：2026-09-27  
确认：产品负责人明确表示不再要求独立实现，应选择效果和维护成本更好的方案。  
替代：[Architecture Review 001](../ARCHITECTURE_REVIEW_001.md) 的决策 15 中“必须独立实现、不复用 SillyTavern 源码”的实施限制。已完成的格式 adapter 不因此自动替换。

## 背景

dreamtalk 已有 Apache-2.0 的 Python Core、React/Tauri 客户端、Character Card/Lorebook 兼容、独立知识权限和确定性 World Kernel。成熟项目可能已经解决聊天交互、格式兼容和内容激活等局部问题；重复实现会增加成本。SillyTavern 的 [World Info 文档](https://docs.sillytavern.app/usage/core-concepts/worldinfo/) 描述了关键词触发、来源绑定、扫描范围和内容预算等成熟体验。其[主仓库许可证](https://github.com/SillyTavern/SillyTavern/blob/release/LICENSE)为 AGPL-3.0，与本仓库当前许可证不同。

## 选择

对每个具体能力先比较：采用现有项目或组件、通过公开接口集成、沿用现有 dreamtalk 实现。优先选择满足用户体验、世界内核权威、知识隔离、可维护性和可分发性的复用方案；不再把“独立实现”当作目标本身。可以复用成熟格式规范、交互模式和许可证适合的依赖，也可以评估独立进程或服务集成。

不得把来源项目代码直接贴入 Apache-2.0 仓库，然后仍声称全部代码按现有许可分发。若具体方案涉及 AGPL 代码、其衍生修改、重新许可或新增运行依赖，先列出代码边界、分发方式和许可证影响，再决定是否采用。没有这些前提时，借鉴公开行为与规范、保持现有实现仍是可行选择。

## 不变的边界

- Director 只产生批量计划，不直接写最终角色台词或提交 WorldEvent。
- 只有确定性 Kernel 提交正式世界事件；LLM 和外部组件不能直接写 WorldTruth。
- 角色与玩家知识先按权限过滤，再进入检索和提示词。
- 外部内容仍经 Draft → Preview → Commit；暗线默认不向角色开放。
- 本 ADR 不引入 SillyTavern 运行依赖、不复制其代码，也不改变当前包的许可证。

## 后续评估

每次复用记录具体能力、项目版本、许可证、维护成本、数据流与退出方案。只有收益高于适配和长期维护成本时才引入依赖；不为“看起来现成”而增加框架。涉及世界书条件激活时，先区分创作素材、角色可见权限与运行世界事实，不照搬会泄漏暗线或绕过 Kernel 的功能。
