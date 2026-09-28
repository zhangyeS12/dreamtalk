# 世界书参与聊天：复用调查与实现决定

日期：2026-09-28。目标：公开条目按来源条件参与当前聊天，避免未命中条目自动填满背景。

## 调查与选择

- [SillyTavern 1.19.0](https://github.com/SillyTavern/SillyTavern/releases/tag/1.19.0)，2026-09-14 发布，AGPL-3.0。核对[官方 World Info 文档](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)的常驻、主关键词、次级 AND_ANY / AND_ALL / NOT_ANY / NOT_ALL、大小写、完整单词及历史扫描规则。代码来源：[world-info.js](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/public/scripts/world-info.js)，文件 SHA `1941041a7d3d520bc2239117e3853cd0058feac8`；它直接依赖 script.js、jQuery、扩展宿主和提示词全局状态，不能作为独立 Python 激活器调用。
- [Character Foundry](https://github.com/character-foundry/character-foundry)，当前源码主包 `0.5.0`，MIT；[lorebook 文档](https://github.com/character-foundry/character-foundry/blob/master/docs/lorebook.md)的能力是格式解析、提取、插入和转换，没有运行时激活器。旧单独发布的 lorebook 包也不能解决此缺口。其卡片/CharX 适配可以在后续格式扩展时再评估，不为本轮重写现有导入。
- 选择：复用酒馆已公开的基础行为，在现有 Core 的授权背景读取与上下文入口上做局部适配；不复制 AGPL 源码，不新增 Node 子服务、解析器、LLM 检索调用或依赖。当前调查没有发现可直接接入本项目 Python Core 的成熟独立激活组件。

## 实际规则

1. 先由现有持久接口限定当前世界、当前 accepted 版本及明确设为公共的条目。关键词命中不能授予隐藏条目访问权。
2. 常驻条目可以无关键词；普通条目必须命中至少一个主关键词。启用次级条件且存在次级关键词时，再执行已规范化的四种 AND / NOT 条件。空的次级列表不附加条件；未知来源模式不猜测。
3. 默认扫描最近两条本会话可见消息；条目 scanDepth 优先，其次所属书 scan_depth。深度零不进行普通关键词激活；最大 32 条及末尾 16,384 个原始字符。群聊使用本轮已提交发言，后续发言者可因前一位说的话触发背景。不跨会话、跨世界或扫描隐藏条目正文。
4. 默认不区分大小写，中文采用字面子串；按来源显式要求区分大小写或完整单词。完整单词检查只使用转义后的字面关键词，不执行来源正则。与酒馆不同，本切片不在扫描文本中补入角色名，不展开模板。
5. 关键词匹配条目优先于常驻条目，再沿用 priority 降序、order 升序、稳定 ID 排序；最多 16 条、title/content 共 12 KiB。超量跳过，不使用 ignoreBudget 绕开既有硬限制。背景保持 lower-trust 数据，不成为 WorldTruth 或系统指令。
6. 正则/模板关键词、未知次级逻辑、非固定概率、持续/冷却/延迟/仅递归、互斥组、角色筛选和附加资料扫描等未支持条件不会退化成普通激活；相关条目暂不参与聊天，并在条目预览和已导入详情解释原因。向量匹配是附加匹配方式，未接入时仅消费有效字面关键词；来源插入位置、脚本、自动化和递归扩展仍不执行。

## 边界与后续

- 内容 API 增加只读 activation_summary 与 secondary_keywords，旧客户端仍可忽略；没有新增持久字段或迁移。CommonLoreEntry 可附带同一 accepted 快照的所属 LoreCollection，供读取已保存的扫描深度。
- 这是基础激活能力，不是完整 SillyTavern World Info 引擎或 RAG。角色专属隐藏授权、向量检索、递归、概率、时序状态及源插入位置仍待后续方案。
- 现存 test_common_lore 使用“公开后无条件入 prompt”的历史预期；本轮产品规则改为真实条件激活。遵守用户负责测试的要求，没有添加、修改、运行或弱化测试。后续用户授权测试维护时，需要更新这类历史预期，并覆盖触发、未触发、常驻、四种次级逻辑、世界隔离和群内历史。
- 构建与静态检查结果记录在 HANDOFF.md 最新接续。
