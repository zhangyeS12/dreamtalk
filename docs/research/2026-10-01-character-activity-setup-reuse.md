# 角色初始活动地点：成熟实现调查与复用

2026-10-01；从1d735a9继续，用户授权继续推进。实施前阅读官方文档、项目源码和许可。

- [SillyTavern角色设计](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)中的Scenario描述对话情境；[World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)提供背景提示及角色/聊天绑定。读取[release package.json](https://github.com/SillyTavern/SillyTavern/blob/release/package.json)为1.19.0，[许可](https://github.com/SillyTavern/SillyTavern/blob/release/LICENSE)为AGPL-3.0。这些界面适合作为创作UX参考，不能把提示文本当成本项目物理状态的权威执行器。继续复用已接入的卡片/世界书，不复制其代码或替换Kernel。
- [Generative Agents plan.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/plan.py)依赖persona/maze既有world/sector/arena/object选择活动地址；[LICENSE](https://github.com/joonspk-research/generative_agents/blob/main/LICENSE)为Apache-2.0。核对的是当日main，不宣称固定release或引入其逐角色LLM循环。采用“已有地点作为选项”的方式；初始位置由用户确认，后续批量Director继续使用现有受控地点集合。
- 最终直接复用当前Kernel PlaceCharacter、空expected_state_revision的CAS、CharacterPlaced/state投影、全局命令指纹/回执和SQLite写事务。React19.3.0受控select/form及既有API client负责普通配置，SQLAlchemy2.x投影只返回设置存在性。无新依赖、新Agent框架、新数据库或另外的放置执行器。

新可选activity_player_id作为本入口守卫：同世界当前玩家及私聊归属、创作地点目录、未初始化和已有Director16角色容量在持有writer的同一Kernel事务内核对。None保留旧fingerprint和行为；指定时指纹包含身份，且只允许初始revision。事件格式和receipt格式保持，运行数据无需新migration。

仅显示当前身份的私聊角色及是否已设置，不显示隐藏位置或未来计划；设置不是Player Knowledge。离线联系继续独立于地点。显式提交不调用模型，旧批不被打断；停止的Director可由用户显式请求新规划。失败保留原请求，不自动重放；读取后的“已设置”不代替本次回执证明。

按AGENTS第20节只做源码/diff/静态检查与编译、打包字节核对；用户负责运行验收。既有第三方许可保留，无复制上面项目的实现代码。
