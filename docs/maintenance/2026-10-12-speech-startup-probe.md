# 本地配音启动前检查超时修复（0.1.58）

日期：2026-10-12。用户已选择部署模型目录，点击检查并启动后看到本地服务20秒未就绪。

## 证据与原因

只读核对运行入口为0.1.57，所选目录为已有独立IndexTTS环境。检查时没有配音Python进程、7861监听或local-speech.log。两次仅TCP连接诊断没有发送API／生成请求，端口返回Windows10061拒绝连接，其中一次用时2050毫秒。

原native health()把整个请求期限设为2秒，启动前ensure()先调用health()。Windows返回拒绝连接需要略超过2秒，计时先终止请求；错误被映射为speech_local_start_timeout并显示20秒等待。该分支尚未创建Python进程，因此不是模型权重加载慢，也没有启动日志。证据支持这一启动前期限竞态；不把只读连接核对说成新版运行验收。

## 修复

本机健康检查改为连接5秒、整个请求10秒，让正常拒绝连接得到处理并进入启动分支。真正的检查超时与其他网络错误分别返回probe_timeout／probe_failed，不复用20秒启动就绪提示。已成功创建子进程后的20秒就绪期限保持；仍只在确认未占用服务时启动，不抢占端口、终止外部进程或自动重复生成。

没有新增依赖、下载模型、改代理／防火墙／开机入口、读取聊天或启动服务测试。沿现有Reqwest／Tokio和此前批准的可选模型生命周期。

## 交付与验收

Rust格式／cargo check、前端ESLint／TypeScript通过，完整build-only构建退出0，网页和Tauri release编译完成，EXE版本0.1.58。保留既有大chunk、STATIC_VCRUNTIME弃用、jieba转义与PyInstaller可选依赖警告，不因此推定运行兼容。没有运行自动测试、应用／安装器、真实迁移、模型或付费服务。用户需退出旧版后打开新包，在设置检查并启动并确认服务就绪，然后用新的角色回复验收音频。公开版仍v0.1.53，源码未提交或发布。

本地入口：artifacts/portable/voices-0158/dreamtalk/dreamtalk-desktop.exe，ZIP：artifacts/portable/voices-0158/dreamtalk.zip；构建日志：artifacts/build-voices-0158.log，最终摘要与静态门禁：artifacts/voices-0158-delivery.json。
