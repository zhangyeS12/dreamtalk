# 地点层级与角色活动范围（0.1.41）

日期：2026-10-07；正式仓库 `D:\LivingWorld`，起始／当前已提交HEAD为 `0e6f2ee`，分支 `codex/world-archive`。本轮按用户地点优化要求修改工作区；没有新的推送／Release授权。0.1.40源码已推送与本轮0.1.41未提交改动分开，公开下载仍是v0.1.37。

## 用户决定与观察条件

- 地点管理和初始位置配置移到通讯录；角色卡管理下方有“添加／编辑地点”，资料／阵营／关系网右侧增加“地点”。
- 地点有父子关系，父节点也是独立可停留地点。初始地点界定根与所有获准后代，允许子→父、子→另一后代，不能越界；具体移动沿既有日常批次执行，不增付费抽签或移动循环。
- 用户明确锁定只绑定初始地点。角色已在子地点时，锁定保存会通过Kernel立即回到初始地点，原日常／共同活动先按既有生命周期结算或中断。修改初始地点同样显式保存并放置到新根；解锁且根未变时保留合法当前位置与活动。
- 隐藏父节点限制整个分支；每个隐藏祖先都须对角色显式开放。作者可在地图看到地点；角色规划仅可选获准地点。历史已亲历信息不被删除，世界书中独立公开的文字不被本功能自动改写。
- 相遇／共同休闲必须位置ID完全相同，父子包含不是同场。原节奏、授权、持续同场去重、未回复门禁与费用规则保持。

## 实现入口

UI为 `LocationWorkspace.tsx` / `locations.css`，`WorldContent.tsx`挂载编辑器、资料中的初始地点／锁定与二维图；`ProductApp.tsx`只在设置保留自动活动和前往通讯录入口。移除未被引用的旧 `WorldLocations.tsx` / `CharacterActivitySetup.tsx`。位置读数每5秒只读刷新，隐藏通讯录时停止；保存失败保留草稿和原请求，不自动重发。

API沿v1扩展活动地点GET／POST，并新增地点PUT、角色`location-policy` PUT；目录返回当前身份下角色的稳定卡根ID、初始／当前地点、锁定和版本。新卡可通过明确保存位置创建／复用角色与私聊身份，不调用模型或发送消息。系统“家”保留且不能重命名。当前容量仍为32地点／16活动角色。

0038仅追加 authored `location_policies` / `location_character_access` / `character_location_policies`，不改旧账本或实际位置。旧角色缺少配置时从第一条canonical CharacterPlaced恢复初始地点，不以今天位置冒充初始地点；旧版已在范围外的实际位置不会在迁移时被改写，可在通讯录保存规则立即返回，之后活动只能选合法范围。

`location_rules.py`是共同判定入口。Director输出校验按角色允许ID；Kernel执行与相遇／共同活动再次核验最新规则。地点重命名通过LocationUpdated v1和CAS更新投影，角色返回使用既有CharacterPlaced v1；当前位置不变的规则修改记录CharacterLocationConfigured v1并保留活动。两种新增事件均有replay处理，作者配置在投影重建期间保留。角色本人放置记录有真实self Observation，聊天当前自身位置优先于旧活动地点。没有公开其他角色私聊或虚构玩家见证。

地点层级循环、跨世界父引用、同名、移出当前活动范围或撤销当前／初始地点的访问会被拒绝；后两项需先调整角色初始地点或保留其开放。位置保存核验presence和配置版本，重试沿同请求回执，不重复返回或创建。

复用与许可见[调查](../research/2026-10-07-location-containment-reuse.md)。具体用户操作见[地点手册](../ACTIVITY_LOCATIONS.md)。

## 本轮检查与交付

已完成ESLint / TypeScript、Core与脚本Ruff、修改Python格式检查、252份Core源码AST、3张新表的SQLite DDL编译（不连接数据库）、Git差异空白检查；源码文档链接886个本地目标／0断链。既有测试与CI保留，没有添加新测试。本轮不添加／运行自动测试，不启动应用／浏览器，不调用模型，不读取真实存档或执行其迁移，不修改自启动。位置布局、迁移、实际活动和锁定／隐藏／同场效果均待用户验收。

实际build-only成功，退出码0。新包：`artifacts/portable/locations-0141/dreamtalk/dreamtalk-desktop.exe`与同级`dreamtalk.zip`，版本0.1.41，API协议1，迁移源码head0038。此前便携包保留。便携目录与ZIP均已生成，最后界面提示／长名字排版重新编译并同步到同一包。产物哈希与源码文件比较记录在`artifacts/locations-0141-build.json`。


构建日志：`artifacts/locations-0141-build.log`与`artifacts/locations-0141-ui-final.log`。首次受限构建在Tauri规范化`../../web/dist`时出现拒绝访问（os error 5），调整构建权限后成功；未绕过测试／存档边界。Python venv启动仍出现`Failed to find real location of D:\python\python.exe`提示，但源码检查和打包实际退出成功。打包保留PyInstaller的tzdata／pysqlite2／MySQLdb可选导入提示，Rust的STATIC_VCRUNTIME废弃提示，以及Web大于500kB提示（主包733.56kB、Three587.98kB、关系网817.51kB）。没有以构建成功推定运行性能或兼容性。

包内帮助为本轮打包快照，源码引用链接仍以`SOURCE_REVISION.txt`中的已提交0e6f2ee为基线，新改动尚未出现在该远程Git引用中；包内文档不是之后每次仓库更新的动态镜像。用户可先从原托盘退出旧版，完整保留新版Core目录再打开0.1.41，自行验收升级／位置／视觉。当前没有必需的产品疑问，也未授权扩大地点容量、玩家旅行或发布。

最终只读比较252份随包Core源码与工作区一致；包内帮助530个本地目标／0断链。文档同步重打ZIP时，首次遇到既有auto-launch许可文件的1973年时间戳；已沿用原构建脚本的strict_timestamps=False生成兼容ZIP，不修改许可原文。
