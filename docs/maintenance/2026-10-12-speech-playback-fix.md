# 本地配音播放权限修复（0.1.59）

日期：2026-10-12。用户在0.1.58窗口反馈没有声音，截图显示“声音已生成，但播放器未能开始或继续播放”。本轮修复现有播放链路并做静态／build-only交付；不生成测试声音、不调模型参数、不读音频正文、不改存档或系统入口、不公开发布。

## 已确认的配置缺口

只读进程核对确认当前Desktop与Core来自本地0.1.58目录；前轮运行旧0.1.54的快照已经过时。

`SpeechPlayback.tsx`先按权限读取已保存音频Blob，创建object URL，再交给HTMLAudioElement播放；参考录音试听也采用Blob。桌面配置此前只有 `default-src 'self'` 和允许图片Blob的 `img-src`，缺少媒体来源声明。图片权限不会授权音频，媒体来源缺省回退到default-src。这是能直接解释该播放失败的源码配置缺口；没有运行GUI、抓取WebView控制台或播放声音，不把源码判断写成已复现的运行结论。

一手来源：[MDN media-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/media-src)、[Tauri CSP](https://v2.tauri.app/security/csp/)。使用既有Tauri配置与浏览器Audio接口，无新依赖。

## 修复

- 桌面配置增加 `media-src 'self' blob:`，仅允许自身媒体和本地object URL。音频仍通过现有认证HTTP读取；不授权任意外部媒体地址，不把令牌放进播放器URL，不关闭CSP。
- 播放失败区分播放权限、自动播放限制、音频解码和加载／缓冲超时；媒体安全策略事件监听在结束、停止与失败时释放，不保留台词或URL诊断日志。
- Desktop／Tauri／Cargo及锁文件同步0.1.59。API协议1与迁移0045保持；已保存声音和单次任务回执不修改，读取ready缓存不重新合成。
- 包含前轮项目说明和提示词清理。旧Git提交／公开附件与在用0.1.58目录保留原样，新包构建到独立目录。

## 交付与验收

构建前核对既有打包脚本的测试分支，用 `--build-only --output-name voices-0159`。前端ESLint／TypeScript、版本一致性与Git差异检查通过；完整build-only退出0，Web／Rust release编译完成；源码隐私849文件、载荷1282文件均0发现，282份Core源码逐字节一致，1282项程序清单核对一致，媒体来源策略已静态核对存在于EXE；没有自动测试、浏览器／桌面smoke、真实模型或声音生成验收。

已交付新入口为 `artifacts/portable/voices-0159/dreamtalk/dreamtalk-desktop.exe`，完整ZIP为同级 `dreamtalk.zip`，构建日志 `artifacts/build-voices-0159.log`。EXE FileVersion与ProductVersion均为0.1.59；完整摘要见 `artifacts/voices-0159-delivery.json`。本轮保留已有Vite大分包、STATIC_VCRUNTIME弃用和PyInstaller的tzdata／pysqlite2／MySQLdb可选依赖警告。

用户正常退出旧窗口并打开新包后，点击原消息旁“播放配音”验收已保存声音；无需为这一播放修复重新聊天或重复生成。仍须确认真实声音、缓存重播、参考录音试听、群聊顺序及切页／失焦停止。此前模型加载／长度上限问题与本次播放权限分开，见[诊断记录](2026-10-12-speech-diagnosis.md)。
