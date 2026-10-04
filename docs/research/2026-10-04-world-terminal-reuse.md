# 世界内界面优化：成熟方案与实际复用

调查日期2026-10-04；目标为改善现有产品界面的材质、信息层级和阅读，不新增游戏行为。

| 来源 | 借鉴或复用 | 版本/许可与决定 |
| --- | --- | --- |
| [Fluent 2布局](https://fluent2.microsoft.design/layout) | 间距、对齐和邻近关系形成信息分组，桌面与窄窗口采用不同布局 | 官方在线文档，调查日快照；参考设计原则，不复制组件代码、图标或品牌资产，不增加Fluent包。 |
| [Fluent 2排版](https://fluent2.microsoft.design/typography) | 清晰的字级和阅读行宽，重点放在正文而非装饰卡片 | 同上；沿用本地系统中文字体，不下载或运行外部字体。 |
| [原生details](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details) | 会话工具折叠、头像编辑、既有设置折叠；键盘语义由浏览器提供 | HTML标准元素，使用Tauri既有WebView2，无新增包；独立编写少量焦点/关闭接线。MDN资料仅参考行为，不复制文档段落。 |
| 现有React19/TypeScript/Vite/Tauri | 原组件、状态管理、草稿、保存和错误状态继续使用 | 精确版本以锁文件为准；已有依赖许可记录和便携包许可清单继续生效，没有新增依赖。 |
| 现有ContactAvatar/coverImage/socialSnapshot | 聊天和通讯录共用同一角色头像与既有资产接口 | 本仓库Apache-2.0；只读取已授权世界内头像元数据，不外发、不改变存储或增加付费模型调用。 |

已评估Radix等成熟无样式控件的渐进接入。此次只有原生折叠和既有弹窗，现有组件足够；整套引入会增加状态和样式维护成本，未安装。关系网继续使用已锁定的3d-force-graph1.80.1和Three.js0.186.1，不另造三维图库。

实施文件见[世界内通信终端](../WORLD_TERMINAL.md)。源码/类型/构建检查与真实用户验收分别记录。
