# Android 实现与构建

## 来源与边界

正式 Windows 源码来源为 D:/LivingWorld。`source-snapshot.json` 记录捕获时的 HEAD、工作区文件、时间与摘要；这是包含当时未提交改动的独立快照，不代表 Windows 最新发布版本，也不跟随其他任务自动同步。后续明确授权的增量同步及保留的安卓差异见[同步说明](ANDROID_WINDOWS_SYNC.md)，当前源码与已发布 APK 的边界见[状态清单](PROJECT_STATUS.md)。没有改动 Windows 源码、真实存档、模型配置或已安装应用，安卓源码已通过独立分支和精确提交 CI 管理，没有推送 Windows 主分支；源码标签、发布及验收边界见状态清单。

保留 React／TypeScript／Vite → 版本化 HTTP／流式响应 → Python Core → SQLite WAL／FTS5 与 Alembic。Android 宿主使用 Tauri 及本地插件内嵌 Python，Core 只绑定本机回环。密钥在 Kotlin 层通过 Android Keystore AES-GCM 加密，Python 只在内存凭据会话中取得密钥；模型配置文件只包含引用。安全存储实现已编译，仍待真机验证。

入口：`apps/web/src/mobile`、`apps/mobile/src-tauri`、`plugins/android/src/main/java/ExamplePlugin.kt`、`services/core/src/livingworld/bootstrap/mobile_host.py`。原有 Core 与 API 客户端代码保留；Android 快照另外修正了导入初始地点的空 UUID，以及未启用联网检索时不应强制导入 ddgs 的问题。

后台运行默认关闭，未开启时退到后台仍设置维护屏障；用户明确开启并授权通知后，应用级 Core 和原生前台会话可继续处理已开启的世界任务。通知仅对应已提交消息，沿用费用和中断恢复契约。设置迁移、后台与文件操作详见 [安卓设置与后台联系](ANDROID_SETTINGS_MIGRATION.md)，交付及验收边界见状态清单。

## 性能取舍

使用简单列表与聊天页面，不挂载三维书架／关系网，不预加载视觉资源；禁用装饰动画、毛玻璃和阴影。历史 Markdown 正文使用 memo，沿用原分页和可见消息限制。聊天、配音和视觉沿 API 入口；固定 BGE 检索资源随包分发，用于保留与 Windows 相同的记忆检索规则。Python 冷启动、大量历史排版、图片解码和并发群聊仍可能占用手机资源，不能用桌面浏览器结果证明手机流畅。

固定语义检索经原生 CPU 后端运行，每小批最多四段、ORT 两线程和 NumPy 一线程，保留原有超时／故障关键词回退；依赖、许可与模型摘要见[聊天一致性](ANDROID_CHAT_PARITY.md)。配音／视觉 API、系统文件导出和完整存档的安卓适配状态统一见状态清单；不能把手机的验证缺口登记为 Windows 未实现功能。

## 依赖选择

| 组件 | 使用版本与许可 | 复用理由／维护点 |
| --- | --- | --- |
| Tauri | Cargo.lock 中 2.12.5，MIT／Apache-2.0 | 延续既有宿主和 IPC；需验证 Android 生命周期 |
| Chaquopy | 17.2.0，MIT | 在 Android Gradle 中嵌入现有 Python Core，避免重写业务层；原生 wheel 必须逐项验证 |
| Python | 3.13，PSF | 与现有代码语法和 Core 兼容 |
| Pydantic | 2.10.6，MIT；core 2.27.2 | Android wheel 自编译；离线回归验证而非直接假定 Windows 原生 wheel 可复用 |
| SQLAlchemy／Alembic | 2.0.54／1.20.0，MIT | 对齐当前源码的 schema 反射语义，旧依赖组合已发现不兼容并替换，未放宽 schema 校验 |
| RPDS | 0.25.1，MIT | jsonschema 的本地依赖，自编译 ARM64 wheel |
| FreeType | 2.9.1，FreeType License | 对原依赖同版本源码重新链接 16KB LOAD 对齐；不改变业务接口 |

实际 Python 依赖与自编译 wheel 摘要见 `android-python-dependencies.json`。npm 与 Cargo 版本分别记录在 lock 文件，版权说明随前端资源及 Android assets 分发。源码、版本和许可来源：

- [Tauri Android](https://v2.tauri.app/start/prerequisites/#android)
- [Chaquopy 17.2 Gradle 文档](https://chaquo.com/chaquopy/doc/current/android.html)
- [Chaquopy 许可](https://github.com/chaquo/chaquopy/blob/17.2.0/LICENSE.txt)
- [Pydantic Core 官方源码](https://github.com/pydantic/pydantic-core)
- [RPDS 官方源码](https://github.com/crate-py/rpds)
- [FreeType 固定版本源码](https://github.com/freetype/freetype/tree/VER-2-9-1)
- [Android 16KB 页说明](https://developer.android.com/guide/practices/page-sizes)

## 本机继续构建

工程环境使用 PowerShell 7、Node、Rust、Python 3.13。便携 JDK、SDK、NDK 及 wheel 在本目录的 `build-tools`；运行 `npm run android:build` 执行 Core wheel、类型检查、前端与原生编译、Gradle APK、对齐、签名和载荷检查。该命令不调用真实 API、不启动已安装应用，也不发布。

Windows NDK 链接器不能稳定处理当前中文路径，因此当前构建临时使用 `build-tools/temporary-build-location.json` 指向的 ASCII 缓存，具有专用标记和 NDK 硬链接；源码和最终 APK 留在 Android 目录。脚本先核对缓存标记。Tauri 在本机创建符号链接受限，只有确认 Rust 编译成功且错误明确为符号链接权限时，才复制已编译库并继续 Gradle；没有开启 Windows 开发者模式或修改系统权限。

体验签名文件位于 `private`，口令以当前 Windows 用户 DPAPI 加密；不应分发、提交或放入安装包。升级同一体验版应保留该签名。未来正式发行需单独确定发行签名和更新流程。

`verify-mobile-apk.py` 递归检查 APK 与 Python IMY，复用现有隐私门禁；只对同摘要的已审核公开校园模板映射容器路径。检查迁移源文件存在、测试桥接未入生产资源及全部 ELF LOAD 对齐。静态通过仍不等于 Android 运行通过。


## 启动修复与原生验证

启动库遗漏、Python 扩展显式链接、图标迁移及模拟器证据见 [修复记录](ANDROID_STARTUP_REPAIR.md)。构建脚本在复制分支中同时分发 C++ 运行库，最终 APK 门禁验证图标像素、原生依赖闭包及自编译扩展的 CPython 链接。

本次构建前的精确提交 CI 已通过。用户随后要求未主动要求时不再走 CI，因此停止等待或重跑标签重复检查；没有修改共享工作流配置或构建门禁。当前结果与验收边界见状态清单。

用户未明确要求时，工程端不主动运行或等待 CI。单次发布使用显式 SkipCI 参数和匹配版本的授权回执，保留默认门禁、共享工作流和本地编译、验签、载荷及下载核对。当前执行结果见状态清单。
