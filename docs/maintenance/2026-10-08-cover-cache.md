# 0.1.45 封面 Blob URL 缓存回收

日期2026-10-08；正式仓库D:\LivingWorld，分支codex/world-archive，起始HEAD85f8035。用户先要求仅检查，源码确认问题后明确授权“优化”。继承未提交的0.1.43世界独立模型与0.1.44角色移动，本轮未提交／推送／公开发布；公开Release仍v0.1.42。

## 问题与修复

useWorldCovers原先仅在卸载或client／world／enabled变化时释放URL；保存新封面只更新元数据，旧world_id:digest仍留在Map。频繁替换图片会积累无引用URL，关闭封面编辑器或刷新书架不会卸载此hook。此结论来自源码，没有读取真实存档或实测内存。

现在在React外观提交后，保留当前显示的URL及当前封面三面仍需的digest，释放并删除其余缓存项。新图加载期间保留旧显示资源，新外观／文字回退提交后回收旧项；共享digest继续复用。元数据保存／刷新的sequence同时约束图片异步结果，过时任务不能创建URL、写错误或覆盖外观；取消／卸载的abort与最终释放保持。

只修改apps/web/src/useWorldCovers.ts的资源生命周期，无新依赖、Core／协议／数据库行为或磁盘资产清理。同步Desktop五处版本为0.1.45，以区分体验包；继承0039迁移但未执行真实迁移。书架与设置手册都复用该hook，编辑器自己的预览URL管理保持。

## 检查与交付

ESLint／TypeScript与Git差异格式通过；仓库文档935个本地目标、0断链。沿既有脚本执行`.venv\Scripts\python.exe scripts\build-portable.py --build-only --output-name cover-cache-0145`，退出0；Core、Web与Desktop完成编译，未执行脚本的smoke／测试分支。使用受控构建权限读取web/dist，避免此前沙箱已确认的路径拒绝。

完整目录artifacts/portable/cover-cache-0145/dreamtalk及同级dreamtalk.zip已交付；EXE文件／产品版本和五处源码版本均0.1.45，256个Core源码与包内逐文件字节一致，包含继承的0039迁移。随包文档584个本地目标、0断链。最终文件清单及SHA256见artifacts/cover-cache-0145-evidence.json和包目录外部SHA256SUMS.txt；构建日志为artifacts/cover-cache-0145-build.log。程序未启动，旧0.1.43仍被已批准自启动使用，本轮不改注册或启动／停止应用，也未删除旧体验包。

构建保留既有告警：三个Vite资源块超过500kB，Tauri的STATIC_VCRUNTIME弃用，PyInstaller可选hidden import的tzdata／pysqlite2／MySQLdb未找到，以及jieba正则的转义SyntaxWarning。默认沙箱下源码检查的Python launcher打印过定位提示，命令仍退出0；受控完整构建退出0。没有新增依赖或据此假报运行故障，告警不等于运行兼容验收。

未新增或运行自动化测试、浏览器／桌面smoke、真实模型调用或用户存档诊断，不宣称运行内存已实测下降。

## 待用户验收与建议

在同一次书架停留中频繁替换不同图片并保存、移除背面／书脊、改为文字封面并保存，再刷新；核对其他世界与三面共用图片仍正常、连续保存不会出现旧图回写或失效图片。实际内存变化及新版运行由用户验收，前序移动／模型与共同联系验收范围不扩大。没有新的产品决定需要确认；建议先使用这个完整新包体验，需开机使用新版时在设置显式更新启动位置。
