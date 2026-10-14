# 本地配音一键修复（2026-10-13）

用户反馈升级后的旧服务提示要求普通用户自行结束应用／服务，明确要求增加一键修复入口。本轮Desktop源码0.1.67，API协议1、本地推理revision 6、迁移head0047_speech_preview保持。公开0.1.53／Git HEAD a3f2183不变，未提交或发布。

## 本轮实现与边界

- 设置 → 角色配音 → 本地方式的默认地址旁新增“一键修复本地配音”。按钮显示处理中、成功或具体失败结果；旧服务提示直接引导到此入口。模型路径放在展开项，普通操作不用处理进程、端口、终端或日志。未配置模型时仍需要用户选择已经部署的模型目录，不下载或替换权重。
- 用户点击后，Tauri核对模型目录、凭据引用归属及Core连接，取得120秒自动过期的内存修复租约，禁止本Core在修复期间创建新的本地配音调用；已有生成任务阻止修复。缓存重播和聊天文字不变，修复不创建配音任务、改变旧任务状态、续期缓存或重新消耗配音次数。
- `scripts/repair-local-speech.py`只使用Python标准库、Windows自带PowerShell/CIM与Win32 API。查询固定默认端口的监听者，校验loopback、实际Python映像、精确解析后的桥接入口、模型目录和token文件路径。其他便携版本的入口还核对应用identifier及原始包清单中的桥接哈希；不扫描磁盘或全部进程。只有已认证的本项目服务且busy=false才可处理。
- 新桥接提供认证的maintenance/shutdown：同一事件循环先取得生成门禁再请求uvicorn退出，新的提交不能穿过关闭边界。早期协议2桥接没有这个入口；兼容处理在固定进程句柄下再次核对监听者、命令行及空闲状态，只结束该进程，不结束父应用、进程树或其他程序。旧协议缺少原子维护门禁，仍有其他旧客户端在最后一次空闲快照后提交的竞态限制；不将这一兼容路径说成跨所有版本的无损事务。缺少可信空闲状态、密钥不匹配或归属无法确认时保留服务并显示原因。
- 健康的当前服务直接复用；未启动时启动；确认的空闲旧服务结束后启动当前桥接。凭据由原生安全存储与Core通道同步；已保存的默认本地路线只补必要的凭据绑定，其他尚未保存的设置不被整体提交。原音色、生成声音、六小时期限、候选试听／替换、3候选及容量内整段策略保持。

兼容关闭只接受明确的较早推理revision，未知或更高revision保留；服务在核对期间改变版本时也拒绝关闭。修复辅助脚本是独立源码载荷，最终打包阶段同步该兼容守卫并核对逐字节一致，不需要执行脚本或模型。
- 修复最多等待45秒的辅助操作，随后使用既有服务启动期限；租约结束时释放，连接丢失／宿主退出后最多120秒自动失效。桌面更新与其他原生服务操作互斥。没有自动后台修复、强行关闭生成中任务、切换云端、自动重试台词或修改系统启动设置。

本轮授权是实现用户点击的修复能力；工程端没有运行修复器、结束当前进程、启动服务或调用模型。历史两进程的一次性结束授权仍是已完成的旧记录，不复用为本轮实际进程操作许可。

## 成熟实现、依赖与接线

参考微软官方[Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection?view=windowsserver2025-ps)的OwningProcess查询和[CommandLineToArgvW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-commandlinetoargvw)的Windows参数解析行为（2026-10-13查阅，Windows 10/11系统API）；复用系统组件及已有Python 3.11标准库，不复制文档／第三方代码，不新增依赖或分发Windows组件。保留现有Tauri／tokio／reqwest监督与认证方式；避免引入常驻修复服务或管理员权限。

UI与复制入口：`apps/web/src/SpeechSettings.tsx`／`SpeechPlayback.tsx`／`speech.css`。原生入口：`apps/desktop/src-tauri/src/local_speech.rs`的repair_local_speech，经`lib.rs`注册。辅助脚本：`scripts/repair-local-speech.py`；`build-portable.py`复制到包内scripts，既有安装包载荷由便携目录取得，不改更新渠道。

Core租约：`application/speech.py`的begin_local_repair／end_local_repair，以及`adapters/http/app.py`认证系统路由；只保存在当前进程内，无新数据库迁移。桥接`serve-indextts.py`新增维护能力标记、pid及认证退出入口，推理revision仍6，不改变模型参数。

## 检查、交付与待验收

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；完整构建退出0；EXE文件／产品版本0.1.67，包内285份Core源码及桥接逐字节一致。已交付入口 `artifacts/portable/voices-0167/dreamtalk/dreamtalk-desktop.exe`，使用`--build-only`；日志artifacts/build-voices-0167.log、摘要artifacts/voices-0167-delivery.json。保留既有未提交改动；未提交／推送／发布。

未添加或运行自动化测试／smoke，未启动应用或服务、运行修复器、调用模型、读取台词／声音、操作真实存档或执行真实迁移。辅助脚本编译／AST核对不证明Windows实际进程解析和关闭已验证。

待用户在新版验收：空闲旧服务能一键更新并连接；当前健康服务不重复启动；未启动服务可启动；正在生成时修复明确拒绝；未知程序／错误目录不被关闭；原缓存及候选保留、修复后手动配音可用；退出或失败不会长期阻塞新任务。“第一句后无声”属于独立生成问题，本轮不登记为已解决。

构建保留可选tzdata／pysqlite2／MySQLdb隐藏导入缺失、Vite大分块与Tauri STATIC_VCRUNTIME弃用警告，未用其推断配音故障。文档链接、源码／载荷已知隐私特征、清单哈希与源码一致性检查结果见交付摘要；这些检查不认证实际进程修复或声音效果。

首次交付收尾因文档copy2参数数量错误停止，应用构建已成功且未受影响。修正收尾脚本后，通过原ZIP与清单哈希核对恢复包内原修复器，仅删除核对为空且位于artifacts内的本轮文档暂存目录，再重新同步受检源码／文档、清单及ZIP。该打包错误已经修复，不冒充应用或模型运行故障；最终收尾退出0。
