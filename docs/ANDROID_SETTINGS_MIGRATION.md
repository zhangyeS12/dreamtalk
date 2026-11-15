# 安卓设置迁移与后台联系

本页说明实现和使用契约；交付版本、工程检查和用户验收以 [状态清单](PROJECT_STATUS.md) 为准。

## 设置入口与范围

世界内“设置”提供与 Windows 对应的 11 类目录。书架的设置入口只展示应用设置和全局默认模型。分类按需挂载，访问过的分类保留未保存输入；离开世界或切换主要页面时检查未保存修改。

| 分类 | 安卓行为 |
| --- | --- |
| 模型与聊天 | 全局默认、世界独立模型、全局与世界群聊调度器、恢复继承、容量、回复长度、流式、超时、原生 JSON、每轮 Token 硬上限和世界文风；草稿额度在明确应用后才生效 |
| 聊天视觉 | 通用／会话内角色背景；仅按需加载通用与当前角色背景，不加载其他角色立绘、三维关系网、毛玻璃和装饰动画 |
| 表情与图片 | 频率、不限制表情频率、联网取图、云端图片分析、远程发送同意、每日调用限制、公共／专属／个人表情库；不显示 Ollama、本机目录或部署入口 |
| 角色配音 | 官方在线演示与云端付费路线、远程及费用同意、次数／字数、跳过动作、计价查询；角色资料内导入、绑定、试听、删除和系统导出音色；不提供本地配音路线 |
| 后台运行与通知 | 用户明确开启的后台会话、系统消息通知、停止入口、可选开机恢复、系统通知与电池设置入口 |
| 数据与备份 | 手机私有的自动＋四个手动位置，保存、改名、另存自动位置、导入／导出 .dreamsave、明确确认后加载；不要求用户填写手机文件路径 |
| 世界时间 | 读取、暂停／恢复、倍率；提高倍率可能增加按世界时间调度的 API 用量 |
| 角色活动 | 自动活动、每批规划人数、相遇、共同休闲、状态及明确请求新规划；地点作者设置与角色初始位置／锁定／常驻倾向使用普通表单 |
| 主动联系 | 当前玩家可联系／忙碌、在线间隔、离线阈值、费用同意、未回复限制和任务状态 |
| 世界动态 | 公开背景准备、批次状态和设置；只显示当前玩家已获知的事件 |
| 关于与诊断 | 当前安卓程序版本、系统版本、本机核心与模型配置状态、无正文或密钥的诊断复制；不显示 Windows 路径或更新通道 |

书架提供校园示例预览与确认创建，沿用已有模板、可见范围确认及幂等请求；创建不调用模型，不自动开启后台生成。

聊天回复、私密遮罩与诊断契约见[产品行为](../PRODUCT.md#聊天私密片段与诊断)及[Windows 修改同步](ANDROID_WINDOWS_SYNC.md)。

## 后台与通知契约

- Kotlin `CoreRuntime` 仅持有应用 Context，Python Core 不归聊天页面或 Activity 生命周期所有。用户开启后由 Android 前台服务维持会话，常驻状态通知提供停止操作；未开启时退到后台继续阻止新的生成。
- 首次开启必须明确同意 API 用量，并取得通知许可。这个开关不替用户开启任何世界的活动、主动联系或动态权限。各世界的费用、暂停、忙碌、合法事由和共同等待回复限制继续生效。
- 计划及台词由现有业务校验；Kernel 仍是世界事实的提交方。没有活动依据时可以不联系，不伪造聊天或活动。
- 通知只读取已提交的 outreach 消息。持久游标、稳定消息通知 ID 和只提醒一次标志用于去重；通知不调用模型、不读取私人聊天正文，只显示角色名称和通用来信提示。前台已检查的消息不再补发系统提醒。
- 点击通知后核对世界、玩家绑定和可访问会话；不能借通知切换玩家身份。跨世界跳转时保护未保存输入。通知不会确认已读或解除等待回复。
- 服务进程恢复重新读取 Keystore 与已有存档，沿 Core 的中断回执处理；不重新提交结果未知的付费任务。存档加载后重置通知游标，避免将历史消息当作新来信。
- 默认关闭开机恢复；只有用户单独开启且后台许可仍有效时才尝试恢复。强行停止、明确关闭后台或关机期间不承诺运行；Doze、系统节电与厂商限制可能延迟执行，需要真机检验。

## 安全存储与恢复

聊天、世界和调度器的密钥使用 Android Keystore AES-GCM。派生独立配置分配独立 SecretRef，不覆盖继承源；更换提供商或地址需要重新填写密钥。配音和视觉密钥继续绑定世界，发送到 Core 内存凭据会话，不能进入 localStorage、模型配置文档或存档导出。只在确认没有设置引用且任务已停止后清理旧密钥；清理不确定时保留并提示。

存档复用原 `save_slots`／`save_safety` 的校验、WAL 一致性快照、工作副本升级和恢复日志。创建备份或切换数据前等待活动任务，超时保留当前状态；加载后不重发恢复任务。通过 Android Storage Access Framework 读写用户选择的文档，不申请广泛存储权限。真实 Windows 存档与手机的跨平台互通、系统文件提供者仍需验收。

## 复用与来源

没有新增框架、数据库或第三方依赖。

| 来源 | 版本／许可 | 复用理由 |
| --- | --- | --- |
| Windows 设置与 Core | 独立快照来源由 source-snapshot 回执标识；Apache-2.0 | 沿用模型、费用、知识权限、活动、联系、媒体和存档契约，给组件注入安卓宿主操作 |
| Tauri Android 插件 | 已锁定 2.12.5；MIT／Apache-2.0 | 延续现有宿主，复用权限回调和 ActivityResult 文件选择 |
| Android 原生 API | 工程 compile／target SDK 36 | 使用明确用途的 specialUse 前台会话、通知渠道和系统文档选择；不通过其他用途的服务规避限时 |
| HTTPX | Android 现有 0.28.1；BSD-3-Clause | 为联网取图提供有界传输，避免引入 DDGS 的额外原生运行依赖 |
| DDGS DuckDuckGo 图片协议参考 | main 页面于 2026-11-07 核对；MIT | 独立实现与原桌面相同的单后端、地区、安全搜索和 Share 许可过滤；两次协议请求不自动切换搜索服务 |

参考：[Android 前台服务类型](https://developer.android.com/develop/background-work/services/fgs/service-types)、[Doze](https://developer.android.com/training/monitoring-device-state/doze-standby)、[通知许可](https://developer.android.com/develop/ui/compose/notifications/notification-permission)、[系统文档选择](https://developer.android.com/training/data-storage/shared/documents-files)、[Tauri 移动插件](https://v2.tauri.app/develop/plugins/develop-mobile/)、[DDGS 协议实现](https://github.com/deedy5/ddgs/blob/main/ddgs/engines/duckduckgo_images.py)。

## 验收顺序

1. 创建校园示例，配置自己的 API，打开角色私聊，核对文字聊天和世界设置的继承范围。
2. 明确开启所需活动、主动联系及后台运行，允许系统通知；保持“可联系”和世界运行状态。间隔按世界分钟计算，合法活动条件仍需满足，不保证开启即发消息。
3. 退到桌面、切到其他应用及锁屏，分别观察来信；先收到系统通知，再打开应用，核对消息 ID、保存时间及正文一致。工程侧须证明消息在打开应用前已经提交。
4. 不回复、设为忙碌、暂停、停止后台、拒绝通知、断网恢复及系统回收后分别核对不重复生成、不重复收费与提醒。
5. 用合成存档验证五个位置、系统文件导入导出、取消选择、损坏／较新存档拒绝，以及加载后身份、媒体和费用保护。之后再进行用户真实存档验收。
6. 在 vivo X80／OriginOS 6 检查长时间锁屏、开机恢复、耗电、发热、聊天输入和流式流畅度；编译和浏览器检查不能替代这一步。

## 源码入口

- 前端：`apps/web/src/mobile/Settings.tsx`、`BackgroundSettings.tsx`、`native.ts`、`MobileApp.tsx`，及注入宿主操作的既有设置组件。
- 原生：`plugins/android/src/main/java/CoreRuntime.kt`、`DreamtalkBackgroundService.kt`、`ExamplePlugin.kt`、插件 Manifest 与通知图标；Rust `token_bound.rs` 提供独立于 Activity 的 JNI 计数入口。
- Core：`bootstrap/mobile_host.py`、`mobile_settings.py`、`mobile_storage.py`、`mobile_notifications.py`、`infrastructure/mobile_media_search.py`。
- 回归：`tests_mobile`、前端 `mobile/Settings.test.tsx`、`scripts/check-mobile-settings.py`；检查回执统一见状态清单。
