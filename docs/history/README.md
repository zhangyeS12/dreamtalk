# 历史证据索引

当前工作只从[工程规则](../../AGENTS.md)、[交接](../../HANDOFF.md)和[状态清单](../PROJECT_STATUS.md)进入。历史记录保留原日期／范围；当时的“下一步”“本轮授权”和“未实现”均不是当前指令。

## 重复全文与早期阶段报告

文档去重时移除工作树内的重复全文快照和过期阶段汇总，原文仍在Git中。以下链接固定在整理前提交 `485b512a5dac8da7077326d1cd3daea5eb3304c8`，不依赖以后分支变化；离线也可用 `git show 485b512:原路径` 查阅，不改写历史。

| 历史材料 | 固定原文 |
| --- | --- |
| 早期规则与交接全文 | [AGENTS快照](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/history/2026-10-04/AGENTS.before-consolidation.txt)、[HANDOFF快照](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/history/2026-10-04/HANDOFF.before-consolidation.txt)、[原校验摘要](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/history/2026-10-04/manifest.sha256) |
| 原Architecture Review与代码审计 | [Review 001](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/architecture/ARCHITECTURE_REVIEW_001.md)、[旧代码审计](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/architecture/CODEBASE_AUDIT.md) |
| 阶段验收汇总 | [Stage 2](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/architecture/STAGE_2_ACCEPTANCE.md)、[Stage 3](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/architecture/STAGE_3_ACCEPTANCE.md)、[Stage 4](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/architecture/STAGE4_ACCEPTANCE.md)、[Stage 5](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/architecture/STAGE5_ACCEPTANCE.md) |
| 本次整理前的活动入口 | [AGENTS](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/AGENTS.md)、[HANDOFF](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/HANDOFF.md)、[状态清单](https://github.com/zhangyeS12/dreamtalk/blob/485b512a5dac8da7077326d1cd3daea5eb3304c8/docs/PROJECT_STATUS.md) |

模块技术契约仍保留在architecture目录。阶段报告中的历史检查仅证明当时范围；测试命令和阶段停止点不作当前执行指令。

## 按问题查原始记录

| 主题 | 证据入口 |
| --- | --- |
| 发行、CI、签名与频道 | 当前入口见[状态清单](../PROJECT_STATUS.md)，历次发行按maintenance中的release文件日期检索 |
| 五位置存档 | [批准方案](../proposals/2026-10-17-save-slots.md)、[实现与隔离检查](../maintenance/2026-10-17-save-slots.md) |
| 启动／更新／媒体可靠性 | [可靠性修复](../maintenance/2026-10-17-reliability-hardening.md)、[本机入口修复](../maintenance/2026-10-16-local-entry-repair.md)、[旧版启动更新](../maintenance/2026-10-16-old-version-startup-update.md) |
| 存档升级与新用户问题 | [新用户审查](../maintenance/2026-10-15-new-user-audit.md)、[修复](../maintenance/2026-10-15-new-user-fixes.md)、[启动结构修复](../maintenance/2026-10-15-save-start-fix.md)、[快照更新](../maintenance/2026-10-15-save-snapshot-update.md) |
| 媒体与配音 | [媒体修复](../maintenance/2026-10-15-media-contract-reliability.md)、[本地候选修复](../maintenance/2026-10-13-speech-candidate-sampling-fix.md)、[配音部署](../maintenance/2026-10-12-local-speech-deployment.md) |

维护记录保留必要诊断与授权证据，不再逐条抄进本索引。其他记录用文件名日期／主题检索；研究输入见[研究索引](../research/README.md)。没有新增用户反馈时，不从历史构建成功推断当前验收通过。
