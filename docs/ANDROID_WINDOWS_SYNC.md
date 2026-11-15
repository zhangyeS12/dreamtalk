# Windows 修改同步与安卓边界

本页维护同步范围和宿主兼容契约。当前源码、已发布版本、检查结果和用户验收只查[状态清单](PROJECT_STATUS.md)。

## 来源与范围

来源是正式 Windows 仓库当前源码，包含其未提交修复；不把 Git HEAD 或 Windows 公开安装包等同于这次工作区快照。初始快照保留在 `source-snapshot.json`，增量捕获记录为 [source-state.json](../artifacts/windows-sync-20261108/source-state.json)。其中逐文件记录来源、同步前后摘要和 Android 保留项；备份仅为工程源码，位于同一工作目录的 `before`，不包含真实用户存档或模型配置。

共享 Core、HTTP、API DTO、消息渲染与回归测试按实际内容差异同步。Windows 工程保持只读；桌面宿主、系统设置、安装器、更新频道以及 Windows 本地模型入口不迁移到手机。

## 同步后的聊天行为

- 私密内容在原段落显示局部遮罩，支持点击／键盘展开收起；组件身份稳定，持续会话刷新不会重置展开状态或焦点。关闭时私密原文不进入 DOM；公开文字正常显示，受众变化后重新遮罩。
- 保存并传递 `privacy_fallback`：true 为分类兜底、false 为有效分类、旧记录 NULL 为来源未知。旧消息原文和受众不改写，消息编辑、分支、导出继续保留该来源。
- 普通群聊也接受合法完整的分段协议；JSON 私密分类在终态校验完成之前不显示未分类正文。完整正文遇到可选记忆尾部损坏可恢复，残缺正文仍拒绝，不补字、不增加修复调用。
- 私聊、群聊、HTTP／SSE、持久化及记忆／媒体辅助链路共用固定阶段与原因。供应商类别／状态和未知异常源码帧沿白名单记录，不保留对话、完整提示、密钥、异常原文或 SQL 参数；日志失败不改变业务结果。
- 沿现有 Alembic 链升级，旧来源保持未知；每个支持的旧 revision 保留数据升级回归，不把列物理顺序当作 schema 契约。

主要共享入口：`application/chat_privacy.py`、`chat_event_annotations.py`、`chat_diagnostics.py`、`chat_reply.py`、`group_chat_reply.py`，HTTP 的 `chat_diagnostics.py`／`chat_messages.py`，持久化的 `chat_messages.py`／`migration.py`，以及前端 `PrivateChat.tsx`／`privateMarkdown.ts`／`ChatMessageBody.tsx`／`ConversationParts.tsx` 和 `contracts.generated.ts`。

## 安卓必须保留的适配

| 适配 | 保留方式 |
| --- | --- |
| Core 生命周期与后台许可 | 合并 cli 的 `native_host` 挂接，保留最新 logger 注入；未替换 CoreRuntime、后台服务或原生通知 |
| 手机历史渲染 | 合并最新 Markdown／遮罩组件，并保留 ChatMessageBody 的 memo；不挂载三维界面 |
| Token 硬上界 | 保留 request_bounds 的原生可信计数入口，不退回按品牌猜测或仅字符估算 |
| 模型、配音、媒体与安全存储 | 保留 Android nativeInvoke、API-only 入口及独立 Keystore 引用，不引入 Windows 本机路径 |
| 存档、文件和通知 | 保留 save_safety 移动私有目录、系统文档选择、后台维护屏障和通知游标 |
| 记忆检索 | 同一固定 BGE 与共享排序／权限／缓存通过安卓原生 CPU 后端运行；具体依赖、分词与资源契约见[聊天一致性](ANDROID_CHAT_PARITY.md)，没有远程 embedding 收费路线 |

保持既有框架和数据库；固定检索宿主新增运行依赖及许可见聊天一致性契约。其余复用本项目 Apache-2.0 源码、已锁定 React／react-markdown、FastAPI、标准库 contextvars 及既有 StructuredLogger。安卓离线环境继续使用既有 Pydantic 2.10.6 和 FastAPI 0.115.12，兼容性以当前回归为准，不把 Windows 的其他依赖版本直接装到手机。

## 检查入口与证据

- `scripts/check-windows-sync.py`：Core、前端、契约／类型／格式检查。合成数据库必须位于源码树外的系统临时目录；APPDATA、LOCALAPPDATA、缓存和临时文件独立隔离。Core 检查阻止外部 DNS／网络，只允许回环；前端设置桥接选择 `.venv-check`，不寻找 Windows 的 `.venv`。
- `tests_mobile/test_mobile_chat_sync.py`：通过实际移动宿主启动合成旧 schema，验证升级、原生宿主挂接与 HTTP 错误日志的固定元数据，验证私密正文和会话令牌不进入日志。
- `scripts/check-mobile-private-browser.py`：真实共享组件加安卓样式，使用合成消息，无头临时浏览器验证窄屏布局、持续刷新、展开收起和键盘焦点，阻止外部页面请求。独立测试 HTML／Vite 配置仅在 artifacts 内，不进入生产前端入口或 APK。
- 同步的 `scripts/live-llm-smoke.py` 只供既有离线测试导入，验证没有明确开关时不能调用供应商；本轮未执行真实 smoke。

结果分别保存在 [Core](../artifacts/windows-sync-20261108/core-checks.json)、[前端](../artifacts/windows-sync-20261108/web-checks.json)、[静态检查](../artifacts/windows-sync-20261108/static-checks.json)及[浏览器](../artifacts/windows-sync-20261108/browser/result.json)。首次检查发现测试临时目录位于源码内、设置桥接 Python 路径不适用，修复检查入口后重跑通过；未弱化数据库保护、断言或跳过失败测试。

工程检查不等于 Android 真机安装、升级、模型效果或后台保活通过。源码同步检查阶段没有生成 APK 或发布；之后的独立源码提交、CI 与发行结果见状态清单，该源码同步阶段未运行用户已安装应用、调用真实模型或读取真实存档；后续获准的固定 BGE 合成对照、本机包及手机安装验收另见状态清单。

[收尾核对](../artifacts/windows-sync-20261108/closeout.json)记录本轮源码摘要、Windows 隔离、隐私和文档链接结果。
