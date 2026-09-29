# 后台启动与离线主动联系：成熟实现调查

2026-09-29；实施前核对官方文档和 GitHub v2 分支。

- Tauri 官方 autostart 2.6.0：直接使用 Rust 插件的 enable/disable/is_enabled，注册 `--background`；Windows 是用户登录后启动。https://v2.tauri.app/plugin/autostart/ 和 https://github.com/tauri-apps/plugins-workspace/tree/v2/plugins/autostart 。
- Tauri 官方 single-instance 2.5.0：作为首个插件，普通重复启动唤起已有窗口，后台重复启动不弹窗、不再启动 Core。https://v2.tauri.app/plugin/single-instance/ 。
- Tauri 现有 2.x system tray：启用 tray-icon，复用 Menu/TrayIconBuilder 和窗口 hide/show；不自写注册表、Windows 服务或托盘库。https://v2.tauri.app/learn/system-tray/ 。插件及 Tauri 采用 MIT OR Apache-2.0，具体版本以 Cargo.lock 编译解析为准；随包保留新增组件许可。
- 离线桥接复用 SQLAlchemy/Alembic、现有 Director 已确认角色字段投影、公共世界书筛选与 governed LLM gateway。选人和目的属于一个有限 Director 联系计划；最终台词由独立 Character dialogue 请求完成。复用输入计数/硬预算/路由/用量结算，不引入另一套 Agent 或定时框架。
- 不复制 SillyTavern AGPL 源码；普通聊天和世界时钟沿用现有实现。应用在线记录采用一分钟轻量 checkpoint；没有每角色轮询或每六小时必付费调用。

实际Cargo.lock解析：Tauri2.12.0，autostart2.6.0，single-instance2.5.0，auto-launch0.5.0，tray-icon0.25.1。新许可直接从Cargo下载的源码复制到docs/licenses，采用MIT OR Apache-2.0（auto-launch MIT），不重新实现系统注册/托盘/单实例。初次编译的AppHandle接口与私有token访问错误已按本机正式库源码修正。工具链STATIC_VCRUNTIME弃用提示需在后续CLI升级时处理，本轮保留原静态runtime策略。

自动审批拒绝新增私聊正文外发，采用更窄的替代：模型只接收已授权角色资料/公共背景/计划；本地消息标识与位置只用于去重，不发给模型。

保存修复（2026-09-29）：副本诊断发现通讯录角色不一定有CharacterState；直接复用日常规划planning_input会误报director_characters_required。将原已确认角色字段投影提取为approved_persona并由两处共用，离线联系先按本地绑定玩家已打开的direct会话限定角色；日常活动仍只规划已放置角色。离线输入不读取位置或增造地点，以角色名触发公共背景；已有意图仍作为计划参考。无新依赖、Agent框架或手写角色卡解析。
