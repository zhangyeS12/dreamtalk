# 循环拖动世界书架：复用决定（2026-10-02）

用户已确认：书距略增；横排首尾相接、双向循环；总书位为max(12,世界数+1)，始终有空白创建入口；侧面与正面显示同一个世界名；直接按住书本或背景拖动，短按仍选书，拖动不误触。保留现有抽出后展示详情、草稿和真实世界隔离；三图封面最后实施。

## 成熟实现与实际选择

- [Embla React官方接入](https://www.embla-carousel.com/docs/v8/get-started/react)：React hook与卸载清理、独立导航按钮。当前npm稳定版8.6.0；未使用9.0.0-rc。安装精确embla-carousel-react8.6.0，锁解析出的core/reactive-utils同为8.6.0，React19属于其声明兼容范围。
- [官方选项](https://www.embla-carousel.com/docs/v8/api/options)：loop、dragFree、dragThreshold、watchDrag、显式container/slides。原生有限滚动不能覆盖这轮循环拖动需求，因此直接引入成熟引擎，不另写指针物理、速度衰减、首尾重定位或鼠标拖动点击判断。
- [8.6.0 DragHandler发布源码](https://github.com/davidjerleke/embla-carousel/blob/v8.6.0/packages/embla-carousel/src/components/DragHandler.ts)：8px拖动阈值只用于点击拦截，捕获阶段阻止拖动后的点击；document mouseup处理移出视口的释放。键盘Enter/Space在应用keydown显式激活，以避免旧鼠标点击抑制影响键盘操作。手指拖动交给Embla，保留纵向页面与缩放。
- [官方事件](https://www.embla-carousel.com/docs/v8/api/events)、[方法](https://www.embla-carousel.com/docs/v8/api/methods)：scroll/reInit/settle回调与slideNodes、scrollTo/scrollPrev/scrollNext。应用只读公开slide DOM的实际位置，不调用internalEngine，不复制私有算法。
- [8.6.0 SlideLooper源码](https://github.com/davidjerleke/embla-carousel/blob/v8.6.0/packages/embla-carousel/src/components/SlideLooper.ts)：内容不足以覆盖视口时loop会降级false。12本84px书位在宽屏可能不够，因此按视口增加整圈的纯展示副本，保证内容宽度至少多于视口两个书位；书序持续重复，无新增存档。总书数仍按逻辑书位计。每个逻辑书只有一个按钮/键盘/读屏入口，额外展示书为aria-hidden的非焦点图形，点击复用同一个真实worldId或空白入口。
- [版本标签MIT许可](https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE)：三包均声明MIT，完整原始许可保存在[本地许可](../licenses/embla-carousel-8.6.0-LICENSE-MIT.txt)并随便携包分发。项目仍Apache-2.0。

## 与现有三维场景的衔接

Embla的平面轨道只负责测量与运动，实体书是共享perspective场景内的独立六面书体；既有CSS3D/原生Web Animations继续承担悬停、抽出与归位。重复展示面共用同一BookFaces组件，没有第二套内容格式。已选书固定在抽出位置，拖动只改变背后书排，归位时按当前循环位置接回；世界目录变更缩减空白位时保留名称、稳定请求ID与创建选项。

原版有书脊名称的DOM，但整书rotateY(-90deg)与左侧书脊rotateY(-90deg)叠加，使有字侧面背向视线且被backface-visibility隐藏。新REST改为+90deg，悬停+86deg、展示+24deg，正面与侧面都使用world.name。原HANDOFF的“书脊写世界名”只描述了文本存在，不等于视觉可见，本轮纠正这个实现冲突。

依赖成本：新增三份轻量前端包，无服务/数据库/模型调用；嵌入现有Vite产物。原React/TS/Tauri/Core、业务导入与权限/预算保持。没有游戏资产、Three或另一套应用栈。

## 验证边界

仅静态源码/依赖/许可检查、ESLint/TypeScript、必要release编译和包内字节核对。按AGENTS第20节未新增/修改/运行测试，未启动应用或浏览器，未读取用户存档/凭据或改自启动。真实拖动、循环接缝、快速切换、宽/窄窗口、键盘、创建与返回由用户验收。
