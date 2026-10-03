# 后台任务反馈复用调查（2026-10-03）

## 调查与选择

- [Carbon Notifications](https://www.carbondesignsystem.com/building-blocks/core/patterns/notifications)，页面最后更新2026-08-12、本轮2026-10-03读取；[上游许可](https://github.com/carbon-design-system/carbon/blob/main/LICENSE) Apache-2.0。采用靠近任务的持久行内反馈和明确下一步入口；不复制代码、图标或引入整套Carbon组件。此处参考的是文档快照，没有安装Carbon包版本。
- [W3C WCAG 2.2 状态消息](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)及[ARIA22](https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA22)：正常等待/跳过用status，真正失败用alert；动作按钮放在播报文本之外，不在后台刷新时抢焦点。规范作为实现依据，不作为运行通过声明。
- 直接复用项目已锁定的React19.3.0/MIT、现有按钮/绿色主题/设置分类及认证API。没有新增依赖、调度器、状态机框架或数据表；只有应用内导航和已存在的只读内容/状态请求。

## 代码确认的边界

- Director失败需显式重新规划；暂停不是错误，关闭开关与上一批失败是不同信息。已经放置角色后不再催用户重复放置。
- 世界动态pending只表示尚未发布，不表示玩家尚未经历。最近整批processed达到80%才续批；没有待发布且未达门槛时，引导去世界事件手动标记，保留既有显式付费新批按钮。
- offline_no_contact是合并结果，可对应资格不足、未回复上次主动消息或模型不联系，不能追溯断言某个具体原因；offline_reason_used表示理由已处理。旧记录不补造诊断。首次开启/刷新/托盘隐藏不是立即联系的触发器。
- 公共背景准备情况复用worldContent读取已确认内容，前端仅保留世界书统计和已公开启用条目的核心参与条件文本。已公开数量不是当前可用数量，不在前端重写关键词/quiet/容量筛选，不自动公开，不发送资料到外部模型。
- 页面隐藏只暂停只读轮询，不等于组件已卸载；保存的生命周期独立管理，防止切页后busy无法复位。写失败提示只在显式成功读取后清除，失败刷新不能抹去错误。

## 验证范围

沿AGENTS第20节，只做源码、ESLint/TypeScript、Git差异和编译/包内文件核对，不运行测试、GUI、模型或真实存档；实际反馈、切页、保存与后台行为仍由用户体验。
