# 项目名称与兼容标识

正式公开名称为 **dreamtalk**（小写）。README、网页标题、应用标题、Tauri 产品名和新构建产物使用此名称。项目计划发布至 GitHub；此文档不代表远程仓库或发行版已经创建。

以下旧标识暂时保持稳定，以便现有开发数据、会话与导入内容继续可用：

| 标识 | 保留原因 |
| --- | --- |
| Tauri identifier `app.livingworld.desktop` | 应用数据与 WebView 存储按 identifier 定位；改动需要明确迁移。 |
| Python import namespace `livingworld` | Core、迁移脚本、测试和已生成包的导入路径。新分发名与命令为 `dreamtalk-core`，旧 `livingworld-core` 命令保留为别名。 |
| Windows Credential Manager service `LivingWorld` | 旧 SecretRef 对应的密钥仍可读取；不把密钥复制到配置文件。 |
| 浏览器开发数据目录 `%LOCALAPPDATA%/LivingWorld/development` | 现有开发数据库保持原路径。 |
| `livingworld.*` localStorage keys | 保留用户已选世界和聊天额度。 |
| 已持久化的协议、导入兼容 namespace 与数据格式标识 | 改名不能改变世界事实、旧内容包或重放语义。 |

仓库本机路径 `D:\LivingWorld` 也暂时保持不变。路径、应用数据标识和凭据 namespace 的统一迁移必须单独设计与验证；不得通过简单字符串替换导致用户数据不可见。Stage 0 的 W-001 原始研究报告和 Architecture Review 001 是历史归档，保留当时的 LivingWorld 名称及原文。

开源许可证为仓库根目录的 [Apache License 2.0](../../LICENSE)。正式公开前仍须核查 Git 历史中的秘密、第三方素材和发布包；当前未配置 GitHub 远程地址，也未声称已发布。
