# 设置手册与通讯录入口成熟复用调查

日期2026-10-03；在实现新布局前查询官方资料，保持React19/TypeScript/Vite8/Tauri2。

- [Microsoft NavigationView](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/navigationview)：成熟的分栏导航与窄窗口适配。仅参考交互结构，不引入WinUI/XAML。
- [Fluent 2 Nav](https://fluent2.microsoft.design/components/web/react/core/nav/usage)和[Tablist](https://fluent2.microsoft.design/components/web/react/core/tablist/usage)：参考导航/标签职责。Fluent 2为设计系统版本，未选用或锁定React包版本，未复制实现/素材，不产生分发依赖。
- [Radix Tabs 1.1.18](https://www.radix-ui.com/primitives/docs/components/tabs)：支持受控值、垂直布局、完整键盘与forceMount；[MIT许可](https://github.com/radix-ui/primitives/blob/main/LICENSE)。适合真正的标签组件，本轮七类是页目录，不实现Tabs键盘游标，也不为普通目录引入新的Primitive和传递依赖。

采用现有React状态、浏览器原生nav/button/details/summary和既有CSS token。导航沿用主导航aria-current模式，Tab/Enter/Space由浏览器提供，分类切换定位标题；原生details负责展开与键盘，不写折叠引擎。模型/后台/活动/离线/事件池组件保持挂载，仅隐藏未选分类，保护草稿、授权界面、请求ID与不确定结果回执。只在可见的地点/活动/动态分类启用原只读刷新。

角色卡直接复用WorldImports/ContentEditor/CoreClient的手动/联网/PNG/JSON/预览/确认/版本冲突逻辑，改变入口并增加保存后的通讯录只读刷新；不写新生成器、解析器或存储。封面共用BookFaces/useWorldCovers，只在设置可见且世界已读取后获取当前世界展示图，复用Bearer/Blob与撤销机制。“关于与诊断”复用现有CoreClient.health与桌面状态，不探测提供商凭据。

无新依赖、许可源码复制、Core/API/schema/知识/预算改动，不使用SillyTavern AGPL实现；不调用模型或读写用户存档作验证。
