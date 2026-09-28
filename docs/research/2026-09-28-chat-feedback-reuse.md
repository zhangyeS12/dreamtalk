# 聊天状态反馈：复用决定

日期：2026-09-28。范围：现有聊天的保存、生成、状态查询与安全错误提示。

## 调查与决定

- [FastAPI HTTPException 官方文档](https://fastapi.tiangolo.com/tutorial/handling-errors/)已定义 `detail` 错误响应。本项目后端已经使用稳定的机器标签；客户端原先只保留 HTTP 状态。直接接通既有格式，不新增错误协议、服务或依赖。
- 已调查 [TauriTavern 的前端宿主指南](https://github.com/Darkatse/TauriTavern/blob/main/docs/FrontendGuide.md)与其 [v2.3.0 发布](https://github.com/Darkatse/TauriTavern/releases/tag/v2.3.0)。它有聊天历史、检索和持久化接口，但接入整个 AGPL 运行时来修复局部反馈缺口会增加适配和分发成本。本轮继续使用已有 CoreClient、React 和持久回合接口；未复制其代码。
- 错误响应只提取长度至多 96 的小写字母、数字和下划线机器标签；界面使用预定义中文提示，不显示服务器自由文本、模型内容或凭据。
- “检查回复状态”只访问当前世界、会话及最近玩家消息的既有 GET；页面刷新或重新打开会话后也可使用。它不 claim、不发送玩家消息、不自动重放模型调用。
- 群聊仅在当前生成请求等待期间，读取完成后间隔两秒再请求已有的有界消息页，显示已经持久保存的发言。连续两次读取失败后暂停，手动刷新可以恢复。停止等待或离开会话时清理定时器。此行为不是 Token 流式输出，也不生成演示消息。

## 已知界限

群轮 `completed` 表示持久终结；当前数据库没有保存自然停止、Token 耗尽或发言条数上限等结束原因，因此 UI 只报告“本轮已结束”。本次未增加状态迁移，不能宣称已经解决持久停止原因。

当前只读检查对应最近玩家消息。更早回合的逐条状态入口、跨重启保留具体失败原因及真实 Token 流式输出另行处理。

## 后续复用要求

新功能实现前必须先调查成熟实现，记录候选、版本/来源、许可、接入成本及采用或不采用理由。普通技术选择由工程师自行决定，在世界隔离、内核权威、调用去重及预算规则内推进。

## 本轮验证

- ESLint、TypeScript 和差异空白检查通过。现有锁文件安装的依赖用于构建，未修改依赖清单或锁文件。
- `build-portable.py --build-only` 成功生成 Windows 便携 ZIP；该选项跳过 Core smoke 和桌面 supervisor 测试。本轮未运行测试或调用模型。
- PyInstaller 的 missing-module 分析警告记录在 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，包含平台分支、可选库与静态符号项；没有以 `livingworld` 命名的缺失模块项。运行效果仍待用户验收。
- 最新产物和 SHA256 见 HANDOFF.md 的最新接续记录。
