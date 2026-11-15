# dreamtalk 安卓 0.1.6 手机体验

本次修复角色卡、卡包、世界书选图后的上传失败，以及 WebP 图片和裁剪结果的编解码。安装包为 ARM64，最低 Android 7.0，包名及原安卓签名保持，按正常方式覆盖安装旧个人测试版即可。

[下载 APK](https://github.com/zhangyeS12/dreamtalk/releases/download/android-v0.1.6-personal.1/dreamtalk-android-0.1.6-arm64.apk) · [发布页](https://github.com/zhangyeS12/dreamtalk/releases/tag/android-v0.1.6-personal.1)

## 本次验收

分别给角色卡、卡包和世界书选择一张图片，调整裁剪后保存；退出设计器再进入，并重启应用，观察图片是否仍然显示。聊天沿用原有体验，现有存档和 API 配置沿原位置读取。

支持静态 JPG／PNG／WebP，每张最多 10 MiB、2000 万像素，单边最多 10000 像素。图片只在手机内处理，不发送到模型。

工程端已在独立合成数据 Android 环境核对同一修复的上传、真实裁剪、保存与重启回读；发行包的真机及覆盖升级仍由本次手机体验确认。当前版本、检查及验收边界以[状态清单](PROJECT_STATUS.md)为准。
