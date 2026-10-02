# 世界档案库复用调查 — 2026-10-02

本轮在首次修改前核对 React 现有结构、原生滚动方案、既有 ContentEditor／WorldImports 和 World API；实现期间补查酒馆的世界书入口及成熟轮播库。需求为世界档案横向书架与现有功能迁移，不是更换技术栈或重写世界书引擎。

| 成熟实现／来源 | 核对点 | 采用方式 |
| --- | --- | --- |
| [SillyTavern World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/) | 独立世界书编辑与上下文绑定，导入和触发设定 | 参考信息组织；保留本项目已支持的导入、确认、公共背景和触发逻辑，没有复制 ST 代码或素材 |
| [SillyTavern release LICENSE](https://github.com/SillyTavern/SillyTavern/blob/release/LICENSE) | AGPL-3.0，项目本身采用 Apache-2.0 | 未内嵌 ST 页面／脚本，不引入新的许可依赖 |
| [React 状态身份](https://react.dev/learn/preserving-and-resetting-state) | 同位置保留状态，key 隔离世界组件 | 明确书架与已进入世界，业务组件以真实世界 ID 区分；复用 React 19，未新增状态管理或路由库 |
| [MDN CSS scroll snap](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll_snap/Basic_concepts) | 横向浏览和原生吸附 | 原生 overflow-x／scroll-snap 与按钮滚动，不自行实现拖拽物理引擎 |
| [MDN 减少动态效果](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40media/prefers-reduced-motion) | 系统减少动画偏好 | CSS 关闭转场、按钮滚动改为即时；动画不控制真实数据是否就绪 |
| [Embla Carousel 仓库](https://github.com/davidjerleke/embla-carousel)、[MIT 许可](https://github.com/davidjerleke/embla-carousel/blob/master/LICENSE) | 现成轮播依赖选择 | 当前没有循环、惯性手势或复杂轮播需求，原生滚动足够，未安装／复制；官方 React 文档此次抓取失败，未声称验证其 API |
| 本仓库 ContentEditor／WorldImports／ModelSetup／CoreClient | 手动、联网生成、预览确认、导入、更新、可见范围与模型配置 | 直接复用；只补类型范围过滤和保存通知，未重复实现解析器、生成服务或权限判断 |

核对日期对应在线文档／release/master，未固定或复制上游代码提交。没有新增依赖、图片资源、Agent 框架、数据库表、HTTP 契约或迁移。世界书入口移动不改变条目触发与后台生成策略。book 的白灰文字封面使用 CSS，符合当前用户方案；三图上传和素材持久化暂不实现。

实际静态检查／编译和用户运行验收分别记录在 HANDOFF 与 [使用说明](../WORLD_ARCHIVE.md)。
