# 地点包含图复用调查（2026-10-07）

用户要求通讯录中的二维欧拉图：地点可多层包含，父地点可直接停留角色，头像表示当前位置。现有三维关系图负责相识连线，不表达空间包含；用手写圆碰撞／最小包围圆算法会增加维护与退化场景处理成本。

实际采用 [D3 hierarchy pack 官方文档](https://d3js.org/d3-hierarchy/pack)中的层级圆形排布。直接依赖锁定 `d3-hierarchy 3.1.2`，许可证 ISC；发布版本及元数据见[上游包](https://github.com/d3/d3-hierarchy/blob/main/package.json)与[版本记录](https://github.com/d3/d3-hierarchy/releases/tag/v3.1.2)。该包无额外运行依赖。仅复用布局计算，React/SVG绘制地点和头像，原生指针与非被动滚轮监听负责平移/缩放，不引入新的应用框架、WebGL场景或后台渲染循环。

布局把直接位于父地点的角色作为该地点的直接叶子，与子地点圆并列，因此不会把父地点角色画成处于某个子地点。地点名称使用独立布局叶子保留空间；此叶子只用于排版，不是地点或角色数据。空地点也保留可辨认的圆。图形不暴露计划、私聊或关系数值。

开发类型声明为 `@types/d3-hierarchy 3.1.7`，MIT，仅供编译，不进入产品运行依赖。许可原文保存在 [布局许可](../licenses/d3-hierarchy-3.1.2-LICENSE-ISC.txt)和[类型许可](../licenses/d3-hierarchy-types-3.1.7-LICENSE-MIT.txt)，生产许可汇总追加布局包原文；便携打包沿用完整许可目录。

保留现有 Three.js/3d-force-graph 关系网；不复用其力导向模拟表示包含关系。未复制 SillyTavern 源码。本轮实现按用户要求复用现有SQLite/Alembic和Kernel，不引入图数据库、路径规划库或额外模型调用。工程端未运行图形／浏览器／桌面测试，视觉和操作由用户验收。
