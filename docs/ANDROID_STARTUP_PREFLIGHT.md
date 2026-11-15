# 安卓启动前检查与诊断

当前交付、工程检查及手机验收统一见[状态清单](PROJECT_STATUS.md)。

## 现场与证据边界

用户反馈已安装的 0.1.3 能进入 dreamtalk 页面，但提示“暂时未能打开／启动失败”。复制出的诊断为 core_running=false、startup={}。这说明旧诊断没有给出失败原因，不能只凭空对象断定手机具体异常。

隔离临时目录中使用父目录别名，复现 save_link_rejected、Core 线程未创建、复制诊断仍为空的组合，见[复现回执](../artifacts/android-013-startup-investigation/prethread-reproduction.json)。路径来自原生 Context，却被当作普通存档路径逐级检查，可能在 Core 线程启动前失败。此情形与用户现象一致，但未读取手机底层路径，不能把模拟归为真机确诊。

Android 系统存在应用数据路径别名的源码背景可参考 [AOSP Zygote](https://android.googlesource.com/platform/frameworks/base/+/bba5ed7765e4b843877513cd9e518f85da0e43cc/core/jni/com_android_internal_os_Zygote.cpp)。不据此推定 vivo 当前路径布局。

## 修复契约

- Kotlin 只规范化 Android Context 提供的 filesDir，再拼接固定 dreamtalk 子目录；Python 在同一可信宿主边界仅解析父目录。物理存储及稳定身份保持，不移动真实存档。
- 不解析掉托管根或其子目录中的链接；save_safety.plain 的拒绝规则保持。托管根与备份根的链接负向回归仍必须失败。
- 启动前的目录、安全存储、存储准备、存档检查、模型配置和 bootstrap 写入有固定阶段；Core 导入／运行与就绪超时分别诊断。只保留固定错误码、异常类别和项目源码位置，不保留异常原文、完整路径、配置、正文或密钥。
- 复制诊断不再依赖读取安全存储或初始化目录；未开始启动时明确记录 not_started，不返回空对象。新的成功启动清除旧失败，未知收费结果和模型重发规则不变。
- 前端对可识别的启动错误提示复制诊断，不回显任意原生错误文字。

源码入口为 bootstrap/mobile_host.py、原生 CoreRuntime.kt／ExamplePlugin.kt，以及 mobile/host.ts。复用现有 pathlib、traceback、Python 标准库及 Android File API，无新增运行依赖或框架。

## 本地工程检查

33 项移动宿主回归通过，使用源码树外合成存储、回环服务并阻止外部网络。覆盖父目录别名实际启动、内部链接拒绝、安全存储故障、配置故障、诊断脱敏、重试清理及超时。6 项前端提示回归、TypeScript、Ruff 与离线 Kotlin 插件编译通过。

记录见[移动宿主](../artifacts/android-013-startup-investigation/mobile-startup-regression.json)、[前端](../artifacts/android-013-startup-investigation/frontend-regression.log)和[Kotlin](../artifacts/android-013-startup-investigation/kotlin-compile.log)。既有 Kotlin／Gradle 弃用提示保留。

源码修复阶段未运行 CI、生产 APK、已安装应用、真实模型或真实存档；后续用户已授权快速发布，交付结果以状态清单为准。此修复已进入当前交付 APK，具体版本和分发证据见状态清单；手机启动反馈以状态清单为准。
