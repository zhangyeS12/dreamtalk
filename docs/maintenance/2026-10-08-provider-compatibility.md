# 0.1.42 模型服务适配维护

日期：2026-10-08。正式仓库 D:\LivingWorld，分支 codex/world-archive，起始/当前已提交 HEAD 为 0e6f2ee；继承未提交的 0.1.41 地点优化。本轮用户授权完善其他 API 厂商适配，并明确选择保留严格整轮 Token 硬上限。源码未提交/推送，公开 Release 仍 v0.1.37。调查见[成熟接口核对](../research/2026-10-08-provider-compatibility.md)。

## 完成的代码

- `bootstrap/llm_runtime.py`：可选同次事件/记忆附带从官方 DeepSeek 扩展到四类已配置文本路由；原生/JSON-object 能力与可选聊天附带分开，主动联系/动态没有原生能力时仍用原提示加本地校验。
- `application/chat_event_annotations.py`：合并前置系统消息，符合 Gemini 的单系统消息约束。数量、来源原句、合法普通台词、损坏/截断 JSON 拒绝、流式只显示 reply 和权限约束沿用，不额外发起提取或修复调用。
- `infrastructure/llm/structured.py` 及 Anthropic/Responses/兼容 adapter：仅转换厂商 wire schema 副本，按厂商子集约束处理；本地仍对原 schema 严格校验，违规结果不提交。Gemini 保留当前接口形状。原有相关用例的 wire 期望已随契约调整，未添加或运行测试，原始 schema 不变和本地违规拒绝断言保留。
- `ModelSetup.tsx` → Tauri `llm_config.rs`：可读回/显式保存 1～600 秒请求超时，以及按具体模型确认的原生 JSON Schema 能力。默认仍 30 秒/未声明原生；更换服务、模型 ID 或地址清除未确认能力选择，保存不会探测密钥/调用模型。旧桌面生成配置继续可编辑；其他高级配置不覆盖。
- Claude/Gemini 继续按可信模型输入容量预留，不新增估算准入。界面显示输入预留、最低输出空间和一次完整回复额度，并说明群聊等需要共享余量。OpenAI 官方 Responses 计数与精确匹配的官方 DeepSeek 既有路径保留，代理不继承官方保证。

## 版本、检查与交付

Desktop package/Tauri/Cargo/对应锁文件为 0.1.42；Web/Core/root 版本不变。本轮没有新增迁移，源码 head 仍 0038_location_policies；不读取或改动真实存档、凭据、后台授权与自启动。

已通过ESLint／TypeScript、8个修改Python文件的Ruff／格式／AST、3个Rust文件格式、5处Desktop版本一致性核对与Git差异空白检查。源码文档903个本地目标／0断链；最终文档／包内清单与哈希记录在`artifacts/providers-0142-build.json`。

便携构建仅使用 `scripts/build-portable.py --build-only --output-name providers-0142`，实际退出0，未执行脚本内smoke或supervisor测试。EXE的FileVersion／ProductVersion均为0.1.42；入口`artifacts/portable/providers-0142/dreamtalk/dreamtalk-desktop.exe`，完整ZIP在同级`dreamtalk.zip`。新目录独立，旧包保留。

构建日志`artifacts/provider-build-0142.log`保留PyInstaller的tzdata／pysqlite2／MySQLdb可选导入提示、STATIC_VCRUNTIME弃用提示，以及Web大于500kB资源提示（主包735.22kB、Three587.98kB、关系网817.51kB）；不由构建推定运行性能。受限uv检查首次因缓存目录拒绝访问失败，改为既有venv直接执行后检查通过；venv检查仍提示`Failed to find real location of D:\python\python.exe`但实际退出0。Rust格式在受限路径规范化时遇到拒绝访问，按同一源码范围提升权限后完成；没有扩大为测试或真实存档操作。

包内文档为本轮构建快照，最终同步检查记录后只更新帮助与重新压缩ZIP，不运行应用。首次受限产物路径解析也遇到拒绝访问，尚未写入文件即停止；在同一产物范围提升权限后重新核对。`SOURCE_REVISION.txt`仍以已提交0e6f2ee作为源码链接基线，本轮未提交代码不在该远程引用中；包内文档不等于未来仓库动态快照。

## 用户验收与接续

工程端没有启动应用、浏览器或真实模型，没有运行自动化测试或实际迁移。待用户验收：四类服务的普通/流式私聊和群聊、同次事件/记忆与原句来源、调整超时后保存/重启/读回、按具体模型声明原生能力后的主动联系/动态、严格额度提示与拒绝。此前地点、共同联系及其他未明确验收项继续保持待验收；没有为催出共同联系改变条件。
