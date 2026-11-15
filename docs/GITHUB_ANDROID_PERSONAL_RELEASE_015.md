# 安卓0.1.5个人测试发行

[发布页](https://github.com/zhangyeS12/dreamtalk/releases/tag/android-v0.1.5-personal.1)；Release ID 445806143；公开预发布、非Latest。标签android-v0.1.5-personal.1绑定独立安卓提交163f9445b73459cebb9a6dbda2895e8b29bc87de，分支codex/android-hotfix-0.1.5；没有推送Windows main或修改既有标签／发布／更新频道。

用户明确要求发布到GitHub供手机验证，并保留未主动要求时不走CI的指令。本轮使用版本匹配的SkipCI回执及跳过标记，没有运行或等待CI，没有修改共享工作流。

APK为170350539字节，SHA-256 d43b05a273b2fdf5b9c84b3fc3b704035d314f23bf0b053898203bc976fc95b8。原发布证书及分SDK的v1／v2／v3、16KB对齐、Core398模块对应、固定BGE／ORT／五项许可、Logo与启动依赖通过。四附件远端和禁用个人curl配置的匿名完整下载均核对一致。

327项前端及59项移动宿主离线检查通过。首次移动宿主检查的一项Windows临时ready文件读取冲突保留在本轮日志，打包结束后全新隔离目录串行复核通过。两个bootstrap文件仅改三个应用版本字符串，其余396个Core源文件不变；Windows完整工作区和远端隔离核对通过。

发行APK未在本轮执行，没有真实模型、凭据或用户存档检查。既有本机首页的用户反馈及原生合成检查不能代替手机验证。

具体证据与当前验收统一见[状态清单](PROJECT_STATUS.md)和 ../artifacts/github-android-personal-015/。源码标签中的文档保留构建前快照，当前状态以本页及状态清单为准。
