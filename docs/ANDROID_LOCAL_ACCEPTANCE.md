# 安卓本机验收

日常改动在电脑验收，等用户明确要求再发布。默认不走 CI，不修改发行版本、Windows 应用或 GitHub 附件。工程端负责本地构建、离线检查与排错，用户负责界面和实际聊天效果验收；默认不使用 computer-use 自动巡检界面。

## 使用入口

项目根目录的[安卓本机验收.cmd](../安卓本机验收.cmd)可双击打开可视安卓模拟器和真正的安卓应用。测试包与源码指纹一致时直接复用；源码已有改动则先在本地更新。模拟器启动或更新需要一点时间，重复点击会提示已有启动任务。

[更新安卓验收.cmd](../更新安卓验收.cmd)强制重新构建一次再打开。它使用独立的本机测试证书和输出目录，不接触手机发行私钥，不递增发行版本，也不上传文件。界面显示的应用版本仍沿现行版本，具体本机源码和包摘要以本机回执为准。

应用退出后再打开会保留测试世界、内容和配置。关闭模拟器窗口即可结束这个虚拟设备；下次双击入口会重新打开。入口不清除数据，也不会通过卸载处理安装失败。

已准备的内置校园示例可用来检查通讯录、角色档案、阵营、地点、世界书与设置。真实聊天需要用户在此模拟器的应用内配置 API。它与 Windows、手机的数据和凭据互相独立，工程检查不会复制现有凭据。

## 实现边界

- 使用已有 Android Emulator 37.2.13、Android 15／API 35 Google APIs x86_64 revision 9 镜像，通过镜像的 ARM64 翻译层运行同一 ARM64 应用。只调用本机已有 SDK 工具，不引入新框架或依赖，不复制其源码；许可沿 SDK 随附许可／NOTICE。
- 复用项目 Tauri v2、Chaquopy 和 Gradle 构建。构建实际生产前端、Rust、Kotlin 与 Core wheel，保留正常自启动、通知、Keystore 和系统文件桥接；不向生产前端注入测试宿主。
- 模拟器显式使用已有 SDK 的 host 图形后端（电脑显卡），保留禁用客体 Vulkan 的设置；仅影响电脑上的虚拟设备，不改变 APK、手机渲染或视觉效果。启动期模拟器宿主进程退出时立即停止等待，并只记录退出码、阶段和图形模式，不自动清除数据。具体故障证据与兼容性检查见[状态清单](PROJECT_STATUS.md)。
- 使用固定独立 AVD DreamtalkLocalAcceptance001、serial emulator-5580、独立 ADB 服务端口。操作前校验 qemu 标志和 AVD 名称，拒绝实体设备及其他模拟器。覆盖安装使用保留数据模式，不包含 wipe-data、清除应用数据或自动卸载。
- 测试包路径固定为 artifacts/android-local/dreamtalk-android-local.apk，使用仅供本机的测试证书。该包不作为手机发行包，手机继续沿既有发行证书更新。
- 构建前后核对运行源码指纹；源码中途变化不替换上一个验收回执。打开前核对包摘要和源码；签名、16KB 对齐、原生依赖闭包、Logo、迁移及隐私载荷检查继续执行，结果写入本机目录，不覆盖发行记录。
- profile 与签名保存在忽略目录 build-tools/local-acceptance，通过现有已验证的 ASCII 工具路径别名访问。它不使用 Windows dreamtalk 的数据目录。
- 工程自动化不复用用户后续的实际聊天、API 配置或存档作测试。真实模型调用和数据诊断须有对应具体授权。

## 源码与检查入口

- scripts/android-local.py：启动锁、独立设备身份、源码指纹、构建回执、覆盖安装和启动。
- scripts/build-android-local.ps1：本机构建／签名／载荷核验，不调用发行脚本或 CI。
- scripts/verify-mobile-apk.py --report：允许核验结果写入独立本机目录，原发行默认行为保持。
- tests_mobile/test_android_local_entry.py：拒绝错误设备、篡改包、越界回执及构建中途源码变化等离线回归。
- artifacts/android-local/build-receipt.json：当前本机包、构建时间、源码指纹和摘要；apk-verification.json 与 logs 保存工程检查。
- artifacts/android-local/setup/：本轮初始化合成世界的检查记录；不把这些初始化工具当日常读取用户数据的入口。

官方机制参考：[模拟器图形后端](https://developer.android.com/studio/run/emulator-acceleration)、[模拟器命令行](https://developer.android.com/studio/run/emulator-commandline)、[ADB 安装及启动](https://developer.android.com/tools/adb)。复用理由是已安装官方工具可直接运行实际 Android 包，Python 标准库和 PowerShell 已足够完成入口，不需要引入额外启动器框架。

## 验收边界

本机可以验收应用启动、界面、正常数据保存、聊天流程和 Android 系统集成。模拟器不能证明 vivo 的真实 ARM 性能、耗电发热或 OriginOS 的省电／后台策略，这些到用户安排手机阶段时再检查。当前构建和实际检查结果只见[状态清单](PROJECT_STATUS.md)。

## 固定检索合成验证

工程使用独立 DreamtalkRecallCheck20261108／emulator-5582 与 app.livingworld.recallcheck 测试沙盒，仅在获得当轮具体模型授权后运行 scripts/offline-recall-benchmark.py。该脚本明确要求模型运行开关，只含三条合成记忆和一个问题，不读用户世界或配置；测试沙盒断网，结果和完整应用启动证据单独保存。日常用户入口继续使用 DreamtalkLocalAcceptance001，用户后续内容不进入工程自动化。

新本机包已包含固定 BGE 检索资源；打开原验收入口自动按摘要安装，保留验收数据。模型抽样一致不等于真实 API 长聊天、手机内存／耗电或后台策略已经验收，当前证据只查状态清单。
