# 安卓封面图片处理

角色卡、卡包和世界书沿用原有图片 HTTP 接口与本机素材存储。选图后直接上传到应用内 Core；图片不发送到模型或外部服务。上传原图后才进入裁剪，原图保留供重新裁剪，保存沿用原有归属、摘要和版本校验。

## 格式与边界

接受静态 JPEG、PNG、WebP，每张最多 10 MiB、2000 万像素，单边最多 10000 像素。EXIF 朝向在裁剪前处理，动画和损坏图片继续拒绝。裁剪仍输出 WebP：角色卡 1200×757、卡包 900×1286、世界书正背面 980×1430／书脊 210×1430。透明度和图片归属契约不变。

## 安卓素材发布

[素材存储](../services/core/src/livingworld/infrastructure/packages/asset_store.py)在 Android 使用同一私有目录下的文件锁序列化发布者。先完成临时文件写入、刷新及同步，再在锁内重新校验目标；不存在时原子重命名，存在时核对原文件。读者不会看到半张图片，既有损坏文件不会被静默覆盖，失败会清理暂存文件。非 Android 环境继续使用既有硬链接发布逻辑；正式 Windows 仓库不受安卓目录修改影响。

这解决 Android app-data 内硬链接被系统拒绝的问题。操作仍限于应用自有的哈希素材目录，不增加存储权限、任意路径入口或数据库迁移。

## 编解码复用与维护

既有 Pillow 11.0.0 的 Android 构建只有 JPEG／PNG 所需组件，[Chaquopy 上游配方](https://raw.githubusercontent.com/chaquo/chaquopy/master/server/pypi/packages/pillow/meta.yaml)未包含 WebP。WebP 既是允许的上传格式，也是全部裁剪的输出格式，因此需要补齐实际编解码，单改错误提示无法完成流程。

继续复用 [Pillow 11.0.0 的原始 WebP 扩展](https://github.com/python-pillow/Pillow/blob/11.0.0/src/_webp.c)，静态链接 [libwebp 1.6.0](https://github.com/webmproject/libwebp/tree/v1.6.0)。不引入新的图片框架，不改用平台特有的像素／EXIF 语义。Pillow 按 HPND、libwebp 按 BSD-3-Clause 分发，保留 libwebp 的专利授权和作者名单。

[构建脚本](../scripts/build-android-webp.py)使用固定源码摘要、NDK 27.2.12479018、API 24、ARM64 及对应 CPython 3.13.16 头文件，只生成缺少的 PIL/_webp.so。现有 Pillow 扩展保持；版本、来源、摘要与四项许可载于[资源清单](../plugins/android/src/main/assets/third-party/image-codecs.json)，许可正文随 APK 分发。

维护成本是固定 C 扩展的重编译与 Android 实测。升级 Pillow／Python／NDK 或 libwebp 后需同步构建、审核摘要和许可，再核对实际上传、解码、裁剪及重新读取；不能仅凭桌面 Pillow 可用就认定 Android 可用。

## 工程入口

- [构建前校验](../scripts/prepare-mobile-images.py)：固定扩展和许可资源。
- [APK 图片门禁](../scripts/verify-mobile-images.py)：实际嵌套载荷、摘要、Python 动态链接及四项许可；由现有 APK 门禁调用。
- [图片处理回归](../tests/core/test_cover_image_processor.py)：真实解码、输出、透明度、朝向和拒绝边界。
- [安卓发布语义回归](../tests/persistence/test_mobile_asset_publish.py)：在 Windows 使用替代锁验证并发、不可覆盖与中断清理；真实 flock 和系统权限另由独立合成数据 Android AVD 验证。
- 当前构建、运行、发布及用户验收结果只维护在[状态清单](PROJECT_STATUS.md)。
