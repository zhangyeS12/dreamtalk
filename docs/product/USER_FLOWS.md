# dreamtalk 用户流程

本页提供当前流程入口；规则看[PRODUCT](../../PRODUCT.md)，实际完成度看[状态清单](../PROJECT_STATUS.md)。流程存在不等于所有场景已验收；原始问题编号只用于历史追溯。

| 流程 | 用户操作与结果 | 详细说明 |
| --- | --- | --- |
| 配置与进入 | 打开书架，配置／导入默认API；预览后进入或创建世界。世界可独立配置API并恢复默认。失败保留数据，提供明确恢复入口。 | [设置](../SETTINGS_HANDBOOK.md)、[书架](../WORLD_ARCHIVE.md) |
| F-01／F-02：建立资料 | 书架管理世界书，通讯录管理角色卡；手动编辑、文件导入或联网辅助生成，审阅草稿后确认。先有世界，资料与身份按世界隔离。 | [产品约定](../../PRODUCT.md#世界资料与知识)、[导入](../architecture/IMPORT_MODEL.md) |
| F-03：导入卡／书 | 选择文件、查看转换与兼容提示、预览并确认；导入定义不等于已创建运行角色或开放隐藏背景。 | [导入契约](../architecture/IMPORT_MODEL.md) |
| F-04／F-09：交流与获知 | 打开私聊创建／复用角色；群聊可指定下一位或自动选人。消息持久保存；来源、记忆与世界事件按权限读取。最后未回复消息满足条件时可人工恢复并确认新费用。 | [聊天](../CHAT_FUNCTIONAL_EXPERIENCE.md)、[记忆](../LONG_TERM_MEMORY.md)、[事件](../WORLD_EVENT_JOURNAL.md) |
| F-05：后台与联系 | 按需开启自动活动、相遇、共同休闲、动态或主动联系并确认费用。Busy／Available控制联系许可，暂停控制世界时间，两者不同。 | [日常](../DIRECTOR_ACTIVITIES.md)、[主动联系](../PROACTIVE_CONTACT.md)、[离线](../OFFLINE_MESSAGES.md) |
| 配音与图片 | 配置音色／路线后开启；完整回复才进入配音队列，重新配音先试听再确认。三库表情、图片与可选说明按权限和费用操作。 | [配音](../CHARACTER_VOICES.md)、[媒体](../CHAT_MEDIA.md) |
| 存档与更新 | 书架存档入口选择文件夹，管理一自动四手动；导入不加载，加载前可另存当前自动档。应用内确认更新后沿签名完整包与独立保护快照交接。 | [存档](../DATA_BACKUPS.md)、[更新](../WINDOWS_UPDATES.md) |
| F-08：设置与诊断 | 设置手册管理模型、额度、后台和世界配置；普通用户看到状态与可执行下一步，不承担进程／端口／数据库维护。 | [设置](../SETTINGS_HANDBOOK.md)、[开发权限](../../AGENTS.md#20-current-verification-responsibility) |

早期 F-06 的完整 Director 风格、F-07 的 Checkpoint／Timeline Branch 尚无完整产品流程；整份本机存档已经实现，两者不能混淆。它们不因保留历史编号获得开发授权。
