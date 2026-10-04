# 三维流星启动的成熟实现调查

日期2026-10-04；用户批准替换自己的Logo并大胆设计具有真实空间/立体感的旋转流星启动画面。现有源码只有App核心连接文字及随后挂载的书架，未满足这个明确反馈；本轮不是重做已有关系网。

| 候选 | 一手依据、版本/许可 | 选择与实际复用 |
| --- | --- | --- |
| Three.js渲染、粒子及GPU材质 | [官方粒子示例](https://threejs.org/examples/webgl_buffergeometry_custom_attributes_particles.html)、[ShaderMaterial](https://threejs.org/docs/pages/ShaderMaterial.html)、[PerspectiveCamera](https://threejs.org/docs/pages/PerspectiveCamera.html)；已锁定0.186.1，MIT | 直接使用已有WebGLRenderer、PerspectiveCamera、BufferGeometry、ShaderMaterial、Sprite、球体和灯光。自定义光尾形状/配色属于用户指定画面，没有独立重写投影、渲染器或粒子框架。运行/类型依赖许可已随关系网依赖收集，本轮没有新增包。 |
| Tauri官方icon命令 | [官方应用图标文档](https://v2.tauri.app/develop/icons/)；本地CLI2.11.4，MIT/Apache-2.0 | 使用官方多尺寸图标生成器；PNG嵌入透明方形SVG满足输入要求，原图字节不改。复用默认窗口图标和现有托盘default_window_icon链路，没有新写Windows资源编辑器。 |
| 3d-force-graph | 现有1.80.1、MIT | 继续用于关系网。启动没有节点、关系/布局/拾取需求，直接使用同一Three.js底层，避免导入图布局和交互成本。 |
| CSS或2D Canvas旋转光环 | 浏览器已有能力 | 只用于静态首屏、Logo和最终透明过渡；不能满足用户要求的真实纵深，不将其充当主漩涡。 |
| GSAP、Lottie、整套特效引擎 | 本轮无额外依赖/许可决定 | 已有Three.js与短RAF相机轨迹足够；预渲染二维素材不能提供所需空间表现，新框架不解决当前额外缺口。 |

官方示例提供用法参考；项目代码使用库公开能力，自定义品牌曲线/视觉着色器。所有素材本地随包，不向CDN或其他服务发送角色、聊天或存档，也不调用AI生成资产。

像素比上限1.65、26个光尾/900星点、资源释放、隐藏原生窗口暂停和静态回退按源码检查；没有运行测量，不能据此承诺具体FPS。图标CLI本轮提示一个Windows字体文件无法加载，但SVG仅引用PNG、不使用字体，生成产物正常存在；此告警保留，未称为产品运行问题。
