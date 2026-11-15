# 安卓通讯录契约

通讯录复用项目现有的 WorldContacts、WorldImports、FactionManager、ContentDetails、CharacterVoice、LocationManager、CharacterLocationEditor、UnplacedCharactersEditor、StickerLibraries、WorldStyleEditor 和 FileExportDialog。它们来自当前 Windows 项目的 Apache-2.0 源码；复用原因是保留既有权限、预览确认、稳定身份、请求幂等和错误处理。使用现有 React 19、TypeScript、Tauri v2／Android 文档桥接，无新增第三方依赖或外部源码。

## 手机入口与信息边界

- 角色资料提供名称搜索、头像、原始卡片、动态词条历史／回退、音色绑定、角色背景、位置规则、打开会话及删除卡片。只读资料不发送消息或调用模型。
- 阵营保留父子层级、创建／改名／移动、空阵营删除、多阵营成员，以及退出时明确选择保留相识或切断阵营联系。草稿、处理中和结果未确认时报告未保存状态。
- 人物关系提供个人／全局二维图、阵营筛选和备用列表，使用 socialSnapshot.connections 中已确认的边，不从同屏、聊天参与者或空间位置推断相识，不显示关系数值，也不把没有共同阵营的连线虚构成一次相遇。
- 地点使用既有获准的作者目录，提供二维地点包含图、备用位置列表和原编辑器，保留隐藏分支／开放范围、初始地点、锁定、常驻倾向及批量放置规则。不提供隐藏活动全知面板。
- 世界风格沿用预览后确认，表情包沿用公共／角色／个人库。卡片及世界书沿用导入、新建、研究生成、编辑预览、确认保存与可见范围规则。
- 使用根身份绑定头像／背景／音色；打开会话与更新卡片使用最新 import 身份。删除仍保留历史事件与会话，旧会话的只读规则由 Core 执行。
- 资料、阵营、位置、音色、风格、表情和卡片草稿的未保存状态汇总到手机外层导航；编辑卡片期间禁用资料页删除。切换分类或打开会话时保留必要离开确认。

## 简版展示与性能

挂载二维 SVG 人物关系网与地点包含图，具体见[二维图契约](ANDROID_CONTACT_DIAGRAMS.md)。图形每页 12 个节点，个人图额外保留中心人物；备用列表每页 30 人，名称目录仍每页 50 人。头像只取当前图／列表所需节点及当前档案，隐藏目录不加载全部头像。聊天背景按当前根身份读取，图片 URL 沿现有生命周期释放。不挂载三维人物关系网或表情立绘编辑器。

页面单列、44px 操作目标、暗色表单和紧凑图标；不增加动画、毛玻璃、粒子、3D、轮询或后台模型调用。打包中仍有未挂载的历史懒加载图形模块，构建体积提示不等于它在手机上运行。

## 单独导出

角色卡支持 V2／V3 JSON，世界书支持 World Info JSON，沿既有导出信息、格式警告、来源 reviewed_hash 和内容 expected_digest 校验。原始隐藏世界书条目也属于显式作者导出范围，界面继续说明此范围；不附带聊天、API 凭据、运行状态或头像图片。

原生保存复用系统 ACTION_CREATE_DOCUMENT。JSON 保存传输上限 64 MiB，通过现有 16 KiB 分块传给受限临时文件；原生逐块上限 32 KiB，总大小再次限制。原有音色／存档传输上限及路径保护保持。系统保存成功、取消或失败后沿原桥接清理临时文件；失败不会重发导出读取或调用模型。

此处没有新增聊天 TXT／JSON 导出入口，也没有新增全局角色卡库、卡包收集／拆包入口。它们属于[剩余差距](ANDROID_WINDOWS_GAPS.md)。

## 证据与手机验收

源代码入口：mobile/Contacts.tsx、mobile/ContactLists.tsx、WorldContent.tsx、ContactSocial.tsx、FileExportDialog.tsx、mobile/native.ts，以及 ExamplePlugin.kt。相对前端源码根目录解释这些路径。

工程记录在 ../artifacts/contacts-alignment-20261108/：frontend-tests.log、typecheck.log、frontend-build.log、kotlin-compile.log、browser/result.json 和检查截图。检查使用合成内容；文件提供者、系统选择窗口、实际图片、卡片更新后的连续性、通知返回和滚动效果由用户通过本机验收入口查验，真机场景留待用户安排。当前发行和已通过项只见[状态清单](PROJECT_STATUS.md)。
