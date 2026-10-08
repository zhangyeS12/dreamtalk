# 角色移动倾向：成熟方案调查

日期2026-10-08，实施基线85f8035。用户要求初始地点具有粘性，允许父／子／兄弟地点直接往返，确认允许极低概率跨地区远行，并批准开始优化。

参考Song等的2010年论文 [Modelling the scaling properties of human mobility, arXiv v1](https://arxiv.org/abs/1010.0436v1)，正式论文DOI为10.1038/nphys1760。论文提出探索与优先返回机制，解释常去地点的重复访问与探索机会变化。参考其“返回常去地点”的概念；不把人口统计模型当作角色性格模型，也不声称本文参数具有实测依据。

该论文使用 [arXiv非独占分发许可](https://arxiv.org/licenses/nonexclusive-distrib/1.0/license.html)，不是可直接并入Apache-2.0项目的开源代码许可。本轮没有复制代码、图、数据或整段文字，没有新增依赖。D3 hierarchy 3.1.2的既有二维包含图继续复用，许可和选择见[地点图调查](2026-10-07-location-containment-reuse.md)。

选择本地有界规则，而非另引入轨迹仿真框架：本项目只有地点树，没有坐标、交通或真实路程。按树距离和明确地区标记选目的地，先抽类别再选地点，避免增加商店数量稀释常驻概率。持久化远行判定门禁、离开时间和返程冷却；Director只沿本批已定路线安排既有日常，不额外调用模型。参数是用户批准的产品默认，可在角色资料选择三档常驻倾向。

实际契约见[批准方案](../proposals/2026-10-08-character-mobility.md)，代码／检查／交付状态见[维护记录](../maintenance/2026-10-08-character-mobility.md)。
