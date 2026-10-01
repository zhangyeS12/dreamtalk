# 自身活动与聊天衔接：复用调查

日期2026-10-01；从68025eb接续。已有亲历事件输入和事件话题，不再新建活动聊天入口。缺口是缺少有效世界时间、当前活动确认和相对时间；最新自身开始还可能被近期其他观察挤出12条上限。

- [SillyTavern Author’s Note官方文档](https://docs.sillytavern.app/usage/core-concepts/authors-note/)：当日官方文档快照，无固定文档发行号。支持临时情境注入与指定聊天位置；采用临近当前问题补充情境的产品做法。[源码许可AGPL-3.0](https://github.com/SillyTavern/SillyTavern/blob/release/LICENSE)，没有复制源码、模板或安装其运行时。它不能替代本项目的Kernel事实和Observation权限。
- [Generative Agents retrieve.py](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/reverie/backend_server/persona/cognitive_modules/retrieve.py)：当日main快照，非固定发布版本；[Apache-2.0](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/LICENSE)。它把事件检索分为近期、重要性和相关性；已有原文检索适用于对话记忆，本轮仅复用近期自身事实与当前情境相联系的做法。安装其环境、embedding检索和模拟循环会重复当前世界内核并增加成本，未引入。
- 直接复用SQLAlchemy/SQLite、角色授权Observation SQL、现有事件描述投影、EffectiveWorldTimeSource、私聊/群聊上下文与模型预算。只增加一个只读自身活动快照，提取已有观察过滤供两处使用；没有新依赖、数据库表、迁移、事实执行器或模型任务。

## 实现及边界

生产组合根显式绑定CharacterActivityContextReader至验证过的当前发言者。单SQL读取同世界时钟、仅该角色观察过且主体为自己的最新已提交CharacterRoutineStarted v1，以及自身current revision/地点；白名单JSON类型检查，不材料化整个payload。再按同一事件ID复用已授权描述投影。状态匹配、开始不在未来、当前WorldTime位于半开原定区间时，才能描述正在进行；区间结束或状态变动只保留历史开始，不声称完成。

新内部reader为可选constructor参数，原事件reader接口保持。每条新快照最多2KiB，过长历史描述省略；时间为WorldTime和经过的世界分钟。私聊临近当前问题，群聊只给本次speaker；selector、普通玩家事件API和离线联系输入保持既有边界。所有文字继续作为lower-trust USER资料，不把资料中的指令提升为system。

没有补造过去成果、主动通信目的、Player Observation/Knowledge、EpisodicMemory、关系或世界书公开范围。模型回答本身不保证获知模型准确性，运行验收由用户完成；本轮仅格式/lint/type和构建、字节核对。
