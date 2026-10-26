# 聊天上下文与后台诊断优化记录

## 范围

本轮处理两项已有源码证据、无需改变产品权限或费用契约的工程问题：

- 私聊回复准备不再先读取玩家在世界中的全部会话再查找目标；上下文按 `world_id + conversation_id` 精确读取，并按会话根导入只追踪当前角色卡版本链。
- Director、在线主动联系和离线联系增加统一的脱敏结构化后台诊断。记录固定组件、阶段、任务 ID、世界 ID、代际和失败码；不记录提示词、聊天正文、模型回复、凭据或原始异常文本。诊断 sink 失败不会改变持久结算、取消或防重放规则。

实现入口：

- `application/chat_context.py`
- `application/chat_conversations.py`
- `infrastructure/persistence/chat_conversations.py`
- `infrastructure/persistence/world_content.py`
- `application/background_diagnostics.py`
- `infrastructure/background_diagnostics.py`
- `infrastructure/logging.py`
- `application/director.py`
- `application/proactive_contact.py`
- `application/offline_contact.py`

## 检查

| 检查 | 结果与边界 |
| --- | --- |
| Python 3.13 Core compileall | 通过；使用项目 `.venv`。系统 Python 3.11 无法解析仓库既有 PEP 695 语法，不作为代码失败证据。 |
| Ruff | 全仓通过。 |
| Pyright | 项目配置检查通过，0 errors / 0 warnings；新增诊断模块已纳入配置。 |
| 前端 lint／TypeScript | 通过；本轮未改变前端行为，但核对了当前工作树既有改动。 |
| Git 差异空白／配置 JSON | 通过。 |

## 交付边界

本轮没有运行自动化测试、真实应用、真实模型、后台付费任务或用户存档，也没有提交、打包或发布。改动仍在当前工作树，不能归入已公开的 0.1.91；真实聊天性能、后台故障日志和存档连续性仍待用户验收。

角色长期意图、自主 Agent 闭环、世界时间线分支和聊天分支的界面提示未在本轮实现，保留后续讨论。
