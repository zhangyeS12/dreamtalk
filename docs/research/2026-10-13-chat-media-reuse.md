# 表情与聊天配图：成熟实现调查

日期：2026-10-13。目标为用户已批准的三套库、同次媒体意图、一次搜索、持久附件及可选图片说明；不引入独立聊天框架或新的世界行为。

| 来源／核对版本 | 许可／边界 | 复用决定 |
| --- | --- | --- |
| [SillyTavern release package.json](https://raw.githubusercontent.com/SillyTavern/SillyTavern/release/package.json)，本次读取1.19.0 | [AGPL-3.0](https://raw.githubusercontent.com/SillyTavern/SillyTavern/release/LICENSE)；release分支会变动，此版本是调查快照 | 参考图片描述持久化、描述编辑、消息附件及搜索结果有界；不复制其源码、不引入runtime。 |
| [图片描述官方说明](https://docs.sillytavern.app/extensions/captioning/)及[实现入口](https://github.com/SillyTavern/SillyTavern/blob/release/public/scripts/extensions/caption/index.js) | 本地／远程描述来源与聊天文本路由可分别配置 | 独立分析当前图片，说明保存复用，不每轮把历史图片重新发给模型。 |
| [酒馆Web Search](https://docs.sillytavern.app/extensions/websearch/) | 图片支持由具体搜索来源决定；不是完整三库权限方案 | 参考图片附件、独立搜索开关与有界结果；沿本产品规则限制为原聊天轮次一次查询。 |
| [DDGS v9.16.0源码](https://raw.githubusercontent.com/deedy5/ddgs/v9.16.0/ddgs/ddgs.py)及[项目文档](https://github.com/deedy5/ddgs) | MIT，仓库已有固定依赖9.16.0 | 实际复用images接口，固定单个DuckDuckGo后端、最多五个结果，不多后端回退。 |
| [Ollama Chat API](https://docs.ollama.com/api/chat)／[视觉兼容接口](https://docs.ollama.com/api/openai-compatibility) | 独立本机模型或用户明确配置的远端服务；模型本身许可另行遵守 | 用已有httpx对接本机/api/chat及兼容/chat/completions，不分发、下载或测试视觉权重。 |
| [SearXNG Search API](https://docs.searxng.org/dev/search_api.html) | JSON须由实例开启，公共实例未必可用 | 未增加新实例依赖；现有DDGS足够实现本切片。 |

酒馆的Character Expressions是聊天旁的角色立绘，不能据此宣称已有消息表情库。公共／专属／用户库及群聊收录是本次用户明确规则，独立实现。

网络结果选择采用搜索相关性与文件验证；未配置视觉分析时，不能称模型已看清图片或已核验复杂梗。检索先过滤授权库，候选只发短说明。下载验证公开地址并固定连接IP、逐次验证重定向，拒绝内网、非图片与超限载荷；界面使用本机附件，不加载模型输出的任意外链图片。

DDGS许可仅覆盖检索库，不授予搜索结果图片的权利。搜索使用分享许可过滤并保留原来源，但过滤不替代原站许可核验；不把检索结果写入源码或随安装包分发。图库服务是否允许永久缓存须逐来源核对，未采用需额外缓存批准的GIPHY媒体缓存方案。

本轮无新Python／前端运行依赖。已存在Pillow 12.3.0、httpx、jieba 0.42.1承担文件验证、缩图、请求和分词，维护成本为新增附件存储、配置、回执和UI接线。未执行真实搜索、视觉模型、浏览器或数据库验收。
