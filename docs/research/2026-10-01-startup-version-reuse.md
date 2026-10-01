# 更新启动位置与桌面版本：成熟实现调查

2026-10-01，实施前核对官方文档、GitHub插件目录及Cargo.lock解析的本机发布源码；沿用已有组件，不引入新的启动框架或注册表实现。

- [Tauri官方autostart文档](https://v2.tauri.app/plugin/autostart/)提供Rust的enable/disable/is_enabled以及启动参数。
- [官方插件源码目录](https://github.com/tauri-apps/plugins-workspace/tree/v2/plugins/autostart)：实际使用tauri-plugin-autostart2.6.0，Apache-2.0 OR MIT。发布源码的Builder在setup时通过current_exe确定当前程序路径；现有应用已经注册--background参数。
- 传递依赖auto-launch0.5.0，MIT，原仓库[zzzgydi/auto-launch](https://github.com/zzzgydi/auto-launch)。本机发布源码src/windows.rs的enable覆盖同名Run项，is_enabled只判断登记存在及StartupApproved状态，不比较登记路径与当前程序。这解释了原应用“已经开启便跳过enable”为什么一直保留旧包。
- Tauri2.12.0现有AppHandle.package_info().version提供桌面版本；std::env::current_exe提供当前程序位置。界面将其标为当前运行信息，不伪装为对系统登记目标的读取。

选择：用户在开启自启动时每次显式保存均调用已有manager.enable；即使开关未改变，也允许保存。关闭分支沿用manager.disable。读取/刷新只调用is_enabled；不在启动时静默登记或改变默认关闭行为。托盘配置先写临时文件再进行注册，落盘失败明确反馈部分保存；无法通过插件恢复未知旧路径时不声称完整回滚。前端同步锁和请求序号避免重复保存及卸载后旧结果覆盖。

桌面配置、Cargo和npm桌面workspace版本同步为0.1.1；Core及协议仍0.1.0，storage identifier不变。无需数据库迁移、新依赖或额外模型任务。既有许可证随新包保留。此次只在Windows当前便携路径范围内实现并静态审阅；系统登录、实际保存和任意迁移路径的运行验收仍由用户负责。
