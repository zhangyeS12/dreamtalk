# Windows 更新入口调查

日期：2026-10-08；实现前调查，源码基线85f8035，Desktop0.1.45。

| 来源／版本／许可 | 已核对行为 | 采用与取舍 |
| --- | --- | --- |
| [Clash Verge Rev v2.5.7 更新 hook](https://github.com/clash-verge-rev/clash-verge-rev/blob/v2.5.7/src/hooks/use-update.ts)／[原生更新器](https://github.com/clash-verge-rev/clash-verge-rev/blob/v2.5.7/src-tauri/src/core/updater.rs)，GPL-3.0 | 开关控制检查，后台缓存安装包及版本，前台提示立即安装／稍后，旧缓存淘汰；配置有签名公钥与多个端点。 | 参考提示与缓存生命周期，不复制或并入GPL源码。dreamtalk只在点击更新后下载；不自动预下载，也不采用第三方代理端点。 |
| [Tauri v2 updater 官方文档](https://v2.tauri.app/plugin/updater/)／[插件2.13.1源码](https://github.com/tauri-apps/plugins-workspace/tree/updater-v2.13.1/plugins/updater)，MIT／Apache-2.0 | 公钥校验安装包；Windows使用完整NSIS/MSI，静态JSON包含版本、说明、日期、平台URL与签名；默认仅升到更高版本。Windows安装分支会直接退出宿主。 | 新增精确固定tauri-plugin-updater=2.13.1，使用原生命令封装，不开放JS任意下载／安装API。不自造签名验证或把便携ZIP当标准更新包；显式先排空并关闭Core。 |
| [Tauri Windows安装文档](https://v2.tauri.app/distribute/windows-installer/)／本机tauri-cli2.11.4生成NSIS模板，MIT／Apache-2.0 | currentUser安装、原目录覆盖、旧文件清单与快捷方式、前后安装hook；默认并非原子回滚事务。 | 复用标准安装器，完整Core资源打包；hook修复官方入口、在更新后前台重启。保留恢复包至新版真实就绪，失败不谎报已清除旧版本。 |

依赖理由：现有Tauri不包含下载、Minisign校验和Windows安装器派发，官方插件直接解决这三个缺口。Tokio启用macros只用于下载大小／期限取消选择；不增加应用框架、数据库迁移、模型API或后台云服务。实际插件许可证随安装包提供。更新签名不是Windows Authenticode证书，不保证消除SmartScreen提示。

更新频道使用固定`update-preview` Release资产`windows.json`，与版本Release中的签名安装包分开。发布每个新版本时同时替换频道资产；只推源码或上传普通ZIP不会触发更新。预发布不依赖GitHub latest对预发布的筛选规则。

## 0.1.48修复补充调查

锁定的tauri-cli2.11.4在[打包源码](https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.4/crates/tauri-bundler/src/bundle.rs#L119)中先修改主程序安装类型、结束后恢复构建文件。因此生成清单必须针对实际装入NSIS的字节，不能仅查看构建输出；未引入新版CLI或关闭该标记。复用[官方7-Zip26.04](https://www.7-zip.org/download.html)静态读取实际安装器并逐文件核对，[许可](https://www.7-zip.org/license.txt)为LGPL／BSD及unRAR约束，仅作为独立构建工具，不随产品分发。旧安装清单修复按已确认的完整原清单和主程序摘要钉住范围，不放宽运行时校验，见[修复记录](../maintenance/2026-10-08-update-manifest-fix.md)。
