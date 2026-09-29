# 手动活动地点：调查与实现范围（2026-09-29）

本轮从78b7055继续，用户授权继续推进项目。选择补齐普通设置的手动地点创建；现有家以外没有配置入口。玩家移动过程和地点层级仍未冻结，本轮不实现移动、层级、路径、地图、主动联系或新活动类型。

## 调查与复用决定

- [SillyTavern World Info官方说明](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)与[release package.json](https://github.com/SillyTavern/SillyTavern/blob/release/package.json)，2026-09-29读取版本1.19.0，AGPL-3.0。World Info用于背景注入，适合描述地点，不是本项目的持久物理位置/受控动作模型。继续使用已有世界书编辑与激活器描述背景，不复制酒馆源码为它增加第二套世界状态。
- [Generative Agents plan.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/plan.py)与[LICENSE](https://github.com/joonspk-research/generative_agents/blob/main/LICENSE)，2026-09-29当日main，Apache-2.0，无声明本次代码为固定release。它依赖persona/maze空间表示选择sector/arena/object。采用受控既有地点集合的思路；不引入其完整逐角色模拟运行时，与现有批量Director/Kernel不兼容。
- 最终直接复用既有CreateLocation Kernel command、SQLAlchemy/SQLite事务、Alembic、请求回执、React受控表单及API client；无新依赖、没有复制第三方代码、没有第二个调度器或模型调用路径。新增工作仅为已有能力的普通产品入口和本地创建目录的安全投影。

## 具体切片

设置中的“活动地点”显示本地用户在这个世界手动创建的地点，以及既有启动流程创建的家。只返回ID/名称/是否初始家；不枚举其他后台地点、角色位置、未来活动、事件或私人知识。目录是单本地用户app-data的创作配置，不是Player Knowledge；不能推广成多人身份授权。

手动填1–120字名称，明确提交后通过同一Kernel事务创建LocationCreated事实、Location投影、本地目录及CommandReceipt。目录是操作元数据，与canonical事件分离；事件格式不变，不重写旧历史。新CreateLocation可选list_locally默认为false，旧指纹保持；true指纹加入标记。相同request ID同参数重放只读旧回执，跨世界/不同参数冲突。目录同世界名称以NFKC/casefold规范键防重复，保留显示名称。家保留给既有启动流程。

沿用Director最多32地点的容量；新建前同一写事务检查实际世界地点数，并为尚未创建的家保留一个名额。目录的所有读写均带world_id。新增0026本地目录表，旧版本验证显式排除新表；不回填未知地点，也不运行用户数据库迁移。Location外键保持，现有projection rebuild使用延迟外键且完整恢复投影，目录不是重建输入。

新增地点不移动任何主体、不自动导入世界书地点、不授予任何人事件知识，不改变旧批候选，不额外请求重规划。已开启Director会在下一次常规规划读取这些已有地点；选择是模型决定，不保证每批访问每个地点。若要补充设定，仍在世界书逐条确认公共背景。

表单提交立即锁定；失败保留名称和未决请求ID，可用原ID重试或只读刷新确认结果。旧读取不能覆盖刚保存状态，切换世界前提示尚未保存草稿。错误在表单附近明确展示，网络失败不自动重放。查看/创建目录不调用模型，不探测凭据。

## 验证边界

只做静态lint/type/format与必要编译打包；按AGENTS不新增、修改或执行测试，不运行应用/GUI smoke/真实API，不修改用户数据、配置或密钥。实际迁移、同名/断线/跨世界和Director选择效果仍由用户验收。
