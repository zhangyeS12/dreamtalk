# 书架默认模型与世界独立模型（Desktop0.1.43）

日期：2026-10-08。本轮起始HEAD`85f8035295ee416a7982e2c63258a105f008c564`，分支`codex/world-archive`，正式仓库`D:\LivingWorld`。用户明确要求世界内模型修改与书架默认隔离。前序公开包仍为[v0.1.42](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.42)；本轮0.1.43为本地工作区，尚未提交／推送／发布。

## 本轮问题与变化

0.1.42书架与世界内使用相同Tauri模型保存命令，没有世界身份，且Core只有一套模型快照；因此修改会影响全部世界。现在：

- 书架“模型设置”保存默认配置；没有独立配置的世界继承它。
- 世界内“设置 → 模型与聊天”明确显示继承或独立状态。保存后只修改当前世界，不改默认或其他世界；“恢复使用书架默认配置”移除本世界覆盖。
- 独立范围含provider、base URL、model、凭据引用、输入／输出容量、超时、流式、原生JSON能力。原有每轮聊天Token上限仍是本机共用设置，界面明确提示。
- 普通／流式私聊和群聊、选人、同次事件／记忆、手动摘要、卡／书资料生成、Director、世界动态、在线／离线主动联系均按请求或持久任务的WorldId选择配置；书架中已选世界的联网资料生成也使用该世界的有效配置。
- 默认配置由高级方式管理时，继承的世界仍可另建普通独立配置；已有独立高级配置与默认高级路由／定价不被普通表单覆盖。

## 接线与持久化

前端`ModelSetup.tsx`／`ProductApp.tsx`／`WorldArchivePage.tsx`传入可选WorldId；设置目录和诊断也显示当前世界状态。API client的health增加可选`world_id`查询，API协议仍1。

Tauri`lib.rs`／`llm_config.rs`按范围读取、原子替换或移除配置；保持`config/llm.json`路径。旧v1文档作为默认继续可读；有世界覆盖时写v2容器`{version:2, default:<v1>, worlds:{<WorldId>:<v1>}}`，严格验证尺寸、UUID与各内层版本。容器损坏时LLM子系统fail closed，不静默切换服务；世界／存档仍独立。

Core`production_config.py`加载不可变快照，`bootstrap/llm_runtime.py`为默认及独立世界分别组装注册表／adapter／路由／保守预留，`application/world_model_config.py`提供按实际世界解析。各应用服务与HTTP回复入口读取对应快照；凭据启动同步取所有范围的引用并集，模型健康按所选范围计算。没有数据库迁移，Alembic仍`0038_location_policies`。

API Key继续由Windows安全凭据存储持久化，不写JSON、日志或返回给页面。未输入新密钥时可以共享旧引用；更新／恢复后仅清理不被默认或任何世界引用的旧凭据。更换服务类型或兼容服务地址必须输入新密钥。没有新增provider调用、隐藏背景或私聊外发范围。

保存仍沿用共享Core重启与失败回滚，不是热切换；在途调用可能中断，已接纳调用可能收费，旧失败不会自动重放。已经独立配置的世界保持其快照，后续默认更改只影响继承者。v2模型配置不能由0.1.42旧模型加载器识别，不要切回旧程序覆盖模型配置。

## Kimi／GLM

已有兼容Chat Completions adapter不按品牌限制model ID。Kimi／GLM官方提供兼容入口，可在“兼容Chat Completions的服务”填写完整base URL、实际模型ID、密钥和可信容量。能力按型号确认，原生JSON默认关闭；严格保守准入保持，未核实的容量不猜测。本次只核对接入资料，没有真实Kimi／GLM调用或兼容验收。[调查与来源](../research/2026-10-08-world-model-config.md)。

## 检查与交付

ESLint／TypeScript退出0；13个修改／新增Python源码的Ruff、格式和AST解析通过；Rust格式核对和Git差异空白检查通过。文档链接928个本地目标／0断链，379个外部链接仅计数，不宣称全部外链可达。

`scripts/build-portable.py --build-only --output-name world-models-0143`退出0；未执行其中的smoke／supervisor测试。随后补齐高级独立配置的状态提示与恢复默认入口，仅重新编译桌面并替换同包EXE，Core源码没有后续改动。EXE文件／产品版本均0.1.43；253个随包Core Python源码与当前工作区逐文件一致（规范CRLF后比较）。最终桌面编译、包内帮助、程序与ZIP哈希清单见`artifacts/world-models-0143-build.json`。

新入口`artifacts/portable/world-models-0143/dreamtalk/dreamtalk-desktop.exe`，同级完整`dreamtalk.zip`；保留providers-0142等旧包。两个构建日志为`artifacts/world-models-0143-build.log`与`artifacts/world-models-0143-desktop-final.log`。仍有PyInstaller的tzdata／pysqlite2／MySQLdb可选导入提示、jieba转义SyntaxWarning、STATIC_VCRUNTIME弃用与大于500kB的Web资源提示；不由构建推断运行性能。受限Rust路径规范化首次拒绝访问，限定源码／构建范围提升权限后通过；venv源码检查提示找不到D:\python\python.exe原位置，但实际检查退出0。

包内帮助在检查结束后同步并重新压缩，不运行程序。`SOURCE_REVISION.txt`使用已提交基线85f8035，本轮未提交源码不在该远程引用中；`BUILD_INFO.json`明确working tree修改。用户存档、凭据、自启动没有读取／修改；没有自动化测试、应用／浏览器smoke、真实模型或实际迁移验收。

## 待用户验收

- 在书架设置默认A；进入世界一设置B，再核对书架与世界二仍为A。
- 世界一独立B后，将书架默认改C：世界一仍B，继承默认的世界二为C；世界二也独立后两者互不影响。
- 重启后读回各世界地址／模型／能力设置；恢复默认后使用当前默认配置。
- 默认未配置而世界已有独立模型时，该世界仍能聊天和使用已获准后台功能；切换世界和诊断显示对应状态。
- Kimi／GLM按官方地址、完整型号和可信容量配置后，由用户核对普通／流式单聊、群聊及实际所需额度；保存就绪不代表密钥／余额／网络有效。

共同联系继续等待用户，不为了验收触发生成或改变节奏。没有新增疑问；后续按用户具体反馈修复，发布0.1.43另需用户授权。


后续2026-10-08用户要求清理旧文件，仅保留本地0.1.43完整包；上文“保留旧包”为构建时事实。现行保留／启动指向与源码保护见[清理记录](2026-10-08-local-cleanup.md)。
