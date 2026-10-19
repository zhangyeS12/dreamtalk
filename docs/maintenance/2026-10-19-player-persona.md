# 设定身份优化的工程证据

## 范围与授权

用户批准明确绑定设定身份、预览确认及逐角色的初始认识，并单独批准本轮仓库外合成数据、模拟模型和内存界面回归。未访问真实存档、系统凭据、已安装应用或外部模型；未运行安装器、发布或改动版本号。

## 实现

行为与源码入口见[身份契约](../PLAYER_PERSONA.md)，不在此复制产品说明。新增增量迁移及生产服务，客户端契约继续从Python生成；稳定玩家、既有资料和聊天保持连续。身份数据随合成整库存档往返。

## 检查与证据边界

- 相关后端隔离回归91项通过，覆盖身份、直接／群聊、离线与在线联系、容量边界、旧资料、历史迁移、存档往返及HTTP生产组装。涉及`test_player_persona.py`、`test_chat_context.py`、`test_group_chat_reply.py`、`test_local_profiles.py`、`test_offline_contact_capacity.py`、`test_capacity_boundaries.py`、`test_migrations.py`、`test_example_world_migration.py`、`test_save_slots.py`、`test_profile_http.py`、`test_http_composition.py`。
- 最后追加Unicode、转义及玩家绑定变化边界，身份专项重新核对13项；此项与上述91项重叠，不相加。
- 最终内存界面及API客户端22项通过，来自`PlayerPersonaEditor.test.tsx`、`ProfileEditor.test.tsx`及客户端现有契约检查。覆盖显式确认、冲突保留输入、过期世界请求、来源分页和重复角色、完整emoji截取。
- Ruff、TypeScript／ESLint、Pyright、契约生成一致性、文档链接及当前工作树隐私检查通过。

隔离检查的数据库、备份、用户目录、缓存及临时文件均放在仓库外专用临时目录。沙箱内两次创建pytest临时目录失败，沿当前许可改为沙箱外执行后完成。首轮检查发现并修复新增迁移在历史结构校验中的接线遗漏；模拟资料服务生命周期、脱敏repr读取及异常Unicode请求编码的夹具问题亦已修正。没有删除或弱化原断言。

尚无真实模型理解效果、真实旧档迁移或产品界面验收证据；已有身份配置的历史用户反馈不扩大到本轮新增功能。未进行桌面编译、打包、Git提交或推送，当前状态见[状态清单](../PROJECT_STATUS.md)。
