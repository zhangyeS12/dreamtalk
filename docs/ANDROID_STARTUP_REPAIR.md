# Android Logo 与启动故障修复

## 用户现象与证据

用户在 vivo X80、OriginOS 6 上反馈：点图标立即退出，且图标仍是默认图标。没有读取用户手机、真实存档或真实 API。

对原发布 APK（0.1.0）检查确认：实际启动图标是 Tauri 默认图标；虽然源目录已有 dreamtalk 原图，Android 资源并未迁移，应用内也只渲染文字。

新建隔离 Android 15 Google APIs 模拟器，在 x86_64 宿主上通过官方 libndk_translation.so 运行原 ARM64 APK，复现同样的立即退出。崩溃为 UnsatisfiedLinkError：主库依赖 libc++_shared.so，APK 的 lib/arm64-v8a 没有该文件；它只存在于 Python 内部 IMY，无法参与原生入口加载。证据见 ../artifacts/android-startup-regression/baseline-reproduction.json 与 baseline-crash.txt。

## 修改

- 使用 Windows 原 dreamtalk Logo，经 Tauri 官方图标工具生成 15 个 DPI 图片，并配置圆形／自适应图标；移动入口使用现有 Brand 组件。固定原图保存在 apps/mobile/branding，生成器不再覆盖自己的输入。
- 修正 Windows 符号链接受限时的复制分支，同时把 NDK 的 ARM64 libc++_shared.so 放入原生目录；这是恢复 Tauri 标准打包所需依赖，不是放宽加载检查。
- 原生入口不再崩溃后，真实 Android 运行继续暴露 Pydantic Core 导入错误。自编译的 Pydantic Core／RPDS 以前沿用桌面扩展的隐式全局符号假设，未显式链接 Android CPython。现链接匹配的 libpython3.13.so，并在构建时拒绝未解析扩展符号。
- 错误诊断仅记录异常类型、模块／符号标识及源码位置，不输出异常原文、密钥或输入；复制诊断有不依赖 Python 导入成功的原生回退。
- 根据模拟器真实截图修正深色界面的系统栏对比和安全区／键盘布局，避免内容进入状态栏或手势区域。
- 版本提升到 0.1.1／1001，保留包名及体验签名，允许覆盖安装，不要求卸载。

## 验证

新增两个实际载荷回归均会拒绝原发布 APK：verify-android-brand.py 校验 15 张图标的可见像素，verify-android-native-deps.py 校验原生目录的 DT_NEEDED 闭包；只忽略 AAPT 对 alpha=0 隐藏 RGB 的等价优化。自编译 CPython 扩展的链接也进入最终 APK 门禁。

0.1.1 在隔离模拟器中通过实际 APK 安装、世界列表、从界面创建新合成世界、初始化身份、前后台恢复及强制关闭后的数据连续性；没有调用模型或产生真实 API 费用。最终运行结果和对应 APK SHA 以 ../artifacts/android-startup-regression/fixed-startup-smoke.json 为准；不能把较早候选包的运行结果套到另一个摘要。

源代码的移动宿主 12 项、前端 40 项及类型检查通过；载荷隐私、签名、16KB ELF 对齐、原生依赖及图标检查见当前交付回执。

vivo X80／OriginOS 6 的修复包实际验收、真机性能、真实 API、Keystore 真机效果仍待用户确认。模拟器使用翻译层，不能当作真实 ARM CPU 性能证据。没有修改 Windows 源码、发布或更新通道。


## 重开竞态补充

最终字节重开回归抓到 ready.json 的存在性检查与读取之间被 Core 删除／重建的竞态。现启动前移除旧标记，并对本机就绪文件的短暂缺失或未完整 JSON 重读，始终校验当前 nonce；不重试模型调用。新增两项确定性回归先红后绿，最终同 APK 连续三次强制关闭重开通过。

修复版 [0.1.1 个人测试预发布](https://github.com/zhangyeS12/dreamtalk/releases/tag/android-v0.1.1-personal.1) 的附件与匿名下载均已验证；完整证据见 ../artifacts/github-android-personal-011/completed.json。
