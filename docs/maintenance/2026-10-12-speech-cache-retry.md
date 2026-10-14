# 手动配音与6小时缓存（0.1.61）

日期：2026-10-12。用户先讨论后明确要求开始修改：点击“播放配音”时，没有有效音频就把该消息交给配音模型；生成成功后缓存6小时，其间重播复用缓存；到期清理，之后手动点击可重新生成。上次失败不能永久阻止手动重试；生成中的重复点击复用同一任务。本轮授权本地实现与build-only交付，不授权工程端生成声音、运行测试、操作真实存档或公开发布。

## 具体行为

| 点击时的状态 | 行为 |
| --- | --- |
| 同一台词／音色／路线的任务正在生成 | 查询并等待已有任务，不创建第二次调用 |
| 声音成功保存后尚未满6小时 | 播放原缓存，不调用模型、不计生成次数；重播不续期 |
| 从未生成、缓存过期或容量清理后没有声音 | 手动点击创建新尝试；成功后重新计算6小时 |
| 上次失败或结果不明且没有缓存 | 手动点击创建独立新尝试，保留旧任务／远程ID／次数回执；不自动重试 |
| 同一个请求编号重复到达 | 复用其原尝试，不把失败请求重置成新调用 |

自动朗读新持久回复仍按现有开关和前台队列执行，沿同一缓存规则；旧消息、刷新、切页、启动及后台清理不自动重新生成。每次真正新生成仍遵守原字数、远程／付费确认、全机每日次数及串行限制，失败或结果不明也计一次。选择付费路线时，手动重新生成属于新的付费任务；界面已明确此含义。

6小时使用真实经过时间，不使用世界时间。Core在成功保存时写UTC时间；运行时按最近到期时间唤醒、至少每分钟核对，读取入口同时强制检查期限。退出期间不运行清理，下次启动先清理已过期声音，不能因重启获得新6小时。旧版没有成功保存时间的缓存保守使用原创建时间，不猜测新期限。原256 MiB总容量及32 MiB单结果保护保留，容量不足可能提前清理；清除音频内容，不删除聊天、任务历史或无正文次数回执。

可选本地桥接的内存音频也在成功生成后6小时过期，并在状态／音频读取时核对。桥接修订3继承原40Token分段／单路解码和不完整结果失败治理；Tauri与Core拒绝让缺少新缓存规则的旧桥接承接新任务。自定义外部服务／远程平台副本仍由其自身管理，应用的缓存清理不擅自远程删除。

## 实现入口

- [SpeechPlayback.tsx](../../apps/web/src/SpeechPlayback.tsx)：手动点击生成请求UUID，自动队列不携带人工重试请求；轮询沿原任务ID，不循环提交生成。
- [API client](../../packages/api-client/src/index.ts)／[HTTP入口](../../services/core/src/livingworld/adapters/http/speech.py)：新增可选请求编号，旧空正文调用兼容为自动路径。
- [SpeechService](../../services/core/src/livingworld/application/speech.py)：复用有效缓存／运行任务；新尝试经原UpdateMaintenance接纳，清理等待器只在短清理事务期间计入屏障，退出取消。
- [配音Store](../../services/core/src/livingworld/infrastructure/persistence/speech.py)：逻辑缓存键与独立尝试指纹分开；写意图事务保留次数准入、请求幂等和各世界／玩家权限。
- [0046迁移](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0046_speech_cache_attempts.py)：仅追加可空cache_key／audio_saved_at及两个索引，保留原唯一约束、音频／历史／回执；历史0045的形状校验继续支持。工程端不执行真实迁移。
- [本地桥接](../../scripts/serve-indextts.py)：后台／读取期限清理内存音频，保留进程期回执与原容量限制，不运行额外模型。

## 成熟组件复用

复用现有CPython3.13.7标准库asyncio（PSF License）、SQLAlchemy2.0.54（MIT）、SQLite（public domain）及Alembic；没有新依赖、队列服务或缓存框架。以原SQLite事务保存尝试与期限，采用标准Event唤醒清理等待器，每个并发事务各自使用AsyncSession。仅复用公开接口，不复制其他项目代码。

核对来源：[Python Event与锁](https://docs.python.org/3.13/library/asyncio-sync.html)、[SQLAlchemy异步会话并发边界](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks)、[SQLite时间表示](https://www.sqlite.org/lang_datefunc.html)。独立模型环境仍为原Python3.11，模型、权重和推理参数未更换。

## 检查与交付

当前源码Desktop0.1.61，迁移head0046_speech_cache_attempts，API协议仍1；尚未提交或发布。Python Ruff／格式、前端ESLint／TypeScript和Rust格式已通过。Rust格式的沙箱路径访问限制经同一只读检查的受控执行解决；保留既有Python解释器定位提示。10份Python AST、6条SQL与0046离线DDL编译通过，没有打开数据库或执行SQL。完整build-only退出0，EXE文件／产品版本0.1.61，包内283份Core源码与桥接脚本逐字节一致，原构建1286文件载荷的隐私核对0发现。保留既有Vite大分包、STATIC_VCRUNTIME弃用、jieba转义及PyInstaller可选依赖告警；未运行自动测试、模型或播放。

已交付入口 `artifacts/portable/voices-0161/dreamtalk/dreamtalk-desktop.exe`，ZIP同级 `dreamtalk.zip`。当前正在运行的旧应用／服务不由工程端停止；用户从托盘退出旧版后打开新包。完整声音、等待时间、失败后的手动重试、重播不再调用及6小时过期由用户验收，不把构建当作这些运行结果。
