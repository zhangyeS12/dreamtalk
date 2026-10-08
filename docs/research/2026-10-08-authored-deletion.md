# 2026-10-08 · 角色卡与地点删除调查

用户要求补足角色卡、阵营、地点删除入口并直接发布，未授权删除历史会话或真实存档。核对发现角色卡与地点确无删除接口／按钮；阵营已有删除接口，但只能删除无成员、无子阵营的空阵营。

复用当前依赖，不引入新框架：

| 成熟来源 | 当前锁定版本／许可 | 采用与边界 |
| --- | --- | --- |
| [SQLAlchemy 删除与级联](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#deleting) | 2.0.54／MIT | 在既有 SQLite writer transaction 内保存作者停用标记；只移除作者阵营／头像绑定。不对角色、地点和事件外键执行级联删除，避免毁损不可变历史。 |
| [Alembic add_column](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.add_column) | 1.20.0／MIT | 0040 追加两个 nullable 时间字段；不重建受引用表，不覆盖历史状态。名称唯一约束仍保留，移除地点使用内部保留键释放作者名称。 |

实现是项目独立代码，没有复制第三方源码。删除不生成 WorldEvent、不伪造物理离开、不放宽聊天权限或付费重放规则。旧活动依法结束；未开始候选与联系上下文重新核验停用身份。
