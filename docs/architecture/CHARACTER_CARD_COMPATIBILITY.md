# 角色卡兼容约定

导入由独立 adapter 实现，格式转换不依赖酒馆运行，不复制其源码。当前实现、静态检查和用户验收分别见[状态清单](../PROJECT_STATUS.md)。以下行为适用于当前源码；不代表已公开安装包或任意酒馆插件行为已经兼容。

## 支持范围

| 输入 | 处理方式 |
| --- | --- |
| V2/V3 JSON、PNG/APNG | 识别公开 spec，先进行有记录的输入兼容转换，再生成 canonical 内容预览。 |
| V1、旧 Pygmalion JSON、PNG 内 V1 | 映射已知旧字段到 V2 canonical 表示；记录原始格式，原始文件完整保留。 |
| CHARX | 在内存中只读取根目录 card.json，复用同一导入流程；归档、资产描述符保留为来源，不提取附件或自动设置头像。 |
| 较新 V3 | 解析已知结构并提示版本差异；未知字段保留为不透明数据。 |
| 其他容器／酒馆插件运行行为 | 尚无通用兼容承诺。YAML、BYAF、PNG writer、脚本／正则插件执行及完整酒馆提示编排不属于上述支持范围。 |

公开规范为 [V2](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md)、[V3](https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md)；容器参照 [PNG](https://www.w3.org/TR/png-3/)。本轮对照酒馆 **1.19.0** 的[JSON 导入分支](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/src/endpoints/characters.js#L818)、[PNG metadata 读写](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/src/character-card-parser.js)及[CHARX 结构](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/src/charx.js)。酒馆采用 [AGPL-3.0](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/LICENSE)；这里只核对外部格式与互操作行为，使用现有 Python 标准库独立实现，未引入依赖或分发其代码。

## 输入转换与保留

- 角色名称必须是非空文本。描述、性格、情境、开场、对话示例等文本缺失或 null 时使用空文本；明确写成对象等无法解释的正文拒绝，并指出结构路径，不随意 stringification。
- 空缺或 null 的标签／问候使用空数组；字符串标签按酒馆的逗号形式处理，单条字符串问候转成一项。缺失 V3 群聊问候不阻断导入；数值版本和已知旧版本写法规范化，并保留来源。
- character_book 为 null 按未附带世界书处理。附带书应用可解释的空值默认；个别不可用条目只保留来源，其他条目仍可预览。整本书结构不可用时，角色主体仍可预览，必须展示书未启用的提示。来源缺失的正则开关按普通关键词处理并记录，不启用正则执行。
- 不可用的可选元数据／资产只保留来源并提示，不使角色主体失败。assets 的源索引在过滤后保持可追踪；数据 URL 不访问，原描述符可用于受控导出。
- UTF-8 BOM 可读取。原始 bytes、来源 hash、未知字段和转换记录保存；不改写源文件。V1/Pygmalion 转换后的 provenance 使用 V2 格式，input_compatibility.origin、original_spec、original_version 保留输入身份。
- 常规文本映射 display_name、description、personality、scenario、creator_notes、example_dialogue、tags；system_prompt、post_history_instructions、first_mes、alternate_greetings 保存在 authored_instructions。导入不自动创建聊天消息；确认后的角色卡、开场及写作要求按[扮演契约](CHAT_MODEL.md#角色扮演优先与开场)进入聊天高优先级提示，不授予程序或知识权限。

## PNG 选择与明确确认

ccv3 优先于 chara，两者不合并。卡片关键字忽略大小写；base64 允许空白与缺失 padding，同时保持字符和解码大小校验。主数据有效时，另一份未采用数据的解码／结构问题只提示并保留原图。

V3 无法读取但 chara 可读取时，预览明确标记来自 V2，确认按钮显示“确认使用 V2 内容”；用户取消不会提交。不存在有效候选、同关键字不同 payload 的歧义、PNG 容器边界／CRC 损坏继续拒绝，不猜测应使用的正文版本。

## 安全、容量与保存

原始上传和解码后的 JSON 各最多 **32 MiB**；JSON 嵌套最多64层，PNG chunks／CHARX 成员最多10000，世界书最多10000条；超过10000项的资产列表只保留来源并提示，不实例化为附件。CHARX 声明的展开总量最多128 MiB；禁止不安全路径、重复归档路径、符号链接和加密条目，只读取有界 card.json，不向磁盘解包。

重复 JSON 键、无效 UTF-8／孤立 surrogate、非有限数、无法识别的角色主体及资源超限明确失败，不截断正文。错误保留稳定 detail code，并附加结构 path；界面分别说明格式／字段／容量／服务异常，不显示源正文。批量兼容提示按 code 分组，字段可展开，避免每个默认字段生成一个顶层提示节点。

预览不写数据库，仍需 reviewed hash 明确确认；内容、来源、资产元数据按原事务保存。来源不授予 WorldTruth／角色知识，不执行脚本、模板表达式或外部工具，不下载 URL。聊天做`{{char}}`／`{{user}}`字面名称替换；只有卡内主提示和后置指令另支持`{{original}}`引用对应默认写作要求，替换不递归，其他模板不执行。示例、开场和后置位置见[扮演契约](CHAT_MODEL.md#角色扮演优先与开场)，世界书权限与[已有触发边界](LOREBOOK_COMPATIBILITY.md)保持。

## 导出与工程检查边界

输入兼容转换位于 card_compatibility.py、card_lore.py；严格 schema 单独位于 card_schema.py，导出直接使用该 schema。canonical 内容优先，输出继续生成规范 V2/V3 JSON，不把坏源字段重新包装成合法输出；未启用的书和未打包附件给出损失提示。原始文件保留与规范 JSON 导出是两个不同操作。

现有`tests/application/test_character_card_import.py`已包含V1转换、缺省兼容和损坏容器等回归；不再沿用早期“旧断言尚未修订”的停止点。实际检查结果只维护在状态清单及对应记录；测试存在不代表本轮运行通过，真实导入、确认保存、重启及导出往返仍按具体场景验收。
