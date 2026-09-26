# dreamtalk Windows 便携版

将整个 `dreamtalk` 文件夹解压后运行 `dreamtalk-desktop.exe`。请勿只复制 exe：`core/` 文件夹包含随附的 Python Core 和迁移脚本。使用 Windows 10/11，并确保系统有 WebView2 Runtime。无需另行安装 Python、uv、Node 或 Rust。

应用数据保存在本机用户的 Tauri app-data 目录，不会写入解压目录。此版没有代码签名或自动更新；Windows 可能显示未知发布者提示。请先在非重要数据上试用，并保留自己的应用数据备份。

首次打开可创建世界并在设置中配置自己的模型服务。配置会要求提供可信的输入 Token 上限；程序不会在启动或保存配置时测试密钥，也不会自动产生付费调用。角色对话需要可用的模型服务和用户自己的 API 凭据，可能产生服务商费用。

本地便携版不是 GitHub 正式发布。项目源码采用 Apache-2.0 许可证；发布前仍需完成产品功能与用户验收。
