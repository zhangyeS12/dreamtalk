# 0.1.44 常驻中心与角色移动

日期2026-10-08；正式仓库D:\LivingWorld，分支codex/world-archive，起始HEAD85f8035。继承此前未提交的0.1.43默认／世界独立模型实现；本轮只实施用户批准的移动优化，未提交／推送／公开发布。最新公开Release仍v0.1.42。[批准方案](../proposals/2026-10-08-character-mobility.md)／[成熟方案调查](../research/2026-10-08-character-mobility.md)。

## 已实现

- 初始地点改为常驻中心，允许父／子／兄弟节点直接移动；隐藏祖先、角色开放、锁定原地点、严格同LocationId相遇不变。非作者运行地点不因为范围扩大而进入模型目录。
- 地点编辑加入地区标记，角色资料加入一般／强／很强倾向。默认普通批次70/25/5，类别先于地点数量；距离衰减、离开后返回倾向、跨地区单独1%机会和返程路线由本地代码确定。
- 远行判定至少相隔24小时WorldTime，返常驻地区后7天冷却。门禁和计划快照在调用前持久化，不逐移动调用模型；失败不补抽。Kernel提交真实移动时同步更新离开／远行状态，锁定或改中心的真实返回也保留冷却。
- Director须沿输入路线安排2～4条日常，不能借相遇改变地点。规则签名在派发／接纳／执行检查，配置改变不接纳旧结果、没有付费自动重放。原窗口、失效阈值、容量、费用与暂停逻辑保持。 仅修改倾向不取消当前合法路线，也不因配置revision变化使其失效；初始地点、锁定、权限和地点结构仍作为执行准入。
- Alembic0039追加is_region／residency及character_mobility；枚举用SQLite追加guard trigger约束，迁移检查同步识别新对象及旧0038形状。不重建已有表、不迁移真实用户存档或改写历史。

## 接线

入口在通讯录LocationWorkspace；API client → world_locations／character_activity_setup HTTP →对应应用服务→Kernel作者命令→world_locations／location_rules持久层。新增application/character_mobility负责纯地点选择，persistence/character_mobility负责持久门禁和规则核对，Director规划claim保存路线，DirectorKernelRepository的candidate／start在权威事务中复核并记录到达。位置仍由CharacterState和canonical事件权威提供，门禁不是另一套世界真值。

## 检查与交付

Core全量Ruff通过；256个Python源码AST解析通过；前端ESLint／TypeScript通过；Git差异格式通过；文档链接933个本地目标、0断链。build-only完整构建退出0，Desktop文件／产品版本均0.1.44；复核后修正仅改倾向不失效旧路线，Core单独再次编译退出0，最终装包核对另记录于artifacts/mobility-0144-evidence.json。未运行自动测试、浏览器／桌面smoke、真实厂商调用或真实用户存档迁移。当前版本0.1.44，已构建完整便携目录artifacts/portable/mobility-0144/dreamtalk；旧0.1.43仍被已批准自启动路径使用，待新版完成后由用户在设置显式更新，不擅自修改注册或删除在用包。

构建首次受沙箱限制无法canonicalize web/dist，退出1；受控构建权限重试通过，未放宽产品权限。PyInstaller提示tzdata、pysqlite2、MySQLdb隐藏导入未找到；Vite提示三个资源块超过500kB；Tauri提示STATIC_VCRUNTIME配置弃用。保持现有依赖与配置，不把这些编译告警说成运行验收或已确认故障；没有读取密钥／私聊／用户存档。构建日志为artifacts/mobility-0144-build.log、mobility-0144-build-elevated.log及mobility-0144-core-final.log。

最终装包静态核对：256个Core源码与仓库逐文件字节一致，编译数据源码AST一致；最后只规范化director.py换行，不改逻辑。完整包文档582个本地目标、0断链；Desktop版本0.1.44，Core包含0039迁移文件。完整ZIP约137.8MiB，外部SHA256SUMS.txt记录ZIP／Desktop／Core校验和。程序未启动，自启动仍指向0.1.43，因此没有删除在用旧包。

## 待用户验收

通讯录给璃月／蒙德标记地区，给胡桃设璃月城或往生堂并选常驻倾向；普通批次可向父／兄弟地点走动且回中心，锁定立即返回。核对隐藏祖先授权、地点头像／初始－当前位置、同地点相遇和原活动生命周期。跨地区是极低概率，不保证短时间发生；不为验收放宽概率或触发额外付费任务。旧存档升级、常驻节奏、模型遵循路线和失败提示均待用户运行验收。工程检查不扩大此前验收结论。
