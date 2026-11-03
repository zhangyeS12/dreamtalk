# 卡包交互网页预览

本页保留已确认网页的独立参考入口。正式页已直接复用同一组件与样式，由`PackCollection`接入真实卡库、卡包存储和图片接口；不是重新实现另一套外观。工程与正式桌面验收状态只查[状态清单](../PROJECT_STATUS.md)。用户已确定：切到角色卡页先浏览多个卡包；选中包居中并轻颤，包体有厚度且可拖动360度旋转、查看独立背面；按住顶部封口横向划开，里面的卡片散出后进入原卡环；每次返回卡包或重新切入角色卡页都重新封好。卡包可以创建、独立设计正背面，并选择装入的库卡，原卡保留。

## 预览与正式页边界

- 入口为`apps/web/card-packs-preview.html`，使用项目现有React／TypeScript／Vite。`src/previews/card-packs/previewStore.ts`只提供内存中的演示世界、角色、卡包和图片；刷新恢复初始内容，不构造Core连接，不读取正式存档、凭据或旧localStorage键，不调用模型。完整文件导入／分享及真实世界运行继续从正式入口使用。
- 世界书页直接使用`WorldArchivePage`／`WorldShelf`。拆包后直接使用`CharacterLibrary`／`CardRing`／`CardDesigner`，散出卡面复用`CardFace`，并从原环的真实DOM位置计算落点。没有另写一份书架或卡环。
- 卡包展示和交互位于`world/cards/packs/`：`CardPackLibrary`负责选包、封口、取消和重新封装；`PackBody`将正面、独立背面和四个折边放入同一CSS 3D包体；`PackFace`与`PackEditor`负责双面设计与装卡；`PackSpill`负责散出过渡；`packDesign.ts`复用生成API类型并提供默认外观；正式持久化的有界写模型在`application/card_design.py`。正式适配器只接数据和图片接口，不改变已认可的外观／交互。
- `WorldArchivePage.renderCardCollection`是可选展示挂载点，缺省为正式`PackCollection`，预览则注入独立内存适配器。`CardCropper`新增可选比例／标题参数，缺省保持原银行卡比例；卡包图片沿用同一裁剪交互，当前封面比例为0.7。

## 当前可体验的操作

1. 从底部胶囊切到角色卡，选择一个卡包；居中结束后拖动包体水平旋转360度、垂直改变俯仰，整包位置固定。正背面分别呈现自己的设计，侧边和上下封边具有可见厚度。正面／背面按钮可快速翻面；键盘方向键旋转，Home回正面。旋转时暂停轻颤，失焦／取消释放捕获。
2. 正面或背面朝向自己时，均可从顶部封口任意一端按住横向划到另一端。包体拖动只旋转，封口拖动只剪开；接近侧面或俯仰过大时，先转回可见封口面。未划完放手、失焦或Esc取消时恢复；键盘可聚焦封口使用方向键或Enter。减少动态效果时直接过渡，不强制散出动画。
3. 卡片散出后使用原环绕浏览、固定展开旋转、卡面DIY及拖入演示世界流程；“返回卡包”重新封装，同一包可反复拆开。
4. “设计与装卡”中选择库卡，分别编辑正背面、材质、配色、图片、文字和贴纸；整包固定，仅组件可以拖动。支持一次对称到背面与撤销，原图可重新裁剪。空包会提示先装入角色。
5. “创建卡包”从空包开始，保存后居中，方便继续拆包。独立预览的保存仅在本页内存；正式页保存到存档，重开恢复。

## 实现来源与核对

复用现有React 19（MIT）、react-easy-crop 6.2.3（MIT）、lucide-react及项目Apache-2.0组件；无新增依赖。箔面褶皱、微颗粒与热封压纹使用项目内的[生成纹理与完整提示词](../../apps/web/src/world/cards/packs/assets/README.md)，由内置imagegen生成后原样保存；印刷、四种材质、随旋转变化的光泽和几何厚度仍由组件实时呈现。手势使用浏览器原生[Pointer Events](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events)，散出使用[Web Animations API](https://developer.mozilla.org/en-US/docs/Web/API/Element/animate)，参考接口说明，未复制第三方产品源码。封口和漂浮对应明确用户要求；支持指针取消、键盘、减少动态效果与窗口闲置暂停。

`scripts/card-packs-preview-check.py`针对已启动的独立8768预览检查：自由旋转／侧边厚度／独立背面及背面剪口、未完成／反向剪口、创建装卡、双面独立与裁剪／对称撤销、原卡环与设计器、返回与重新切入后的封装、窄屏和减少动态效果，并断言没有Core API调用。截图和检查回执写入忽略的`artifacts/card-packs-preview/`；当前工程结果与用户验收边界只维护在[状态清单](../PROJECT_STATUS.md)。

工程端从仓库根目录启动预览服务：

```powershell
node node_modules/vite/bin/vite.js apps/web --config apps/web/vite.config.ts --host 127.0.0.1 --port 8768 --strictPort
```

访问`http://127.0.0.1:8768/card-packs-preview.html`。这是独立预览入口，不代表正式数据。正式卡包行为、保存及源码入口见[角色卡库手册](../CHARACTER_CARD_LIBRARY.md#卡包与装卡)；运行与交付证据见状态清单。

## 固定视觉对照

正式数据接入前保存了三种视口的十二张正反面、画布与侧栏原图及摘要，位置为`tests/fixtures/card_pack_visual_reference/`。`scripts/card-packs-integration-check.py`在临时存档中经真实API写入同一组合成角色／卡包，逐图记录像素差，并与实时预览逐节点核对几何和样式。CSS 3D背面的小字抗锯齿存在跨合成器运行差异，检查保留差值并使用单独容差；不重新拍基准掩盖改版。其余原图保持更严格的像素对照。脚本同时验证真实保存、重开后重裁、装卡、新卡自动加入、原卡保留及重新封好；不读取用户数据或调用模型。
