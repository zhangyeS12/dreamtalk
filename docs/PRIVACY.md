# dreamtalk 隐私说明 / Privacy information

本说明用于免费代码签名申请，描述项目的数据处理方式；尚未由签名机构审核，不表示已获得 SignPath Foundation 证书。

## 本机保存

dreamtalk 在本机保存世界、角色资料、身份、聊天、记忆、素材、音色与应用设置。完整备份及用户主动导出的文件可以包含这些私人内容；用户选择文件位置和是否交给他人。模型权重和环境与应用存档分开。

API 密钥由桌面宿主通过本机安全凭据存储管理；配置可以保存不透明的密钥引用。完整存档备份不包含 Windows 安全凭据中的密钥正文。

## 模型与联网功能

用户配置模型服务及服务地址。发起聊天、生成资料、配音或图片分析时，相应请求和获准的相关资料会发送给用户选择的服务。例如云端配音可能需要台词和参考录音，图片分析需要选中的图片。后台活动、主动联系、世界动态等任务必须先按对应设置取得用户授权；开启后可以在应用运行期间提交获准任务。

联网研究、图片搜索或远程素材下载会访问对应来源；本地模型和环境准备可能下载所需组件与权重。应用更新检查和更新下载访问 GitHub。目标网站或服务可以收到正常连接产生的 IP 地址和请求信息，其数据处理与收费适用该服务的政策。把服务地址指向自己运行的本机服务与使用远程服务，具有不同的数据流向。

dreamtalk 不提供开发者共享模型账号，不自动把聊天或存档上传给项目维护者。项目没有面向维护者的自动聊天上传或自动诊断日志提交流程。用户在公开问题页面主动粘贴内容属于用户自己的披露。

## 删除和备份

用户可以使用应用已交付的删除或导出入口管理内容。存档保护入口随 0.1.78 交付；旧安装包不一定具备新备份、恢复或清空入口。真实恢复、跨版升级和故障场景仍待用户验收。

应用内明确清空的设计保留不含聊天正文的调用、费用、预算保护回执，避免用清空剧情重置已知用量。独立备份、用户另存的导出文件和远程服务已经接收的数据，具有各自的删除范围。

## 第三方服务

用户选择的模型、搜索、素材与下载服务，以及操作系统的安全凭据与更新组件，适用各自的政策。项目维护者无法替代这些服务承诺数据保留期限或删除结果。SignPath 申请人的姓名、邮箱和条款同意在 SignPath 申请页面由申请人提交，不进入 dreamtalk 应用或发布载荷。

## 联系

项目与问题入口：[dreamtalk repository](https://github.com/zhangyeS12/dreamtalk)、[Issues](https://github.com/zhangyeS12/dreamtalk/issues)。请勿在公开问题中填写 API 密钥、私聊或存档正文。

## English summary

dreamtalk stores worlds, conversations, memory, media, and configuration locally. Users choose their model services. Authorized chat, creation, speech, image, and enabled background tasks can transmit their relevant inputs to those services. Search, media downloads, model setup, and update checks contact the corresponding services; updates use GitHub. Provider policies apply to those connections.

The project does not automatically upload conversations, saves, or diagnostic logs to its maintainers. API secrets are managed through local OS credential storage and are excluded from save exports. Backups and exports can contain private content. Minimal non-content cost and admission receipts are retained by the explicit erasure design. Third-party copies and separately exported files have separate deletion scopes.
