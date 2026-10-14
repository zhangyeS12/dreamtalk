# 旧配音失败记录与空错误字段修复（0.1.57）

日期：2026-10-12。用户点击以前失败消息的播放配音，看到服务未返回可核实结果。当前运行程序路径已核对为0.1.56；用户明确确认点击的是旧失败消息。

## 确认的问题

一次性任务通过指纹复用旧回执。旧unknown／failed任务没有可播放音频，也不重新提交生成，因此仍显示旧错误；不是这次正在生成。新增reused响应标记和针对旧失败消息的明确提示，原防止重复收费边界不变，新回复仍独立登记新任务。没有删除旧回执或重发旧消息。

静态检查另发现新本地桥接的正常状态包含error:null，而原通用JSON解析器把只要存在error字段都当作失败。这会误拒正常接纳／运行结果。修复为null不代表错误；本地任务状态单独读取state和error，failed状态仍明确失败。其他供应商非空错误和RetCode失败仍拒绝。不运行自动化或模型测试，不以静态修复证明新回复已出声。

## 当前诊断边界

只读核对当前程序与监听：检查时7861未见监听。未启动、终止或重启服务；用户可在配音设置检查并启动服务。尝试读取最近配音任务元数据时定位的数据库返回no such table: speech_jobs，未取得任务行，不能据此解释新任务。已从打包PYZ静态确认当前冻结的配音模块含0.1.56后台任务代码，非仅检查旁置源码；没有读取私聊、世界书、音频或密钥内容。当前无需更多存档诊断解释已确认的旧回执现象。

## 检查与交付

前端ESLint／TypeScript与Python Ruff／格式通过，完整build-only构建退出0，网页和Tauri release编译完成，EXE 0.1.57。保留既有大chunk、STATIC_VCRUNTIME弃用、jieba转义与PyInstaller可选依赖警告，不因此推定运行兼容。没有运行应用、安装器、迁移、自动测试、真实模型／付费服务，也没有修改存档、系统启动或当前已运行包。公开版仍v0.1.53，本轮未提交或发布。

本地入口：artifacts/portable/voices-0157/dreamtalk/dreamtalk-desktop.exe，ZIP：artifacts/portable/voices-0157/dreamtalk.zip；构建日志：artifacts/build-voices-0157.log，最终摘要：artifacts/voices-0157-delivery.json。
