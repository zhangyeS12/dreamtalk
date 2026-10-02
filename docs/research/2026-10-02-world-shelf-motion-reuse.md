# 世界书架空间与动效复用调查 — 2026-10-02

## 依据与范围

用户提供27.4秒绝区零代理人秘闻录屏，并明确批准参考效果实现。按连续帧核对：约6.1～6.7秒从书脊向前抽出并转向封面，约13秒转入详情。视频主要展示选择、切换与打开档案；鼠标悬停幅度采用用户文字要求，不声称视频证明鼠标悬停细节。游戏素材不进入仓库或交付包。

用户要求在本产品中：初始不选书，右侧不展示内容；悬停轻抽，点击完整抽出后显示右侧信息；空白书点击后才出现创建／导入按钮，再进入命名表单；切换／取消时归位。三图封面继续留最后。一个书位仍对应一个真实世界档案，世界可包含多份世界书。

## 调查与实际选择

| 来源／版本与许可 | 核对点 | 本轮采用方式 |
| --- | --- | --- |
| [Codrops 3D Book Showcase](https://tympanus.net/codrops/2013/01/08/3d-book-showcase/)，2013-01-08，[下载示例许可](https://tympanus.net/codrops/licensing/)为MIT（另有声明除外） | 第二例已有书脊收纳、悬停前移与旋转、点击展开／再点归位；作者同时明确它是实验示例 | 参考六面体和交互组织，不把旧jQuery示例当生产组件，不复制代码／文字／素材。GitHub对应LICENSE页此次抓取失败，未声称核对该仓库版本 |
| [MDN transform-style](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/transform-style)，2026-10-02在线文档 | preserve-3d与统一透视；overflow:auto、opacity、filter等会压平三维上下文 | 直接使用浏览器CSS三维；把原生横向滚动放在三维场景外，透视仅放在共享scene。六面体有真实厚度，背板／地面／前缘在同一空间。亮度效果只放在叶子面，避免压平整本书 |
| [MDN Element.animate](https://developer.mozilla.org/en-US/docs/Web/API/Element/animate)，[Animation.finished](https://developer.mozilla.org/en-US/docs/Web/API/Animation/finished)，2026-10-02在线文档 | 原生关键帧、取消与完成Promise | 直接复用Web Animations API，捕获当前姿态后取消并衔接新动画，没有手写逐帧插值／物理引擎。选中键与epoch约束迟到完成，750ms界面兜底避免后台标签暂停动效导致详情不可用；数据读取和模型任务不依赖动画 |
| [Motion React](https://motion.dev/docs/react)，[MIT](https://raw.githubusercontent.com/motiondivision/motion/main/LICENSE.md)，2026-10-02在线文档／main | 成熟React手势、布局与关键帧动画 | 当前是固定六面体的transform与原生滚动，没有手势物理或复杂共享布局需求；浏览器动画API足以承担。未安装Motion、未复制实现，保留后续复杂交互时的选择 |
| [Three.js CSS3DRenderer](https://threejs.org/docs/pages/CSS3DRenderer.html)，[MIT](https://raw.githubusercontent.com/mrdoob/three.js/dev/LICENSE)，2026-10-02在线文档／dev | 成熟DOM三维层级，但文档声明只能在100%浏览器／显示缩放工作，且不能使用材质／几何体 | 当前只需DOM文本六面体，不加入相机／渲染循环依赖；避免该缩放限制。没有声称完整WebGL方案同样受此限制；若后续需要真实模型／灯光再评估WebGL |
| 本仓库React19、WorldImports、ContentEditor、ModelSetup、CoreClient | 已有创建幂等、资料读取、导入与授权边界 | 全部沿用；只调整书架选择、命名表单时机和呈现，没有新增API／数据库／模型调用 |

未新增第三方运行依赖或分发上游代码，因此本轮不增加第三方代码许可证文件。在线资料只用于方案和规范核对，并未运行上游演示。

## 动效与可用性

悬停180ms、抽出480ms、归位340ms；换书时下一本延后90ms衔接。右侧详情在当前书抽出完成后显示，有隐藏标签兜底；减少动画时即时切换。宽窗口右侧信息叠在场景留出的区域，窄窗口放在书架下方，透视和选中位置一并适配。方向键／Home／End浏览焦点、Enter／Space选书，Esc／归位按钮／再点选中书取消。编辑和未知创建结果保留既有离开确认与稳定RequestId。

只按AGENTS第20节进行源码／Git、lint／类型、必要编译和包内静态核对，不运行自动化测试、浏览器／桌面检查或模型调用；真实动效与交互效果由用户验收。
