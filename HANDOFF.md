# dreamtalk 工作交接

更新日期：2026-10-03。此文件记录当前开发现场与接续工作，不替代 [AGENTS.md](AGENTS.md)。先读 AGENTS，再读本文，最后核对实际 Git 状态和相关代码；不能把下面的基线哈希当作永远不变的当前 HEAD。

## 最新接续：2026-10-03 设置管理手册与通讯录角色入口（桌面0.1.15）

- 从干净c2eee7b1fd56cd5de24c24076e7b498e137b3a19 / codex/world-archive接续，实际仓库D:\LivingWorld。用户批准世界管理手册方案，并要求添加角色卡移到通讯录。本轮仅完成设置视觉/分类、角色卡入口迁移及相关只读诊断，不扩展聊天功能。
- [复用调查](docs/research/2026-10-03-settings-handbook-reuse.md)核对Microsoft NavigationView、Fluent2 Nav/Tablist、Radix Tabs1.1.18及MIT许可。采用现有React与原生nav/button/details/summary，不引入新库/框架或自写Tabs键盘机制；复用当前组件/Token/BookFaces/受认证Blob封面。设置显示当前世界小书、白灰纸面、七类书签目录与右页；窄窗口目录横向滚动，内容单栏，减少动态效果与键盘焦点保持。
- 模型服务/回复与聊天额度先显示真实已保存摘要，默认展开模型，额度可展开。应用/当前世界/指定世界范围明确；分类“未保存”来自模型/后台/活动地点/额度编辑状态。原模型保存重启、后台默认关闭和首次费用授权保持。所有分类组件保持挂载，隐藏未选项，不丢草稿/授权面板/请求ID；地点/活动/事件池只在对应可见分类使用原只读刷新。
- **前序文档冲突已更正：** 角色卡不再在设置；“通讯录 → 添加角色卡”直接复用WorldImports/ContentEditor，包含手动、联网生成、PNG/JSON导入、预览确认、编辑与文件更新。保存与返回通讯录触发只读刷新，所选资料按新快照刷新；卡管理初始读取失败提供只读重试，慢旧读由清理标记排除，不重放模型；切换四标签/折叠管理区保留角色编辑，返回书架仍有离开提示。世界书与封面继续书架管理，身份继续“我”。
- 关于与诊断只在可见时调用现有CoreClient.health，10秒有界、离开中止，不验证提供商密钥或产生用量；版本/程序位置来自既有桌面状态。设置封面仅读当前世界展示图，非可见不加载，Blob URL复用/中止/撤销沿用。无Core/API/schema/预算/知识/玩家位置变更，沿用0030，无新存档迁移。
- 五处桌面版本同步0.1.15；ESLint/TypeScript与源码diff静态审查已完成，首编Vite235模块/138ms、Rust release23.27s；补齐通讯录保留挂载后的可见刷新与初读失败只读重试入口、未读取后台状态准确提示后，最终静态检查通过并重新编译。最终Vite235模块/133ms、JS624.33kB（gzip187.98）/CSS46.52kB，Rust release21.52s，日志artifacts/settings-handbook-desktop-build-final.log。完整独立包已静态核对，目录artifacts/portable/settings-handbook/dreamtalk；桌面EXE 13,223,424 bytes / SHA256 2F588A8C01FA357F08C49E1B138CF38917928E117D8D11E2B550E8977FA13E20；ZIP 50,735,055 bytes / SHA256 9E67D46805A0EA4E2BD544C45E08B99D2C793DB8E2C7C5AD382ABBE357CC37D1。Core源码未变，逐文件核对215个Python源码/冻结副本及471个Core文件后沿用完整0.1.14 Core；26份许可证、14份指南与512个ZIP文件字节一致，672个本地Markdown目标无缺失，清单artifacts/settings-handbook-package.json。仍有Vite主chunk超过500kB、STATIC_VCRUNTIME弃用及原Core可选tzdata/pysqlite2/MySQLdb/numpy/olefile/defusedxml缺失警告，未运行验证其影响。保留旧包，本轮不启动应用/GUI/浏览器、不新增/修改/运行测试、不调用模型或读写用户存档/凭据/自启动；不push/发布。
- **接下来：** 用户退出旧托盘并打开完整0.1.15，核对[设置手册与通讯录说明](docs/SETTINGS_HANDBOOK.md)中的七类、草稿保留、卡保存列表刷新、范围/授权、键盘/窄窗口和原保存状态。验收后继续聊天页面统一视觉。暂无新产品疑问；旧ProductApp测试中的首页/设置/角色入口断言待用户另行授权更新，未删除或skip。

## 前序切片：2026-10-03 图片封面可选标题与透明底色（桌面0.1.14）

- 从干净e6a956aa4b5b2064a99974a671ab0927fb84ad26 / codex/world-archive接续，实际仓库D:\LivingWorld。用户认可其他封面效果，指出未输入也显示“绝区零”及标题黑色底块。本轮只修这两点，不扩展书架或业务功能，不引入依赖。
- **前序实现与当前要求冲突：** 0.1.13编辑初值和预览/书架的逻辑OR兜底都会补世界名，前端和HTTP还禁止空标题；只改样式无法取消默认文字。0.1.14文字/图片标题草稿分开，图片默认空；预览与真实书架使用显式空值，图片空标题可以保存，文字封面仍要求标题。HTTP保留120字限制，HTTP与应用层均校验文字标题非空。
- 正面/书脊的图片标题底色改透明、去除黑块内边距，保留轻微文字阴影与左上角dreamtalk浅色标识。已保存标题继续保留，无法区分旧默认与用户主动同名输入，故不批量删除；用户清空图片标题并保存即可去掉旧标题。元数据JSON支持空字符串，沿用0030，无新迁移或用户存档读写。
- 五处桌面版本同步0.1.14。ESLint/TypeScript、Ruff检查/格式、源码diff检查通过。Core与桌面release编译完成；Vite232模块/127ms、JS615.25kB（gzip185.64）/CSS38.90kB，Rust release23.54s。独立完整目录artifacts/portable/world-cover-title/dreamtalk已生成；静态核对215份Python AST/冻结源码哈希、471份Core文件、26份许可、13份说明及511份ZIP文件逐字节一致；667个本地Markdown目标无缺失。Desktop13,219,840 bytes / SHA256 16F8AA5DA4A87354A1C15AC6265B1D7471914FEE8E19C6F1E4A40E699ECF5BB4；ZIP50,733,212 / CA3CCD9CBCC4A246CFE97C045EEDE8A3633EA37649988FAC19A0741FB0F9A765。清单artifacts/world-cover-title-package.json，日志artifacts/world-cover-title-build.log。保留主chunk>500kB、STATIC_VCRUNTIME弃用与PyInstaller既有可选依赖缺失告警，未提高阈值或声称运行时已验证。旧0.1.13完整目录保留。本轮按AGENTS第20节未新增/修改/运行测试、启动应用/GUI/浏览器或模型调用，不代改自启动，不push/发布。
- **接下来：** 用户退出旧托盘并运行完整0.1.14新目录，核对空标题保存/重开仍无文字、自定义标题透明底色、dreamtalk保留。已有标题请清空并保存。验收后继续统一聊天/通讯录/设置视觉。暂无新的产品疑问。

## 前序切片：2026-10-03 本地文字与三面图片封面（桌面0.1.13）

- 从干净c4fe0ff41aebe36acd547c4e5b48f2d7b92a9fb5 / codex/world-archive接续，实际仓库D:\LivingWorld。用户已认可0.1.12效果，讨论两种封面与尺寸/上传后批准“可以，开始实现”。**当前要求覆盖前序交接的“三图封面最后再做”：本轮已实现，不能再按未实现安排。** 保留正面左上角dreamtalk，不改世界名称、世界书正文、玩家状态或背景授权。
- 点击已有世界书后，右侧下方“编辑封面”打开左右编辑区；文字模式输入独立展示标题，正面/书脊同步、白灰书体。图片模式正面必选、书脊/背面可选，缺面使用文字外观；支持静态JPG/PNG/WebP、点选/拖入、固定比例拖动缩放、90度旋转/重置、三角度立体实时预览、图片标题开关、保存/取消及重新读取。比例196:286 / 42:286 / 196:286；建议与正式展示图尺寸980×1430 / 210×1430 / 980×1430。每张<=10MiB/20MP/最长边10000像素。图片标识用浅底保留可读。
- [成熟复用与许可](docs/research/2026-10-03-world-cover-reuse.md)：精确react-easy-crop6.2.3（MIT）及normalize-wheel1.0.1（BSD），Pillow12.3.0（MIT-CMU及随附codec许可）；原始许可随包分发。不写手势/图像codec，不替换React19/TS/Vite8/Tauri2。Canvas只渲染组件选区预览，Core用Pillow格式核对、EXIF方向和LANCZOS生成WebP。按Tauri官方设置main.dragDropEnabled=false，浏览器处理文件拖放；ProductApp仅阻止Files默认页面导航，子上传区正常接收；CSP img-src加blob:，不增任意路径权限。
- 复用FileContentAssetStore哈希不可变资产/大小与哈希校验/链接路径排除，保存原图副本、裁剪百分比与角度；外部原图移动不会影响重新编辑。封面元数据与world_cover_images绑定按真实世界ID隔离，图片经Bearer读取，不能按其他世界/内容摘要读取；单项解码在线程串行处理，不阻塞世界调度。上传准备素材后才确认正式封面；取消不改展示，准备过的哈希素材暂不自动删除，避免误删共享引用。无外部上传/API/模型用量。
- 新增0030_world_covers仅追加world_covers与world_cover_images表。迁移shape保留0029_LONG_MEMORY_REVISION以及更早历史，HEAD改0030；没有执行用户存档迁移。展示metadata不进入canonical、知识、lore/package/replay或模型上下文。编辑沿用revision CAS；保存响应丢失只读核对，不自动重写。草稿/忙状态接入书架离开保护，迟到原图/裁剪预览不能覆盖新的来源或世界；循环展示副本和真实书共用BookFaces/封面URL。
- 五处桌面声明同步0.1.13，Core/协议/identifier兼容值保持。ESLint/TypeScript、Ruff、Python AST及源码diff检查通过。Pillow完整原始许可自带14处尾空格，保持与wheel字节相同；git diff --check仅对此原始许可路径排除尾空格，所有工程源码照常检查。新PyInstaller Core构建约26.5s、PIL.Image/JPEG/PNG/WebP hook与pillow元数据进入包；首次桌面232模块、Vite135ms、Rust23.34s。补齐裁剪重置/实时预览及全应用防文件导航后最终重编译：Vite232模块/129ms、JS614.91kB（gzip185.51）/CSS39.01kB，Rust release21.55s；精确输出见artifacts/world-covers-desktop-final-build.log。保留主chunk>500kB与STATIC_VCRUNTIME弃用告警；PyInstaller可选tzdata/pysqlite2/MySQLdb及Pillow numpy/olefile/defusedxml未安装，不伪装已验证运行时。
- 现有build-portable.py添加--output-name，用全新目录保留旧包；使用--build-only，不跑内嵌烟测。首次shutil.make_archive因依赖可复现旧日期早于ZIP1980失败，已经改为标准zipfile strict_timestamps=False；程序本身构建成功。独立静态打包脚本补齐说明、复制最终桌面并重新压缩；artifacts/package-world-covers.py和world-covers-package.json记录来源与哈希。最终完整目录artifacts/portable/world-covers/dreamtalk，ZIP同父目录；所有旧完整包保留。
- 静态核对215份Python AST/冻结源码哈希、471份Core文件、26份许可、13份说明及511份ZIP文件逐字节一致；667个本地Markdown目标无缺失。Desktop13,220,352 bytes / SHA256 1A3C28DAAB627817CB76EFA0835DF1454A2D508E0EC5CE424F9D4FAE1FA73603；Core14,615,356 / 9F10583EEB992EAC1AD0FB0422E77A88BF2C064FF7A64860302209953E2F5A1F；ZIP50,729,684 / 6E7CDEC67E1F028669262C5354477DE87110A7A1F6273A8762045FC6547EF050。源码仅本地提交，不push/发布。
- 按AGENTS第20节未新增/修改/运行测试，未启动应用/GUI/浏览器、真实模型/API或读写用户存档/凭据/自启动。编译与包核对不等于真实裁剪/保存/存档升级验收；既有ProductApp旧首页断言待后续授权适配，没有删除、skip或弱化。
- **接下来：** 用户退出旧托盘后直接打开完整0.1.13，核对文字与三面图片保存、只正面保存、标题开关、裁剪重置/旋转、取消/换书保护、多世界与循环副本、重新打开/重启保留及0030正常升级，见[封面说明](docs/WORLD_COVERS.md)。升级后不以旧schema程序打开同一存档；自启动需新版设置显式更新位置，本轮不代改。验收后继续统一聊天/通讯录/设置视觉；本地素材清理可后续规划，目前不自动删资产。暂无新产品选择阻塞。

## 前序切片：2026-10-02 循环拖动书架（桌面0.1.12）

- 从干净c2046bccb6063044b90608232c0b54d7f7a3a786 / codex/world-archive接续，实际仓库D:\LivingWorld。用户体验0.1.11后要求间距略散、首尾循环、至少12本且始终保留空白入口、侧面写世界名、按住鼠标直接拖动；先明确五点，用户随后批准“开始实现”。本轮只完成此书架修订，三图封面和聊天业务页视觉留后续。
- 逻辑总书位max(12,世界数+1)：0世界12空白，5世界7空白，12世界追加第13空白，更多仍留1空白；世界ID与空白索引稳定，没有创建演示存档。间距68→84px，正面／背面／书脊同源BookFaces。**原交接与实现冲突：** 0.1.11确有书脊名称DOM，但整书-90deg与左侧面-90deg使名称背向用户被隐藏；REST现+90deg、悬停+86deg、展示+24deg，修正实际可见方向。
- [成熟复用调查](docs/research/2026-10-02-world-shelf-loop-reuse.md)：精确依赖Embla Carousel React8.6.0，core/reactive-utils锁同版，三包MIT；原许可加入docs/licenses并随包分发。直接复用loop、dragFree、8px拖动点击拦截、document鼠标释放及React卸载清理，不写首尾物理或惯性。只用公开slideNodes/scroll/reInit/settle/API，无internalEngine。React19／TS／Vite8／Tauri2保持。
- 宽窗口12本可能不足以让Embla循环，按视口添加完整圈纯展示副本，内容宽度超过视口并预留书位，序列持续重复。显示总数仍为逻辑书数，每个逻辑书只一个真实button/键盘/读屏入口，副本aria-hidden非焦点图形，点击绑定同一个真实worldId或空白索引，不产生重复世界。平面测量轨道与共享三维书体分开，避免旋转与循环变换互相覆盖。
- 按住书或背景直接拖动、松手惯性减速、拖动后捕获阶段阻止点击；已抽出的书固定在展示位置、背后书排继续移动。抽出从实际点击展示面当前姿态续接，归位按当前书排位置补偿起点；pendingOrigin只有真实选择获准后才替换，取消未保存编辑确认不跳走原书。方向键双向跨首尾，Home/End、Enter/Space、Esc保持；键盘显式激活不依赖残留鼠标点击抑制。减少动画时跳过抽出／按钮滚动动画。目录刷新导致空白数减少时保留创建草稿和稳定RequestId，转到保留的空白入口。
- 现有无默认选书、抽出完成后详情、空白书后出现创建／导入、世界摘要按ID过滤、进入／返回可见租约、Draft→Preview→Commit、背景授权和预算均沿用。无Core／API／表／迁移／权限变更，没有模型调用、读用户存档／凭据或改真实自启动配置。
- 五处桌面声明同步0.1.12，Core／协议／identifier兼容值保持。ESLint／TypeScript和diff静态检查通过。首编Vite220模块／124ms、Rust release23.11s后，补齐副本点击姿态衔接／减少动画状态更新并重新编译最终版本；最终Vite220模块／125ms，JS574.24kB（gzip173.52）／CSS33.80kB，Rust release21.57s；日志artifacts/world-shelf-loop-desktop-build-final.log。保留Vite主chunk>500kB与STATIC_VCRUNTIME弃用告警，没有提高阈值掩盖。
- 新独立完整目录artifacts/portable/world-shelf-loop/dreamtalk，ZIP同父目录；旧0.1.11及此前包保留。沿用完整0.1.11的Core／依赖，逐份冻结源码和文件哈希核对；209份Python源码AST／冻结hash、448份Core／依赖、23份许可、12份说明和484份ZIP文件逐字节核对，659个本地Markdown目标无缺失。Desktop13,209,088 bytes / SHA256 816DBD5F3DDD794048A79C785B6B7E084EF7129E67ECE306441D5BEA64E678DB；ZIP43,228,545 / D345445E2FD77AF855A93566BCE370CA43B5175CE61658724F4970A8E9D339A4。清单artifacts/world-shelf-loop-package.json，静态打包脚本同prefix。仅本地提交，不push／发布。
- 按AGENTS第20节未新增／修改／运行自动化测试、启动应用／GUI／浏览器检查或真实API；源码与编译不等于动效／循环手感验收。既有ProductApp旧首页／下拉切世界断言仍待后续获准适配，没有删除、skip或弱化。
- **接下来：** 用户从旧托盘“退出并停止后台运行”，直接打开完整0.1.12新版，核对直接拖动／松手不误选、双向循环接缝、至少12本并保留空白入口、真实书脊名称、抽出后拖动／归位、快速切换、宽窄窗口、键盘和创建。自启动需新版设置显式保存更新位置，本轮不代改。书架接受后统一聊天／通讯录／设置视觉，三图封面最后做。暂无新增产品决策阻塞。

## 前序切片：2026-10-02 世界书架空间与动效（桌面0.1.11）

- 从干净dee08acf1b3df23aa7c8b547973230043d023371 / codex/world-archive接续，实际仓库D:\LivingWorld。用户明确反馈0.1.10默认选中绝区零后悬停无抽动、右侧信息太早出现、缺少空间感，并提供27.4秒绝区零代理人秘闻视频，随后批准“参考视频效果，现在开始实现”。本轮只完成书架修订，不扩展聊天业务页或三图封面。
- **覆盖首轮需求的最新决定：** 初始横排书脊，没有默认抽出的书或右侧内容；已有／空白书悬停都轻抽，点击完整抽出并转向封面后才出现信息。空白书点击后显示创建／导入选项，再进一步填写名称；切换／取消归位。原“记住世界即选中”和页头常驻新建入口与此冲突，已移除。上次世界仅恢复浏览位置；一本实体书仍代表真实世界档案，可包含多份世界书。
- WorldShelf改为共享perspective、六面厚书体、灰色背板／底板／前缘／接触阴影。原生横向滚动位于三维上下文外，叶子面控制背景亮度，避免overflow／filter／opacity把整本书压平。8个白灰空位只是稳定UI入口，不是假世界或世界数量限制；真实世界封面／书脊写用户世界名，没有复制游戏封面或录屏素材。
- 直接使用CSS3D与Web Animations API：悬停180ms、抽出480ms、归位340ms，换书接续90ms；从当前姿态取消／续接，选中键和epoch过滤迟到完成，750ms兜底避免隐藏标签暂停动画导致详情不可用。减少动画时即时切换，窗口尺寸／滚动变更保持选中书与信息区域的空间关系。方向键／Home／End浏览，Enter／Space选书，Esc／再次点击／归位按钮／背景取消，焦点返回原书。动画只处理界面，不驱动模型任务或世界运行。
- WorldArchivePage将真实世界选择、空白书选择、创建表单和详情就绪分开；选中世界摘要仍按ID防迟到，15秒世界状态只读刷新。宽窗口右侧信息叠在场景留出的区域，窄窗口置于下方；命名表单有离开确认，创建未知结果保留名称和稳定RequestId。创建／导入仍先明确创建世界档案，随后复用原WorldImports／ContentEditor／Draft→Preview→Commit，不增加解析／模型调用。
- [复用调查](docs/research/2026-10-02-world-shelf-motion-reuse.md)：核对Codrops六面书与书脊示例、MDN三维压平边界／原生动画完成和取消、Motion React与Three CSS3DRenderer官方文档／MIT。Codrops是旧实验示例，仅结构参考，不复制旧jQuery／素材；Motion未安装，原生动画承担本轮需求；CSS3DRenderer有100%缩放限制，本轮不引入。保留React19／TS／Vite8／Tauri2，无新依赖／Core变更／API／表／迁移／权限扩大。
- ESLint／TypeScript和Git diff静态检查通过；最终Vite217模块／124ms，JS552.23kB（gzip164.42）／CSS33.25kB，Rust release24.46秒成功（首编155ms／27.48秒后，源码复核发现全局disabled透明度优先级会压平三维书体，补强选择器并重新编译）。五处桌面声明同步0.1.11，PE FileVersion／ProductVersion由打包静态读取核对；Core／协议／identifier仍为兼容基线。保留主chunk超过500kB和STATIC_VCRUNTIME弃用告警，没有调整阈值隐藏。
- 新独立完整目录artifacts/portable/world-shelf-motion/dreamtalk，ZIP同父目录；从完整0.1.10包沿用Core，209份源码AST／冻结源码hash及全部Core／依赖文件逐份核对。许可／说明／ZIP逐字节核对，静态清单artifacts/world-shelf-motion-package.json；构建日志与静态打包脚本同prefix。旧0.1.10与0.1.9目录均保留。本轮仅本地提交，不push／发布。
- 按AGENTS第20节没有新增／修改／运行自动化测试、启动应用／浏览器／桌面检查、真实API或凭据探测；没有读取／修改用户DB、模型配置或自启动路径。既有ProductApp旧首页／下拉切世界断言仍待后续获准适配，没有删除、skip或弱化。编译与静态核对不代表真实动效、键盘或窄窗口验收通过。
- **接下来：** 用户退出旧托盘后直接打开完整0.1.11包，核对初始无详情、已有／空白书悬停、抽出与归位、快速切换、空书创建／导入、窄窗口与减少动画，以及旧世界进入／返回。自启动需在新版后台设置显式更新启动位置，本轮不代改。书架接受后再统一聊天／通讯录与设置视觉；三图封面最后做。暂无新的产品决策阻塞。

## 前序切片：2026-10-02 世界档案书架首轮（桌面0.1.10）

- 从90edd3c6e45c36ff13c897e6939d76dac14d45b3建立codex/world-archive，实际仓库D:\LivingWorld。重构前的90edd3c已备份到用户私有GitHub仓库zhangyeS12/dreamtalk的main和codex/chat-feedback，检查点backup/pre-world-archive-0.1.9；本地完整bundle在artifacts/backups。本轮只本地提交，没有上传新前端或发布版本。
- 用户明确要求“开始优化前端，先明确需求”。沿用已讨论的绝区零代理人秘闻式横向世界书架：没有世界也有白灰空书位；真实世界文字封面和书脊写名字；世界书入口移到这里，三张图片封面最后再做。先在commentary列明范围后实施，未更换React19／TS／Vite8／Tauri2或增加库。需求、交互与边界同步到PRODUCT、README、USER_FLOWS、PRODUCT_SURFACE与[使用说明](docs/WORLD_ARCHIVE.md)。
- WorldArchivePage／WorldShelf／独立CSS以真实世界为书，无假世界、消息、最后进入时间、综合未读、关系或记忆计数。空书仅入口，既有世界不限数量；原生横向滚动／吸附，书的正面／侧面、悬停拉出、选中预览，宽窗口并排详情、窄窗口堆叠、键盘焦点／减少动画。状态通常15秒只读更新，可显式刷新；所选摘要请求有失效保护，不把其他世界内容放到当前预览。
- 直接复用WorldImports／ContentEditor／ModelSetup／CoreClient；通过onlyKind与保存回调区分入口。书架管理世界书手动／联网生成／JSON导入／编辑／文件更新／逐条公共背景，设置保留角色卡。所有原Draft→Preview→Commit、来源、预算、隐藏／公共权限和模型路由保持；没有新解析器或额外付费调用。加载失败前禁止编辑，避免慢旧读覆盖新保存，展开管理定位标题，不出现按钮操作后编辑区在视口外而缺少反馈。
- 明确先创建世界档案再加世界书；未知创建结果保留名称与同一RequestId核对，422明确拒绝才允许改名。取消世界书草稿不删除已创建的档案。入口读取实际世界存在与绑定身份，进入后挂载原四个业务页面；未绑定身份时前往“我”完成从家进入，书架不自动绑定或移动玩家。返回书架／切世界提示未保存的内容／资料／模型／当前聊天草稿及进行中的请求，已发起请求可能继续；不暂停世界或改后台开关。
- 预览与真正进入分离；书架报告worldId=null／visible=false，世界内继续原桌面可见租约，退出业务界面清除租约。预览不会加载或标记聊天已读，后台Core与已授权功能仍按原设置运行。没有用户数据库／配置／自启动操作，其他角色私聊／隐藏事件／关系值不进入普通预览。
- [复用调查](docs/research/2026-10-02-world-archive-reuse.md)：原生MDN scroll-snap／reduced-motion和React状态身份；酒馆独立世界书编辑与绑定作为组织参考。核对酒馆AGPL-3.0与Embla MIT，不复制酒馆脚本／素材；当前原生浏览足够，未装轮播库。Embla官方React文档抓取失败已注明，未据此声称API验证。未生成／导入图片或建立封面持久化。
- ESLint／TypeScript与Git diff检查通过，Vite217模块／120ms、Rustrelease21.21秒完成；PE FileVersion／ProductVersion=0.1.10，五处桌面声明同步，Core／协议／identifier兼容值不变。保留Vite547.28kB主chunk超过500kB与STATIC_VCRUNTIME弃用告警；没有调整阈值隐藏。
- Core完全未修改，沿用完整dialogue-resilience包并逐份核对所有Core／依赖文件及209份冻结Python源码；新独立完整目录artifacts/portable/world-archive/dreamtalk，旧包不覆盖。包内说明／许可／ZIP逐字节核对，具体尺寸与SHA见artifacts/world-archive-package.json；desktop构建日志同prefix。package脚本仅静态／编译产物与字节核对，不运行服务或测试。
- 按AGENTS第20节没有修改／运行自动化测试、启动应用／GUI、真实API或凭据探测，没有读取或升级用户存档。已知ProductApp.test仍断言旧首页立即显示四标签与设置下拉切世界，需要后续获准适配；没有删除、skip或弱化这些测试。代码／编译完成不等于真实视觉、导入、切世界或旧存档运行验收。
- 文档冲突已校正：PRODUCT／README先前把世界创建／世界书导入放在设置，与最新用户书架方案冲突，按最新授权移动入口。README关于Director／世界池／Builder／记忆全未实现的旧概览与既有代码不符，改为已完成受约束切片、完整自主能力仍未完成；旧交接段保留为历史。
- **接下来：** 用户退出旧托盘后打开完整0.1.10包，先验收书架文字封面／空书、已有世界进入与返回、世界书导入／编辑／联网草稿、双世界隔离、窄窗口与键盘。如果使用开机自启动，在新版世界内设置显式保存更新路径，本轮没有代改。下一切片统一聊天与通讯录的视觉／导航，再整理设置；三图封面留最后。暂无新增必需产品决策，现有旧首页自动化断言适配需用户改变测试责任指令后进行。

## 前序切片：2026-10-02 聊天台词与可选资料格式兼容（桌面0.1.9）

- 从1347b0b546efba178ff52fae87da461e3db9a6cc / codex/chat-feedback接续，实际仓库D:\LivingWorld。用户反馈0.1.8仍不回复。只读进程路径确认桌面与Core都来自empty-reply-fix完整包；19:04:50日本时间的安全日志是HTTP200/stop/input7870/output33/max_output173315/prompt_json/json_parse_failed，发生在网关严格JSON验证。此次不是空正文；没有原文证据，不能确定是普通台词、代码块或损坏JSON。未读用户DB、密钥或聊天正文，不重复追查先前与运行不一致的空配置。
- [证据与复用选择](docs/research/2026-10-02-optional-chat-annotations-fix.md)：0.1.8只省略provider response_format，却仍声明强制StructuredOutputRequest，导致应用还没获得台词就拦住回复。直接复用现有json/Pydantic/pydantic-core，聊天附带字段以本地chat_reply_encoding标记承载，structured_output=None；标记不发送服务商，提示与真实payload仍走原用量预留／路由／结算。非聊天严格任务及其他模型原策略保持，没有新增框架、JSON修复器或额外API。
- 完整普通台词在调用身份、终态、Token边界及64KiB校验后可保存，该次没有新事件／长期条目，不补调用；既有记忆和历史原文仍可召回。完整JSON及单层JSON代码块只显示非空reply，资料继续按原句／权限／来源／开关校验。损坏／截断JSON、空正文仍失败，不展示内部字段；重复键和NaN/Infinity拒绝。流式JSON保留渐进reply和终态一致校验，普通台词等待完成验证再显示。私聊／群聊共用，不改Kernel活动、世界真值、角色隔离或捕获开关。
- 官方非流式可选资料聊天新增chat_annotation_response_facts，仅固定枚举和数字计数；旧structured_failure安全事实仍保留。提供商完成不等于应用落库，日志不含正文、推理、模型ID、凭据或自由字符串，诊断失败不改结算也不重发。精确官方DeepSeek Flash/V4 Pro既有小任务thinking策略保持；准确用户模型ID仍未知，未改变真实设置。
- Ruff lint/format4份Python、ESLint/TypeScript、209份AST、5处0.1.9版本、3个完整提示JSON示例、610本地文档链接（0 broken）、Git diff静态核对通过。Core冻结28.454秒、Vite143ms/Rust release27.88秒成功；实际桌面PE FileVersion/ProductVersion=0.1.9。保留tzdata/pysqlite2/MySQLdb可选hidden-import、STATIC_VCRUNTIME弃用、主chunk533.69kB告警，未隐藏阈值。
- 新完整目录D:\LivingWorld\artifacts\portable\dialogue-resilience\dreamtalk\dreamtalk-desktop.exe，ZIP位于同父目录dreamtalk.zip。desktop13,193,728 bytes / SHA256 6B216DBEAC02A92D7EDF1BF70596340E120E5CB46B8087B7CDB1916827EE6421；Core13,969,523 / F3488529ACF9CE859BED0B3FDE8949DE462BDFAFC441DFD336395343ABACF00C；ZIP43,210,022 / 7286B637BB325676E9E89B7DE83729A28A134B59D7C0D1556DF2CB3BA624BA7A；helper保持264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。209冻结源码、22许可、11说明及482ZIP文件逐字节核对。清单artifacts/dialogue-resilience-package.json及Core/desktop编译日志同prefix，source_commit交付前更新为实际本轮提交；旧包保留。
- 没有新增／修改／运行测试、启动应用／GUI、真实API、凭据探测、用户DB读写／迁移或自启动改动。没有新依赖／表／公共契约，Core与协议版本及identifier不变；编译不是实际回复验收，不push发布。本次只读既有安全日志与当前进程位置，没有复用以前单次DB诊断授权。
- **接下来：** 退出旧托盘后直接打开完整0.1.9exe，在后台设置核对版本；有自启动时显式保存更新路径。用户验收普通单聊／群聊、具体计划及重要偏好：纯台词应回复但可能无新条目，合规JSON应同次记录。若仍失败，按本次新的固定计数定位，不承诺损坏JSON或提供商空正文已全部解决，不用提高额度或重新生成角色／世界书。暂无新的用户决策阻塞。

## 前序切片：2026-10-02 全角色空回复共用链路（桌面0.1.8）

- 从干净0121a73 / codex/chat-feedback接续，实际仓库D:\LivingWorld。用户报告0.1.7每个角色都返回空。日志日本时间18:38:11、18:48:03、18:48:15均chat_structured_empty_output，发生在完成HTTP响应的空text检查、事件/记忆解码之前；不是JSON字段错误、截断或未获预算的固定码。不能把前一轮“官方偶发”直接当成反复失败的完整根因。用户表示DeepSeek、上限100000、未开流式，准确API模型ID未知；非秘密配置读取仍见177字节空文档，与日志不符，未将其当作真实配置，不再重复诊断。无用户DB/密钥/正文读取。
- [证据与成熟实现核对](docs/research/2026-10-02-empty-dialogue-transport-fix.md)：官方JSON空正文边界及可省略response_format；LiteLLM的格式提示+客户端验证方法。仅复用当前jsonschema/Pydantic/pydantic-core及预算网关，不引入框架或付费修复。原角色规则仍说“只输出台词”，长记忆示例不是完整传输对象，确认风险但未证明某句造成空返回。
- 仅精确官方https DeepSeek根端点/v1、character_dialogue、chat_event_reply、原JSON_OBJECT_LOCAL_VALIDATE能力改用prompt JSON，_payload与generate统一省略response_format，流式同一_payload。保留结构化请求和非流式严格schema校验、应用decode/流式部分JSON，仅完整非空reply保存，不接受纯文本/截断/思考链替代台词。实际body继续进入保守预留；没有额外API、重试或用户配置/预算/开关变化。世界动态、内容生成、选择器、代理及其他服务保持原策略。
- 统一私聊/群聊角色台词与格式规则；明确无事件/记忆/活动来源仍要自然回答，三个完整reply/events/memories示例及reply minLength=1。无效元数据仍忽略、不付费修复，记忆原句/权限/更正/开关及活动Kernel保持。空回复反馈不再默认让用户改模型设置，解释检查状态只是读取。
- 非流式结构化失败新增安全事实日志，仅固定reason/finish/transport枚举及输入/输出/推理Token、max_output、HTTP status数字；不记录原文/推理/模型ID/schema/密钥。未知字段不当0，新日志失败不影响费用结算或引发重试。旧三次失败细分用量仍无法追溯，不能声称已得知提供商内部原因。
- Ruff lint/format6份Python、ESLint/TypeScript、209份Core AST、5处0.1.8版本和3个完整提示JSON示例、608本地文档链接（0 broken）、Git diff静态检查通过。Core冻结30.425秒，Vite134ms/Rust release26.72秒成功；桌面PE FileVersion/ProductVersion为0.1.8。保留tzdata/pysqlite2/MySQLdb三个可选hidden-import、STATIC_VCRUNTIME弃用、Vite533.69kB告警，未提高阈值隐藏。
- 完整新目录D:\LivingWorld\artifacts\portable\empty-reply-fix\dreamtalk\dreamtalk-desktop.exe，ZIP同父目录dreamtalk.zip。desktop 13,194,240 bytes / 302210FF4A0E7B9A45DB71003CC32E21E97145B00898016B4C30E7DEA5FB7C94；Core 13,967,643 / 5695849573FBA00D29BA2A5AB40374CB5A6DE7BDE669272D0E7AB352773908E7；ZIP 43,204,981 / 569828C9C2C10E92D9CCA25A78917FEC1DA04E0AA52E2533A11BBD06EA94FDCD；helper保持264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。209份冻结源码、22许可、11说明、482份ZIP文件字节一致，旧目录保留。清单artifacts/empty-reply-fix-package.json，两份编译日志同prefix，source_commit交付前更新为实际本轮提交。
- 没有自动化测试、应用/GUI启动、真实API、凭据探测、用户DB读写/迁移或自启动改动；本轮只读安全日志和非秘密配置投影，既有单次数据库许可没有扩大复用。无新依赖/表/迁移/公共契约，Core/协议/identifier保持；编译不等于模型实际回复验收，不push发布。
- **接下来：** 用户退出旧托盘后用完整0.1.8包验收单聊/群聊、寒暄、事件/长期记忆及关闭捕获；自启动需显式更新位置。prompt JSON格式仍可能失败，按本地校验报错，不承诺所有模型输出必然合规；若仍失败，从新版本次安全计数继续定位，不用提高聊天额度或重生成角色/世界书。

## 前序切片：2026-10-02 长期记忆、活动生命周期和近期经历（桌面0.1.7）

- 从干净bf9f367a81c574e61420230d5084ab8f5b31cc65 / codex/chat-feedback接续，实际仓库D:\LivingWorld。用户要求尽快完成长期记忆，并明确要求活动生命周期与聊天参考近期经历一并完成再汇报。[复用调查](docs/research/2026-10-02-long-chat-memory-reuse.md)、[普通使用说明](docs/LONG_TERM_MEMORY.md)。核对Mem0、Letta、SillyTavern、Concordia及Temporal的官方实现边界和许可，实际直接复用项目已安装SQLAlchemy/Alembic、Pydantic、SQLite FTS5/BM25、jieba0.42.1、既有结构化回复/预算/Kernel事务/世界deadline调度与原生React dialog。未复制AGPL代码、引入外部Agent/记忆框架、embedding服务、新依赖或额外提取API。
- 新增0029两张应用层表long_chat_memories/long_chat_memory_settings，保留世界/玩家/角色/来源会话/消息/说话者/UTC与可用WorldTime。正常完整回复同次JSON在reply/events之后返回最多4条身份/偏好/约定/重要经历；原句需逐字属于本轮玩家消息或本次台词，无效元数据忽略、不付费修复。完成回复与来源记忆同事务；群聊公开来源进入获准固定成员的独立记忆，私聊只供对方。提取随当前发言角色开关控制，落库仍逐成员检查各自开关；关闭发言角色自动记录时，该次同调用不会为其他成员额外生成元数据。默认开启，用户可按角色关闭后续写入。非官方DeepSeek或未启用现有结构化聊天的路径保留普通聊天，原文召回可用但不保证自动生成新条目。
- 核心/置顶/相关长期条目最多16条、完整数组8KiB；不重复发送当前玩家全文。明确变更写新条目并关联旧条目superseded，按同说话者或玩家明确取消promise限定更正范围；同来源去重、置顶/停用/恢复及revision CAS有界。角色参与过的本世界/本玩家共同会话先SQL授权筛选再FTS5排序，旧原句最多4条、完整数组8KiB，候选最多200条/正文96KiB。新store替代提示中旧近三页召回，避免重复输入；停用或被更新条目的来源不参与长期档案召回。原聊天/近期上下文不删除，非语义向量检索，可能漏掉同义说法。
- 自动审批先拒绝历史原句外发，用户随后具体授权：只限当前世界/玩家、该角色参与会话的相关原句，最多4条/8KiB，随用户发起的正常聊天发送配置模型，不后台批量外发、不额外API，不读其他角色私聊或隐藏世界书。授权后才实施。权限先在SQL验证当前绑定玩家及该Conversation固定成员，再加载内容；selector不读私人观察或长期条目。普通“长期记忆”页查看自己的共同对话内容，不开放私有EpisodicMemory；原Observation-only来源约束不变，不把自述/计划/聊天认证为WorldTruth/Knowledge。
- 活动原缺口是Director到期仅把候选标finished，没有终止事件。新Kernel settle_routines经受信世界调度调用：active候选到期、状态已变化，或已有PlaceCharacter通过CAS后合法中断时，单事务写唯一CharacterRoutineEnded/Interrupted和获准Observation，并标finished/cancelled。ID由candidate稳定派生、链接原start；不改CharacterState revision/位置/Player/成果，保持后续计划revision衔接。自动活动关闭或attention/planning时仍保留已开始活动的结束deadline，PAUSED不推进，重启不补造未发生过程。旧版已finished且没有终止事件的历史不回填，仅作为原定时段已过。
- Replay增加终止校验：唯一start与单次terminal、角色/活动/原地点/计划时刻、当前presence/revision、时段结束边界；现有事件投影对白名单类型支持结束/中断且先Observation授权。聊天快照提供最新活动终止阶段，以及最多6条本人移动/开始/结束/中断，完整6KiB；当前状态优先、旧完整经历先省略。主体ID、亲历时间与actor/witness区分保持，自然语言不由额外API裁判，活动到期不保证任务完成。玩家事件仍只显示自己获知内容，不出现全知后台时间线。
- 最后自动审批拦截可选“任一群成员开启即生成元数据”的开关联动，担心绕过停用角色设置，同时指出提案校验前的终止调用风险。该补丁整段未执行。采用更安全替代：不改当前独立捕获开关；从ActionProposal execute路径完全移除生命周期调用，仅保留受信调度与CAS验证后放置事务。无待批准补丁或授权阻塞。
- Ruff/格式28份修改Python、ESLint/TypeScript、Git diff静态检查通过；209份Core Python AST、5处桌面0.1.7版本配置、29个单head迁移文件及新2表与ORM列/类型/nullable/PK/检查/唯一/FK静态声明核对通过。初次revision AST遗漏AnnAssign，补充读取后单head核对通过；未执行迁移函数或打开数据库。文档本地链接核对通过，最终数量见artifacts/long-memory-package.json。Core初编24.945秒，收紧提案授权后重编23.616秒；Vite138ms、Rust release24.47秒成功，桌面PE FileVersion/ProductVersion0.1.7。保留jieba第三方SyntaxWarning、tzdata/pysqlite2/MySQLdb可选hidden import、STATIC_VCRUNTIME弃用和Vite533.61kB提示，没有提高阈值隐藏。
- 新完整目录D:\LivingWorld\artifacts\portable\long-memory\dreamtalk\dreamtalk-desktop.exe，ZIP同父目录dreamtalk.zip，旧包保留。desktop13,194,240 bytes / B6C4BBE79FF3CB7071748F39C482B2FCE4E5A88FCE23E2526260464133E340CA；Core13,965,528 / 1751AC42606D0BAEABDD2C3DED3D2FDA2D42DCB7E5001CF7D676B9163436DCF6；ZIP43,202,704 / A3A6AE2EF219C87A26451FF7019FB0C8CC0FA527CD819ED81EF963FA3B423887。helper保持264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。209份冻结源码、22份许可、11份说明和482份ZIP文件字节核对通过；MEMORY/RECALL/STREAMING按旧清单核验后沿用，新增LONG_TERM_MEMORY与原名DIRECTOR_ACTIVITIES确保新说明链接可用。清单artifacts/long-memory-package.json，日志同prefix。打包脚本首次旧清单路径引用错，创建目录前失败；修正引用后全量成功，无用户文件改动。
- 按AGENTS§20未新增/修改/运行测试、启动应用或GUI、调用真实API、读取/写入/迁移用户存档或副本、探测密钥、修改系统自启动。既有单次数据库诊断许可未复用。静态声明/构建/字节核对不等于运行验收；实际保存、模型提取/更正、重启、知情隔离、到期/暂停/中断、预算与自然回答仍由用户验收。Core/协议兼容版本和app-data/identifier不变；新增0029仍沿用现有启动升级流程，升级后不要用旧程序打开存档。没有push/发布。
- 用户入口：旧托盘“退出并停止后台运行”后，直接打开新完整目录exe，无需解压；聊天顶部“长期记忆”可核对、搜索、置顶、停用。体验重要偏好→明确更正→重启回忆，以及自动活动开始→到期→问“刚才在做什么”。换包若使用自启动，需显式保存更新启动位置；本轮未替用户修改注册位置。
- **接下来：** 先根据这轮体验修复记忆提取/更正/活动衔接的真实问题，再决定是否增加成熟语义召回与观察经历总结，费用必须另行具体授权；多人主动联系、相遇剧情、关系推进、任务成果/物品及完整离线世界重建仍未完成。当前交付切片无待用户决策阻塞；不要把共同聊天记忆当私有EpisodicMemory，也不要为了更像完成而伪造活动成果。

## 前序切片：2026-10-02 聊天格式失败和动态池背景条件（桌面0.1.6）

- 从干净2e0f992 / codex/chat-feedback接续，实际仓库仍D:\LivingWorld。用户报告聊天回复失败、世界动态生成未完成，并明确批准本次只读失败错误类别／结束原因／Token数量及世界书公开条目计数诊断；不读密钥或聊天正文、不改存档、不调API。[诊断与接口复用](docs/research/2026-10-02-json-chat-failure-fix.md)、[使用说明](docs/WORLD_EVENT_JOURNAL.md)。
- 确认当前desktop和Core来自world-event-journal完整0.1.5包，非旧自启动版本。最新Core日志15:50:31日本时间记录chat_structured_output_failed：完成响应未过结构化校验。旧日志与AttemptFacts未保存细分reason，不能断言本次一定截断／空输出／缺reply字段，也不能说是密钥无效。截图动态池对应news_background_required；claim在付费dispatch前停止，pending和最近批次仍0，没有已生成但未显示的10条。
- 发现角色“只输出台词”规则在JSON传输规则后。改为角色system规则之后、原顺序会话之前给最终格式要求，明确只有reply字段是角色台词；保留reply/events同次调用和严格本地校验，不把截断／格式错误正文当完整聊天、不另调API修复。核对当日DeepSeek官方JSON／thinking文档及已安装recipe0.1.0：仅官方https端点、deepseek-flash／deepseek-v4-pro的chat_event_reply／world_news_batch小型JSON任务指定thinking disabled；其它任务／供应商／代理／旧模型不变。实际payload继续进入保守预留和财务结算，不增加调用／重试或改用户额度。未证实thinking是此次失败的唯一原因。
- 私聊／群聊、流式／非流式新增固定公开错误：chat_reply_output_limit、chat_reply_empty、chat_reply_format_invalid。安全日志额外记录结构化reason固定枚举，不含原始回复／schema／密钥。当前具体错误可见，旧失败不追溯猜测；失败用量原机制结算，未完成消息不自动重发。
- 公共背景授权和常驻／关键词／quiet触发是两个条件。WorldNews configure开始新批前与claim共用同一公共背景筛选；失败事务不提交设置／候选／批次，也不发模型调用。UI不再一律报“已排队”，直接解释条件和路径：角色卡与世界书 → 编辑适合公开的条目 → 提供条件“常驻背景” → 预览确认 → 重新逐条“公共背景” → 生成新批。仍可选有效关键词触发，不自动公开隐藏设定，不更改世界书触发政策。
- 只读用户数据库分支最初被自动审批拒绝，原因是此前只授权副本诊断；已明确报告并取得上述原存档限定读取授权。查询视图仍为0014／无新版表、mtime9月21日，与本次截图／日志不符，未获得可信的当前失败用量／finish_reason／公开计数。停止该分支，未重复第三次同类读取、读正文／密钥、修改／升级／修复／检查点数据库或停止应用；不能归因用户存档损坏。此诊断权限不是测试授权。
- Ruff lint／format5份Python、ESLint／TypeScript、Git diff核对通过；203份Python AST、5处0.1.6版本和docs内547个本地链接通过。Core冻结40.179秒，Vite213模块／173ms，Rust release27.48秒，PE ProductVersion／FileVersion0.1.6。保留jieba无效escape SyntaxWarning、可选tzdata／pysqlite2／MySQLdb hidden-import、STATIC_VCRUNTIME弃用和主chunk526.88kB告警，未造成编译失败。
- 全新完整目录D:\LivingWorld\artifacts\portable\world-event-fix\dreamtalk\dreamtalk-desktop.exe，不必解压，旧目录保留。desktop13,192,704 bytes / SHA256 0337988D5EFD1121235D01A7742FDB5EC0103E83DE9DF374007330B21704C1CA；Core13,933,137 / F4F2EE693B9F07CDB23C3014CEEFE513954E0138FCB78A1C385F81890899C2F7；ZIP43,151,659 / 862CB9F02C50AFD3CEFB2657253B2FDB31B5F37E61C971960D63535444ED7861；helper仍264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。203份冻结源码、22份许可、9份说明、474份ZIP文件与来源字节一致；三份历史使用说明验证旧清单hash沿用，其余来自当前文档。清单artifacts/world-event-fix-package.json和同前缀两份构建日志，清单source_commit以本次实际Git提交为准。
- 未更改AGENTS、测试、迁移／表、Core协议兼容版本、identifier、存档／自启动配置；没有新增依赖。按AGENTS§20未运行测试、桌面／GUI／浏览器、真实API／凭据探测，没有push／公开发布。源码／编译／包内字节成功不等于运行验收，当前未解决的诊断限制是旧调用细分原因不可追溯。
- **接下来：** 用户从旧托盘“退出并停止后台运行”，打开上述完整0.1.6目录，再到设置“保存并更新启动位置”。先核对普通单聊／群聊回复与聊天获知事件，再按提示确认可用公共背景生成动态，验收逐条发布／8/10续批。没有新决策阻塞；若仍失败，保留新版具体提示和安全日志再定位，不加逐句付费裁判。通过后接用户此前授权的项目后续切片。

## 前序切片：2026-10-01 两块世界事件（桌面0.1.5）

- 从干净7c21c8e / codex/chat-feedback接续，实际仓库D:\LivingWorld。用户批准完成“聊天获知＋API批量世界动态”，同次回复判断事件避免单独分类调用，保留原句、获知时间与变化；DeepSeek优先后续适配其他模型。中断后续接完成，不需再次范围授权。[已批准方案](docs/proposals/2026-10-01-world-event-journal.md)、[使用说明](docs/WORLD_EVENT_JOURNAL.md)、[复用调查](docs/research/2026-10-01-world-event-journal-reuse.md)。
- 复用DeepSeek官方JSON object、已安装pydantic-core部分JSON解析／Pydantic本地验证、原SQLAlchemy／Alembic、公开世界书过滤、世界scheduler／有效WorldTime、治理网关／财务预算及Kernel事件提交；不加依赖／Agent框架／第二调度器，不复制酒馆代码。官方recipe／encoding0.1.0已处理response_format，沿用原Rust输入预留helper及实际JSON请求payload；持久模型配置不改。普通其他供应商聊天保留，自动聊天提取当前仅官方DeepSeek受支持JSON object路由，离线联系消息暂不提取。
- 普通单聊／群聊角色回复同次模型调用生成reply与0～3条activity/plan/rumor/invitation/change。selector不参与提取，UI流式只显示reply，原有台词／截断／费用结算边界保持；完整reply校验后保存。元数据有严格字段／长度／原句／时间原句校验，不合格候选忽略且不调用付费修复；格式不等于语义核实。没有额外分类API，但提示、有限上下文和元数据增加Token用量。角色依旧参考自己的活动／身份资料。
- 回复和chat_story_entries在同一个writer事务保存：实际发言者／消息／会话／玩家固定，source事件须为本人同世界已授权观察，updates须同本人同会话历史。独立获知UTC和有效WorldTime，原话时间不猜现实日期；原句／来源指纹去重，明确改变关联旧记录且不覆盖。读取本人本会话最多6条及已发布公共动态最多4条，按完整记录收缩8KiB不截断否定词。聊天获知每页100条可读更早，用户带revision批注／隐藏不修改聊天；不发WorldTruth、Knowledge、Observation或Memory。
- 公共池每世界默认关闭，当前玩家首次开启确认公共背景和后台费用；只发已确认且逐条公共世界书title/body、世界名、已有动态title。金融路由／硬预算沿用director_plan，运行开关和消费政策独立于日常Director。一次10条有限候选；可用在前6小时，过期12～24小时世界时间。持久随机顺序，首条可立即，随后通常15～45分钟世界时间逐条发布。有效公共背景引用、当前绑定、启用revision、暂停状态和候选时窗再次核对。
- WorldNewsKernel经mutation barrier、writer UOW、同世界有效时间，按候选推导稳定EventId／RequestId／幂等键，原子提交PublicWorldEventPublished v1及候选发布状态。canonical事件表示公告实际发布，不证明正文里的传闻／活动结果。replay核对字段和同世界玩家，不改变物理状态／知识／记忆。未发布候选隐藏；关闭／换玩家／背景变化取消或停止受影响任务，付费中断不自动重发，程序关闭不生成，恢复不补造错过公告。
- 每条已发布动态右侧红未经历／绿已经历／灰跳过，文字／aria／键盘操作并存，revision防覆盖。最近整批固定10条中8条已经历或跳过才自动续批，每批仅一次；发布／过期不计经历，旧未处理保留，未处理上限100。空池未达阈值／attention可显式“生成新一批”，刷新只是读取。UI“世界事件”两块显示，原玩家亲历折叠保留，话题仍编辑草稿后手动发；保存失败反馈不会被5秒只读刷新抹去。每世界／玩家组件key防跨身份旧结果。
- 0028_world_event_journal增加chat_story_entries和四张world_news应用表；冻结显式迁移，保留0027旧版本验证路径。静态AST核对模型／迁移列、类型、nullable、主键、约束和索引一致。没有在用户存档运行迁移；用户首次启动新版按原升级机制升级，之后不应拿旧schema程序打开该存档。
- 源码review、Ruff lint／format23份Python、ESLint／TypeScript、Git diff通过；203份Python AST、五张迁移声明、5处桌面版本、docs内547个本地链接核对通过。Core冻结24.673秒；Vite213模块／129ms，Rust release24.20秒成功，PE ProductVersion/FileVersion0.1.5。保留可选tzdata/pysqlite2/MySQLdb hidden-import告警、STATIC_VCRUNTIME弃用、主chunk526.05kB超过500kB告警，非编译失败。
- 全新完整包D:\LivingWorld\artifacts\portable\world-event-journal\dreamtalk\dreamtalk-desktop.exe，旧包保留。desktop13,192,704 bytes / SHA256 B5E2258F2386BD9E07B60CAD3D1AB1D9DFCE3EB9EE505356FEA1E6C67AF27465；Core13,931,619 / 09AA0280157D7A08866B995E3DC9AEDC598C1ECAEA9D2AFCDBCEEAC340EB75BD；ZIP43,151,137 / 709B19C32B7DAA35C5BA6F759C1DC288D4D16E5AB463BF69253C8EA8D4BEE922；helper仍264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。203份冻结源码／22份许可／9份说明／474份ZIP文件字节一致，MEMORY／RECALL／STREAMING经旧包清单hash验证沿用，其余说明来自当前文档。清单artifacts/world-event-journal-package.json，两份build日志同prefix。
- 交接冲突：上版接下来是活动成果／经历记忆，用户最新明确转为两块世界事件，按新范围执行。OBSERVED_EVENTS和EVENT_MODEL还写Director／候选未实现，与实际代码不符，已明确更正；旧切片记录保留历史含义，不扩大为全项目完成。AGENTS没改，Core／协议兼容版本、identifier和app-data位置沿用。
- 按AGENTS§20未新增／修改／运行测试，未启动／停止应用／浏览器GUI、调用真实API／探测凭据、读写用户DB／配置／系统自启动。静态／编译／字节核对不等于聊天、迁移、暂停／重启、并发、数据隔离已运行验收。没有push／公开发布。所有写入D盘限定为本项目源码／文档／构建并经自动审批允许，没有未解审批拒绝。
- **接下来：** 用户退出旧托盘后打开完整0.1.5包，核对设置版本及程序位置；换目录需手动“保存并更新启动位置”。先用官方DeepSeek普通私聊／群聊核对具体计划／变更／时间／寒暄／批注，再逐条公开世界书、在世界动态设置首次授权，检查逐条发布／手动进度／整批8／10续批及暂停／重启／切世界隔离。没有新的决策阻塞；建议收集误记／漏记原句，沿现有同次提取改进，之后适配其他模型，再接有来源活动成果／记忆及相遇／关系／更完整离线世界。当前不引入逐句付费裁判。

## 前序切片：2026-10-01 回答对应角色自身活动（桌面0.1.4）

- 从干净9aa765d / codex/chat-feedback接续，实际仓库仍D:\LivingWorld。用户明确要求“继续推进项目，回答需要对应角色自身活动”。核对原0.1.3自身阶段快照、授权事件投影、私聊/群聊输入和现有回复校验后，发现亲历资料缺少行动主体/目击者标记，直接persona也未给稳定角色ID；自然语言描述容易混淆自己和他人。交接中“当前角色自己的亲历记录”指本人有权看到，不等于本人是行动主体，本轮把两者明确分开。
- 实现前调查Concordia当日main Observation组件（Apache-2.0）以及NVIDIA NeMo Guardrails事实核对文档/develop许可（Apache-2.0），见[复用记录](docs/research/2026-10-01-activity-identity-reuse.md)。沿用SQLAlchemy、既有观察/主体身份、RoutineActivity、活动快照和模型网关；没有复制第三方代码、安装Agent框架或自行增加关键词事实拦截器。语义核对模型会增加推理/费用与误判边界，本轮没有接入额外裁判模型，也不能把输入身份核对说成所有台词已事实验证。
- KnownWorldEvent追加默认None的内部subject，仅为已有授权白名单事件及有效描述投影typed CharacterId/PlayerId。角色观察输入增加subject_kind/subject_id及participation=actor/witness；跨世界主体拒绝，actor必须等于当前角色typed身份，主体字段一起计入原12条/8KiB资料上限。普通玩家HTTP仍逐字段返回旧契约，不暴露新增内部字段；未知schema/缺失引用不猜主体。
- 自身开始的原单SQL标量查询增取合法activity，CharacterActivitySnapshot追加默认None的RoutineActivity。应用再次核对事件subject为当前owner、活动为领域enum，才加入last_own_activity_start；输入增加speaker_character_id/actor_character_id/activity_kind，仍最多2KiB，沿用有效WorldTime、自身revision/地点及未结束原定时段判定。只读已提交自身来源；没有未来候选、私人状态跨角色查询、新表/迁移、事件/Knowledge/Memory写入。
- 私聊persona加入稳定角色ID；私聊与群聊回复共用ACTIVITY_GROUNDING_INSTRUCTIONS。近况以本人活动类型与阶段为依据，不能把角色卡习惯/公共背景/他人聊天替代真实经历，或把目击他人变成“我做过”；同名/改名不改变主体。原定时段过去不证明完成成果，暂停不推进现实时间；没有自身证据时不编造任务。允许角色语气、情绪和想法自然表达，内部字段不需要对玩家逐条播报。所有供应商沿用原自然文本/stream与费用治理，没有额外模型任务；selector不接收私人活动快照。
- Ruff7份Python、format、ESLint/TypeScript、Git diff通过；197份Python AST、4处桌面版本和Cargo.lock、docs内542个本地链接核对通过。Core冻结25.804秒；Vite211模块/146ms，Rust release27.75秒成功，PE ProductVersion/FileVersion为0.1.4。保留tzdata/pysqlite2/MySQLdb三个可选hidden-import、STATIC_VCRUNTIME弃用和主chunk512.43kB超过500kB告警。一次默认沙箱uv缓存访问被拒后，改用已授权的静态解析执行，成功；没有自动审批拒绝或未解构建失败。
- 完整包D:\LivingWorld\artifacts\portable\activity-identity\dreamtalk\dreamtalk-desktop.exe，旧包保留。desktop13,189,632 bytes / SHA256 D553F5076B3F7135D8948F0B4746F99797C3B61ACB6EB20B1BCCF93E8F8BC5C1；Core13,882,637 / F731BF85ADE3D07CB8B39649E8188DAEA122FEF0F6661679C9EF0C4A2684C48B；ZIP43,076,633 / 7A9073930CF0F31AE551782F193874BF0569857C81C2A3AB8611F124DB6DA869。helper保持264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。197份冻结源码、22份许可、8份说明和467份ZIP文件字节一致；MEMORY/RECALL/STREAMING经上包清单hash核对再沿用，README/DIRECTOR来自当前文档。清单artifacts/activity-identity-package.json，build日志同prefix。桌面0.1.4，Core/协议兼容版本、identifier和用户数据位置沿用。
- 按AGENTS§20没有新增/修改/运行测试，没有启动/停止应用、GUI验收、真实模型调用、凭据探测、用户数据库/配置/系统自启动操作；没有push/公开发布。实现、静态检查与构建完成，不代表真实台词、暂停/重启/并发/跨角色隔离已验收。语言模型仍可能输出与证据不符内容；当前没有语义输出判定器，不能宣称自动保证全部事实。
- 体验：旧程序托盘“退出并停止后台运行”后打开完整0.1.4包；为角色设置初始地点并按已有独立授权开启自动活动，等待实际开始后分别在私聊/群聊问当前和刚才的活动。重点核对两个角色活动不同、仅目击他人、同名/改名、原定时段已过和世界暂停。换包后如需自启动新目录，手动使用既有“保存并更新启动位置”，本轮没有代改。
- **接下来：** 基于用户台词反馈继续改善当前活动衔接，再推进有来源的活动结果与经历记忆。先明确结果类型和形成/纠正规则，再接Kernel与角色输入；到期释放占用不等于已完成成果，不能由台词反写世界事实或自动新增私人Memory。多人相遇、关系/主动联系和完整离线世界重建仍未实现。当前切片没有待用户决策的阻塞；建议先核对活动对应，随后再扩展成果，不为每句话追加付费判定模型。

## 前序切片：2026-10-01 自身活动与聊天情境（桌面0.1.3）

- 从干净68025eb / codex/chat-feedback接续，实际仓库仍D:\LivingWorld。用户要求继续上轮“真实活动与聊天衔接”。先读AGENTS/最新交接及相关观察、事件、时钟、角色活动和上下文；已有亲历事件输入，不重复造事件话题入口。调查SillyTavern官方Author’s Note当日文档（源码AGPL-3.0）和Generative Agents当日main retrieve.py（Apache-2.0），没有复制其代码或安装另一套环境；直接复用已有SQLAlchemy、Observation SQL、中文事件投影、有效WorldTime、聊天上下文与预算，见[复用记录](docs/research/2026-10-01-activity-chat-context-reuse.md)。
- 原输入只有“开始活动”历史和原始微秒，没有当前有效时间/自身状态核对；最新自身开始可能被12条其他亲历观察挤出。本轮新增内部CharacterActivityContextReader，组合根明确绑定当前verified speaker。抽取原character_witnessed_events SQL供两处复用；单SQL捕获同世界时钟、该角色自己的witnessed/event_occurrence且主体为自己的最新已提交CharacterRoutineStarted v1、自身状态revision/地点；只取白名单JSON标量，兼顾json_type与SQLite typeof整数边界，不选整个payload、不读未来candidate或Director input。按同事件ID复用描述投影。
- 当前阶段要求来源非未来、planned_until大于开始、自身revision/地点一致，且now早于planned_until，才是within_planned_interval；planned_interval_elapsed仅时段过去，changed_since_start仅状态变动。后两者不证明现在仍在活动或完成成果。WorldTime用现有monotonic/倍率/暂停机制；经过时间为世界分钟，不转换现实日期。无来源只给时钟，不猜活动。只读快照最多2KiB，超长历史描述省略；没有新依赖、表/迁移、公共API/协议或世界事实写入。
- 私聊将活动快照作为lower-trust USER data放在当前问题前；群聊附到当前speaker输入，不进入selector。原亲历事件、记忆、摘要和公共背景继续复用，新增reader参数默认None保持旧构造边界。台词按既有生成路径发送，费用仍进正常回复预算，没有额外模型任务/后台循环。不能由聊天宣称Player同地点、目击或授予新Knowledge；没有普通UI全知活动列表，也没有改离线联系范围。
- Ruff7份Python、格式、ESLint/TypeScript和Git diff静态检查通过；197份Python AST语法解析、4处桌面版本配置以及docs内538个本地链接核对通过。第一次仅导入排序/格式/101字符长行，修正后通过。Core初编25.304秒；源码复核新增typeof防异常超大JSON整数后重编25.199秒。Vite211模块/130ms、Rust release25.55秒成功，PE ProductVersion/FileVersion为0.1.3。仍有tzdata/pysqlite2/MySQLdb可选hidden-import未找到、STATIC_VCRUNTIME弃用、主chunk512.43kB超过500kB告警，没有提高阈值隐藏。
- 新完整包D:\LivingWorld\artifacts\portable\activity-chat-context\dreamtalk\dreamtalk-desktop.exe，旧包保留。desktop13,189,632 bytes / SHA256 123948AAEDEFD9D6F1D3C872B9A8E651D569F360D4A256D8DBEC3EAC3101EEEF；Core13,881,689 / 5BB160618EED5B43606F6D7F3132F169E78F1455A05056BC41DC90A6CB0FB5B4；ZIP43,070,789 / AA449FF176A95FBE8236BDB0D0063C1DACE7B0914DDFC12FF6AE7D6FC2D92DA9。helper保持264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA。197份冻结源码、22份许可（20份第三方+2份顶层）、8份说明和467份ZIP文件字节核对通过。MEMORY/RECALL/STREAMING沿用上包经已存hash核对的未变说明；README/DIRECTOR用当前文档。清单artifacts/activity-chat-context-package.json，build日志同prefix。桌面0.1.3，Core/协议兼容版本、identifier和用户数据路径不变。
- 按AGENTS§20只做静态检查、构建、文件核对，没有新增/修改/运行测试、启动应用/GUI、数据库读取/迁移/副本诊断、真实模型调用或修改系统自启动/用户配置。没有push/发布。编译不代表模型会准确自然地使用情境，真实保存/暂停/重启/并发/跨角色隔离仍由用户验收。
- 体验：旧程序托盘“退出并停止后台运行”后打开完整0.1.3包；为角色明确初始化活动地点，按既有独立授权启用自动活动，实际活动开始后在私聊或群聊问“你在忙什么”“刚才做了什么”。状态与记录无证据时不得期待真实活动细节。换包后自启动需显式“保存并更新启动位置”，避免单实例继续打开旧进程。
- **接下来：** 推进有来源的经历记忆与真实活动结果，先限定结果类型、形成/纠正规则，再接Kernel和角色输入；不能把占用到期伪造成果。相遇剧情、多人主动联系/关系和完整离线重建仍分项未完成。当前切片没有待用户决策的阻塞；已有前端chunk告警可独立按成熟lazy/code splitting优化。

## 前序切片：2026-10-01 角色初始活动地点

- 从干净`1d735a918328611871fcbd9daf1ad49699688257` / `codex/chat-feedback`接续，实际仓库`D:\LivingWorld`。用户授权继续，完成前轮排定的普通角色初始活动地点入口。先读AGENTS/交接、PlaceCharacter/聊天实例化、地点目录、Director及产品/持久化边界，再调查成熟实现；[复用记录](docs/research/2026-10-01-character-activity-setup-reuse.md)核对SillyTavern1.19.0（AGPL-3.0）的Scenario/WorldInfo及Generative Agents当日main（Apache-2.0）的既有地点规划。未复制其实现或引入新依赖，复用当前Kernel、SQLAlchemy、React受控表单和API client。
- 确认交接缺口：打开聊天只创建Character/Conversation，不能让没有CharacterState的角色进入日常规划。原DIRECTOR_ACTIVITIES步骤2及director_characters_required提示却让用户仅打开聊天；PRODUCT_SURFACE也暗示有家便可活动。已纠正为“打开私聊 → 明确确认初始地点 → 开启自动活动/显式重规划”，以实际代码为准。离线主动私聊依旧不需要物理地点。
- 新`GET /worlds/{world}/activity-characters`只返回当前绑定玩家的私聊角色名/ID及是否已设置，不返回当前地点、未来活动、私人资料或事件。复用ChatConversationService的当前已接受角色名及SQL权限过滤；初始化存在性只在已授权私聊身份范围内投影，旧玩家/World/client返回不会覆盖新界面。
- 新`POST .../activity-characters/{character}/initial-location`携带当前玩家、目录地点和X-Request-Id，薄服务调用原PlaceCharacter，expected_state_revision固定None。新增可选activity_player_id默认None，旧命令fingerprint保持；本入口指纹包括玩家且不允许非初始revision。Kernel持有writer后同事务核对当前绑定/私聊归属、本世界目录或真实初始家、没有CharacterState及原16名已放置角色容量，然后走原CharacterPlaced/state/receipt。无新表/migration/event版本、直接SQL世界状态写入、Player移动、Observation回填或另外的放置执行器。
- 普通设置新增“角色初始活动地点”，不预选角色或家、不批量放置；已经设置的角色只能显示存在性，不能再次放置。保存不调用模型，不自动开启Director、立即打断旧批或主动请求新规划；旧缺角色attention需用户显式点击“重新规划”。按已有后台授权和正常批次运行。原自动活动提示与已过时“主动联系尚未开放”的交流状态文案同步修正。
- 保存同步锁/请求序号、World+Player组件key和client失效保护保持；未确认结果保留角色/地点/原请求，未知错误不自动重放。只读刷新可显示已设置，但不把存在性当本次回执；同ID重试读原回执，不在角色后续已移动时再放置。确定固定码拒绝显示具体提示。切世界/新世界/切身份前保护未保存设置，关闭编辑会话后可重新只读核对是否已有初始位置。
- Ruff11份Python检查通过；首次仅导入/长行/格式问题，按无缓存格式化后通过。ESLint/TypeScript、diff静态检查通过；文档链接570个本地目标0 broken，190外部URL仅计数。Core PyInstaller41.591秒成功，Vite211模块/119ms、Rust release26.70秒成功；PE ProductVersion/FileVersion为0.1.2。保留tzdata/pysqlite2/MySQLdb可选hidden-import、STATIC_VCRUNTIME弃用及Vite主chunk512.43kB超过500kB提示，未提高阈值隐藏。195份冻结Python、22份许可、8份说明、desktop/Core/helper及465份ZIP文件字节核对通过。
- 完整独立新包`D:\LivingWorld\artifacts\portable\initial-activity\dreamtalk\dreamtalk-desktop.exe`：desktop13,188,608 bytes / SHA256 `2C76A382338B6B24929904F663508A78317EBFDAE3BD30E4CE731752A0651976`；Core13,874,046 / `16E6D1A8BA1E347047C0B0909D56E04A41FE793CD0AC397A00D1825027139B35`；ZIP43,056,796 / `37898F5108218A70F1BDBDC3EA5FA299AF0E8BD6CC92911F04279A1620198180`。helper保持`264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。清单`artifacts/initial-activity-package.json`及Core/desktop build日志同prefix；随包README/DIRECTOR/ACTIVITY_LOCATIONS更新，旧包保留。桌面版本0.1.2，Core/协议兼容版本与identifier不变，0.1.1自启动路径修复沿用。
- 按AGENTS§20没有新增/修改/运行测试、启动应用/GUI、真实API/模型调用、原存档或副本诊断/迁移、用户配置/系统注册变更；只编译和静态核对。旧副本诊断授权不复用。未push/发布，实际保存、重开、跨世界/身份、并发/重试和Director活动仍由用户验收。
- 用户入口：从旧程序托盘右键“退出并停止后台运行”，打开完整0.1.2包；在通讯录打开私聊，设置 → 角色初始活动地点 → 刷新 → 选择角色/地点 → 确认；再按独立授权开启世界自动活动。更换包后若使用自启动，保持勾选并保存更新位置。普通UI不会列出角色后续隐藏地点。
- **接下来：** 继续完善真实活动记录与聊天话题的衔接，并根据用户实际体验处理问题；不要用开始活动/时段结束伪造成果，也不要把位置或他人事件公开成全知时间线。多人主动联系/关系推进/完整离线世界重建仍是独立未完成范围，实施前需形成具体边界。暂没有待用户决策的阻塞。前端主chunk增长可在后续通过成熟React lazy/Vite拆分改善，而非提高告警阈值。

## 前序切片：2026-10-01 桌面版本与自启动路径更新

- 从干净`645c37b393e3013e7f7752efad80cc6c48d0b096` / `codex/chat-feedback`接续，实际仓库仍`D:\LivingWorld`。用户要求继续，按照前一轮建议先完成版本/自启动更新，下一步才是普通角色初始活动地点。前序排查曾确认真实HKCU登记仍指向offline-contact旧包；这不是本轮修改后的系统验收证据，本轮没有重新读取或改写真实注册。
- 根因在`configure_desktop_background`：原来只有开关变化才enable，插件is_enabled在Windows判断已登记/StartupApproved，不比较exe路径，因此新版保持勾选并保存不会刷新旧地址。直接复用官方autostart2.6.0及既有auto-launch0.5.0的enable覆盖登记，保持--background和单实例/托盘生命周期。调查来源、发布源码核对及许可见[本轮复用记录](docs/research/2026-10-01-startup-version-reuse.md)；没有新依赖、手写注册表或另一个Agent框架。
- 现在用户开启自启动时，每次显式保存都登记当前程序；按钮在保持勾选时仍可用，标为“保存并更新启动位置”。刷新只读，启动时不静默注册，默认关闭不变。托盘配置先准备临时文件；部分失败明确反馈，不冒充已恢复未知旧程序路径。前端请求锁/序号防重复保存、旧返回和卸载后的写入；“刷新设置”可从读取失败恢复，明确会恢复已保存的选项。
- 后台设置显示`AppHandle.package_info().version`和`current_exe`提供的当前版本/程序位置；这不是原注册目标的读取。桌面Cargo/Tauri/npm workspace及lock版本同步0.1.1，Core和其他workspace保持0.1.0，identifier与数据目录不变，无DB migration。编译产物PE的ProductVersion/FileVersion均为0.1.1。
- ESLint/TypeScript、cargo fmt和diff静态检查通过；Vite210模块/175ms，Rust release30.02秒成功。保留STATIC_VCRUNTIME弃用及主chunk505.29kB超过500kB的提示，没有提高阈值隐藏。Core未重编，复用645c37b的修复版并核对193份源码及冻结文件一致；22份许可、8份说明和463份ZIP文件字节核对通过。
- 完整独立新包`D:\LivingWorld\artifacts\portable\startup-version\dreamtalk\dreamtalk-desktop.exe`，desktop13,188,096 bytes / SHA256 `CA8044D495E6E5F39A355855AEC2CFB4A07351ACEAABBA12046714E4337D0613`；ZIP43,045,133 / `F1558BF5B76F25D69F3BAE6D67A437F69314FDF800E73B72CDACAA27B7E38A04`。Core保持`62FE65A44D67F272C8A685C8043A16BD8B4C2F2F66FEAF1DEA8A55961D789BAB`，helper保持`264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。清单`artifacts/startup-version-package.json`、编译日志`artifacts/startup-version-desktop-build.log`；随包README/OFFLINE_MESSAGES已更新，旧包保留。
- 按AGENTS§20，仅静态审阅、编译、打包和文件核对；没有新增/修改测试、运行测试/GUI/应用、模型调用、存档诊断/迁移、真实自启动或用户配置变更。上轮临时副本诊断授权没有扩大复用。没有push/发布。此前角色主动消息是否已经成功投递仍没有新的运行证据，不把开启成功或用户“很好”当作此项验收。
- 用户入口：从旧程序托盘右键“退出并停止后台运行”，打开完整新版，在设置 → 后台运行核对0.1.1及路径；保持自启动勾选，点击“保存并更新启动位置”。下次登录后核对真实版本/路径；保存失败可原地刷新。
- **接下来：** 先调查成熟角色地点/活动设置方案，再复用现有Kernel的角色放置/地点命令，为普通通讯录角色提供显式初始活动位置配置；不能自动把所有角色放进玩家家，也不能因修离线联系移动玩家。然后完善活动与对话的衔接。暂无需用户另行决策的阻塞。

## 前序切片：2026-09-29 离线联系保存失败与刷新入口修复

- 从 `c0f0af18bb9b5661756c85b870329643f279a48d` / `codex/chat-feedback` 接续，实际仓库 `D:\LivingWorld`。用户反馈离线设置任意保存均显示“未能保存，请刷新状态后重试”，界面却没有刷新入口；用户已自行从托盘退出，并明确授权**这一次临时存档副本保存诊断及必要升级**，不调用模型、不改原存档。没有将授权扩大到测试套件、应用启停或真实API。
- 根因路径已通过副本诊断重现：通讯录 `ChatConversationService.open_direct` 仅创建 Character，不必创建 CharacterState/物理地点；OfflineContactStore原 `_capture` 直接调用Director日常 `planning_input`，后者只查询已放置角色，因此抛出 `DirectorError(director_characters_required)`；HTTP将其吞为500/offline_request_failed，前端再吞为笼统保存失败。不能要求用户靠提高Token、增加地点或重试来绕过。
- 离线输入现先绑定本World/Player已打开的direct会话，最多16位；将原Director已确认角色persona SQL字段投影提取为 `approved_persona` 由两处共用，不另写解析器。离线读角色名字/description/personality/background/accepted版本及合规公共背景，用角色名触发公共背景；既有活动意图也限制到这组角色。无需角色地点、Director开关、32地点容量；总资料仍64KiB，恢复/版本/去重/未回复/Busy/暂停/预算规则保持。没有新依赖或migration，没有放置角色、移动玩家、增造世界事件；Director日常输入仍要求已放置角色。
- 新 `useOfflineContact` 统一只读状态与显式保存：请求序号、任务身份、World/Player/client作用域拒绝旧GET覆盖POST或切换后的状态；同步写锁防重复，失败不自动POST或付费重试。GET连续两次失败停轮询，手动刷新成功或保存成功恢复只读轮询。保存错误与读取错误分开，后台GET不会吞掉保存失败提示。
- 设置区增加“刷新状态”/读取中/保存中，保留失败后的时长和授权界面。存储占用、结构/完整性/可用性、角色关联、公共背景容量与格式、内部异常均返回固定安全码及具体提示；日志仅固定码，不记录SQL/参数/异常正文、角色资料或凭据。刷新仅读取，不能修复真实坏存档，也不会重新提交设置或调用模型。
- 存档取证限制：运行期间只读SQLite曾报告SQLITE_CORRUPT；退出后稳定副本却是0014且quick_check正常、没有当前玩家/聊天表，与运行日志的当前world和core_ready不一致。**不能据此判定当前存档已损坏或覆盖恢复原文件**。原三文件已备份并核对字节，保存在 `artifacts/offline-contact-save-investigation/original`。后续仅升级系统Temp临时副本；因无可用玩家，使用既有生产Kernel/内容确认/通讯录服务在该副本建立一个诊断角色（未放置），不是原当前世界完整重建。原版保存真实报上述DirectorError，修复版同路径保存为enabled=true/hours=1/revision=1/idle，eligible=true/1角色/仅批准persona字段；保存未新增WorldEvent，未调用任何模型。有限诊断记录 `artifacts/offline-contact-save-investigation/authorized-copy-diagnostic.json`；原存档/备份未覆盖、未删除WAL，没有自动修库。
- Ruff lint/format（4份Python）、ESLint/TypeScript、diff检查通过；首次Ruff只发现导入排序，修正后通过。Core PyInstaller37.356秒、Vite210模块/Rust release26.43秒成功。沿用tzdata/pysqlite2/MySQLdb可选hidden-import及STATIC_VCRUNTIME弃用提示；Vite新增主chunk503.66kB超过500kB提示，属于后续页面拆分建议，未通过抬高阈值隐藏。193份Python、22份许可、8份说明、desktop/Core/helper与463份ZIP文件字节核对通过。
- 完整独立新包 `D:\LivingWorld\artifacts\portable\offline-contact-save-fix\dreamtalk\dreamtalk-desktop.exe`，desktop13,185,024 bytes / SHA256 `5090360C7C8AFE62944E4534D7ED730D9100D9129388091C38F098D0EAC39D9E`；Core13,865,061 / `62FE65A44D67F272C8A685C8043A16BD8B4C2F2F66FEAF1DEA8A55961D789BAB`；ZIP43,041,469 / `6429F323377189A5FCCC2C3CB452059E68B95C0BABD994AAEBAB574F30991D66`。helper保持 `264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。清单 `artifacts/offline-contact-save-fix-package.json`，日志同prefix；随包OFFLINE_MESSAGES/README已更新，旧包保留。
- 本轮唯一运行例外是用户批准的上述副本保存诊断，没有新增/修改现有测试、运行套件/GUI smoke/应用/真实API/系统自启动设置或原用户存档迁移。编译和有限诊断不等于真实离线恢复、并发界面、权限隔离或模型质量验收。没有push/发布。
- **接下来：** 用户打开完整新包，设置 → 离线期间的消息 → 刷新状态 → 确认开启；优先核对能够保存，再验收既定离线恢复。若仍有错误，按新固定码继续定位真实数据，不能用旧0014副本当最新存档恢复。另一个后续产品缺口是普通聊天角色的活动初始位置配置：日常Director仍需已放置角色，不应为修离线私聊偷偷放到玩家家或扩大行动权限；本轮没有实现地点初始化。无待批准步骤。

## 前序切片：2026-09-29 后台启动与有限离线主动消息

- 从干净 `83cdd3171820ce488fd00b0a15272c1155daad48` / `codex/chat-feedback` 接续，实际仓库仍是 `D:\LivingWorld`。用户明确批准“按你的建议，开始实现”，中断后要求继续；本轮完成这个有限切片，不把“继续”当作上一版运行验收或自动启用用户配置。
- 实施前调查官方 Tauri autostart/single-instance/system tray。直接复用 autostart2.6.0、single-instance2.5.0、解析后的Tauri2.12.0、tray-icon0.25.1及MIT auto-launch0.5.0；不自写注册表/服务/托盘或引入另一个Agent框架。来源、许可与决定见[复用记录](docs/research/2026-09-29-offline-contact-reuse.md)，具体切片见[方案](docs/proposals/2026-09-29-offline-contact.md)。新增组件原始许可随包保留；项目仍Apache-2.0。
- 桌面设置新增“登录电脑后自动启动，保持窗口隐藏”“关闭窗口后继续在托盘运行”，默认关闭，只有用户显式保存才变更启动注册。官方单实例复用已有进程，普通重复打开唤起窗口，`--background`不弹窗。托盘双击打开，右键明确退出并停owned Core；后台仍运行既有Core/Director，关机时不会执行AI。便携包换路径后需关闭再开启自启动以注册新位置；没有替用户改注册表、应用配置、存档或凭据。
- 新OfflineContactService/store以真实UTC每分钟轻量checkpoint、正常退出补记录。默认6真实小时，1–168可配置；首次开启/修改只建立基线。设置只绑定一个World/Player，与每轮聊天Token和Director6小时WorldTime分开。睡眠/重开时超过阈值才记录一次恢复，最多一个现有已打开私聊角色/一条问候或邀请；模型可不联系。Available/RUNNING、绑定/accepted版本/公共背景/current Player message标识均复核，Busy/暂停/不合适/上下文改变则停，同一理由唯一回执及上次主动私聊未回复守卫防催促。queued/planning/writing重启转interrupted，失败/中断不自动付费重放。
- Director只生成有限角色/目的/时段计划，Character单独生成最终台词；复用现有各提供商配置、governed gateway、可信输入预留、Token/金额预算和真实用量账本，最多两个有限模型任务，每次输出最多8192或更低模型上限。输入采用离线前冻结的已接受persona、逐条公共世界书和已有活动意图，计划不当已执行事实。自动审批拒绝新增私聊正文外发；安全替代已落地：不读取或发送私聊正文/摘要/私人记忆/隐藏设定，本地消息ID和位置仅用于去重，不发给模型。所有剩余工作获准完成，无待授权阻塞。
- 新0027_offline_contact为additive：三张操作性表、ChatTurn.kind默认player和ChatMessage可空story_sent_at_utc。正式历史位置/真实created_at不改；独立outreach turn不伪造玩家Message，原玩家reply/claim入口不接受此kind。投递原子保存message/dispatch/episode；剧情时间严格在离线区间内，真实生成/用量在恢复之后。普通消息仍显示真实时间，离线消息可展开“时间详情”；隐藏窗口不清未读，实际可见会话标已读。迁移旧版本shape排除新增表/列，未执行任何数据库迁移或运行验收。
- 新本地UI短租约在desktop启动前清为不可见，Rust核对主窗口visible+focused，前端定期续约、失焦/隐藏撤销。PlayerRepository现场见证查询排除不可见/其他世界的本地绑定玩家，位置/availability不动；已知事件与角色规则保留，不把后台隐藏启动当玩家亲历，也不制造过去WorldEvent、活动成果或知识。
- Ruff lint/format17份Python、ESLint/TypeScript、cargo fmt及diff检查通过；Core PyInstaller30.521秒成功，Vite209模块/Rust正式release24.04秒成功。首次Rust编译的两个实际Tauri接口错误已修正后重新成功。Core沿用tzdata/pysqlite2/MySQLdb三个可选hidden-import警告；Tauri升级后出现STATIC_VCRUNTIME弃用提示，保留原静态runtime策略，后续工具链升级处理。新依赖文件旧时间戳导致首次ZIP失败，改为只对ZIP头钳制1980边界，文件字节哈希不变。193份冻结Python、22份许可、8份说明和desktop/Core/helper核对一致。
- 新包 `D:\LivingWorld\artifacts\portable\offline-contact\dreamtalk\dreamtalk-desktop.exe`，desktop13,184,000 bytes / SHA256 `4CF48EE3F61A8DE550450968E5157AC9D5D6E1B5E22AD7AD2D55E9C73FBAE379`；ZIP43,037,135 bytes / `9205D36D96DAC357707FB6451EB5411E10180B7AC5289D82F74CB73B8CE6189D`；Core13,862,986 bytes / `99112B8B6EDE3CBF9915E62A00B798735881621BCBA6B2F2212B13A65B7038E1`；helper保持 `264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。清单 `artifacts/offline-contact-package.json`，两个build日志同prefix；随包新增OFFLINE_MESSAGES、同步README/DIRECTOR，原活动地点/事件/记忆/召回/流式说明保留，旧包不覆盖。没有push/发布。
- 按AGENTS section20未新增/修改/运行测试、CI、GUI smoke、应用启停、live API或用户存档迁移。源码、编译、哈希不是自启动/休眠/取消/权限隔离/实际模型质量验收。台词的格式、长度、来源和投递边界有校验，不把提示词中的语义禁止宣称为确定性事实验证。当前仅单角色离线消息；多人共同目的Episode、在线持续主动消息、关系推进和完整离线世界/成果重建仍未完成。
- **接下来：** 用户打开完整新包，在“后台运行”和“离线期间的消息”分别开启并确认用量，实际验收登录隐藏、托盘退出、睡眠/重开阈值、Busy/暂停/未回复跳过、剧情/真实时间和未读。默认6h，可先1h体验；没有立即付费测试/强行补发按钮。后续优先修复反馈，再讨论更丰富但有证据的主动话题及有限离线生活重建；新功能仍先查成熟实现。本轮没有必需用户回答的新问题。

## 前序切片：2026-09-29 地点重复界面修复与离线说明

- 从干净c3727c8 / codex/chat-feedback接续。用户截图出现上下两个活动地点，上方不响应输入，下方可用，并问程序是否需一直打开/关机后停止。实际仓库D:\LivingWorld；先核对AGENTS、HANDOFF、相关源码与Git。用户反馈不等于Director整体运行验收。
- ProductApp JSX只有一个WorldLocations入口，但它与同级WorldImports都用world.world_id作key。核对本地React/react-dom19.3.0开发源码及[React官方key规则](https://react.dev/learn/rendering-lists#rules-of-keys)、[ReactChildFiber官方源码](https://github.com/facebook/react/blob/main/packages/react-reconciler/src/ReactChildFiber.js)：同级key须唯一，重复key可能重复/遗漏节点。此明确代码缺陷与截图旧无状态表单/新有效表单符合；未通过GUI重现，不能把静态判断写成运行验收。
- 修正settings同级组件为locations:<World>、content:<World>、activities:<World>:<Player>，原World/Player变化重挂载边界保留；没有第二个地点入口、没有改请求/数据库/迁移/Kernel。用户需退出旧版再开修复版，清除旧页面残留；本轮未替用户操作应用。
- 核对desktop ExitRequested → supervisor.stop、Director closing/fail/interrupted、候选end_at过期及window_end续批、startup UTC bridge。当前本地自动活动要求进程仍运行，可最小化/切其他页；退出/关机/系统睡眠不继续AI执行。重开时RUNNING world按离线elapsed/scale推进时间，PAUSED不推进；有效旧候选可当前时间开始，错过end过期，不完整补造离线生活/成果/亲历历史。中断模型任务不自动重放；主动联系尚未实现，普通玩家消息触发的单聊/群聊回复不等于主动发消息。
- UI自动活动/交流状态直接说明本地运行、最小化、退出/关机及主动消息未开放，避免可用状态被误解为已经自动联系。DIRECTOR_ACTIVITIES去掉过时硬编码0025升级提示，增加当前开关/恢复说明；ACTIVITY_LOCATIONS记录重复key修复。仅澄清现有行为，没有新增离线策略、后台服务、云服务器或主动联系。
- ESLint/TypeScript、diff检查通过；Vite206模块、Rust release22.95秒构建成功且无新增warning。没有Python变更，复用上轮Core，不做无意义重编译；原Core的tzdata/pysqlite2/MySQLdb可选警告属于上轮冻结记录。按AGENTS未新增/修改/运行测试、GUI smoke、应用启停、模型/凭据探测、用户DB/配置/密钥或迁移；静态/编译/哈希不是GUI行为与生命周期验收。
- 新包D:\LivingWorld\artifacts\portable\location-catalog-fix\dreamtalk\dreamtalk-desktop.exe，desktop12,424,192 bytes / SHA256 `7A9310CCAA118FF8EDA36B8C9C2FF3768F1CC2E2245D87B3BCB01BCC7563A65B`；ZIP42,745,007 bytes / `80954EF9CE5B9FBF3FA16CFE9A05A97FF21479590348F8628173BAA8EFAEC5F0`；Core `7F0A817CC2B534AFD15DD40A244970B733BE1A758FCDA4555C9CE20EF1D0CD6B`及helper `264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`与原包一致，14份冻结Python源、13份许可与desktop/Core/helper核对。说明同步随包DIRECTOR/ACTIVITY_LOCATIONS，其他说明保留。清单artifacts/location-catalog-fix-package.json，日志location-catalog-fix-desktop-build.log。旧包保留，无push/发布。
- **接下来：** 优先用户验证重复界面消失及地点保存。建议下一块讨论/补齐有限离线恢复，沿用AGENTS第7节catch-up方向而非要求长期挂机；仍先查成熟实现，不擅自回填旧世界事件或放开主动联系。玩家前往地点与Outreach理由/episode决策仍待明确；此轮没有新增问题要求用户授权。

## 前序切片：2026-09-29 普通设置手动活动地点

- 从干净78b7055 / codex/chat-feedback接续，实际仓库D:\LivingWorld。核对AGENTS、HANDOFF、产品P-07/地点/Kernel动作契约与源码后，选择上一轮建议的普通地点配置切片；玩家移动过程/层级仍未定，未擅自实现前往、地图或耗时路径。当前“继续”不视为上一轮Director运行验收。
- 实现前查[SillyTavern官方World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)、release package1.19.0/AGPL-3.0与Generative Agents当日main plan.py/Apache-2.0。复用现有CreateLocation/Kernel、SQLAlchemy/SQLite事务、Alembic、请求回执、React和客户端，无新依赖、第三方源码复制、另一套模拟/地图/调度器。[调查与范围](docs/research/2026-09-29-location-catalog-reuse.md)。
- 新WorldLocationsService与鉴权GET/POST /api/v1/worlds/{world_id}/activity-locations，仅ID/name/is_home。SQL按本世界本地创建目录先授权再投影名称，额外仅读取既有启动流程确定ID且名为家的初始地点；不枚举其他后台Location、角色位置/状态/未来候选/事件/私人资料。目录属于单本地用户app-data创作配置，不是Player Knowledge或多人权限模型。
- 复用CreateLocation，新增list_locally默认false，true才加入指纹；旧setup/家创建指纹和LocationCreated v1事件payload不变。Kernel同一writer-reserved UOW检查规范同名/实际地点容量，创建canonical事件、Location投影、目录与CommandReceipt。request UUID按World派生地点ID，旧回执重放不写；跨World或不同参数复用request冲突。NFKC/casefold键防同世界规范重名；家名称保留。最多沿用Director32实际地点，尚无家时留一个名额；不读取隐藏地点名称做重名检查。
- 新0026_local_location_catalog additive表带World/Location FK、同世界名称唯一；没有回填、公开旧后台地点或修改canonical重放输入。迁移shape验证区分0025及更早，显式排除后续目录。既有projection rebuild延迟FK且恢复Location，目录不删除/重建。没有运行任何DB迁移，此说明是静态实现审阅，不是迁移验收。
- 普通设置新增活动地点表单/有限目录/刷新/保存中/附近错误和成功通知。立即锁定防双击；失败保留名称，网络/5xx未决保留原request ID可手动重试；GET仅核对，不自动提交。同名只作提示，同request回执确认本次保存。读请求序号防旧GET覆盖新保存，切世界/创建新世界前提示草稿；名称和未决请求在当前编辑会话内保留，关应用后读目录核对，同名限制避免重复。沿用现有product样式，CoreRequestError兼容可空code。
- 新地点只是已有场所集合：不移动玩家/角色、不从世界书自动创建场所、不授予事件知情、不编写最终台词/关系/主动联系/活动成果。添加和读取不调模型，不触发额外付费replan或重写旧批；已开启Director下一次常规批才会考虑，不能保证模型每批选择所有地点。名称入现有规划输入范围，表单明确说明。背景仍通过已有逐条公共世界书。
- 修正SCENES_AND_PERCEPTION把0024/Director未执行写成“当前”的过时段落，标注历史阶段并补当前0025/0026状态；感知规则未变。PRODUCT_SURFACE/PRODUCT_SPEC/DIRECTOR_ACTIVITIES及新ACTIVITY_LOCATIONS说明与本轮范围一致。AGENTS未修改；无新授权/审批阻塞。
- Ruff lint/format14份Python、ESLint/TypeScript及diff检查通过。Core冻结25.67秒；Vite206模块、Rust release22.55秒成功。沿用tzdata/pysqlite2/MySQLdb三个可选hidden-import警告，desktop未新增warning；Git原换行配置继续提示LF/CRLF，未改配置。按AGENTS未新增/修改/运行测试、CI、GUI smoke、应用启停、真实API、凭据探测、用户DB/配置/密钥操作；静态/编译/哈希不代表运行或权限验收。
- 新包D:\LivingWorld\artifacts\portable\location-catalog\dreamtalk\dreamtalk-desktop.exe；desktop12,424,192 bytes / SHA256 `B7E16F1EBCC69C0486640EB08BF328F6660D016D63CE8C3C21C92255AC244A90`；ZIP42,744,075 bytes / `91D0432F129F7722094A0B44E8A717531A4161968A0379519C2EA6A7B3E4B5DC`；Core `7F0A817CC2B534AFD15DD40A244970B733BE1A758FCDA4555C9CE20EF1D0CD6B`；现有helper `264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。14份源码、13份许可、desktop/Core/helper核对一致，清单artifacts/location-catalog-package.json，两个build日志同prefix。随包新增ACTIVITY_LOCATIONS及当前DIRECTOR，原EVENTS/MEMORY/RECALL/STREAMING保留。组包曾因猜错helper路径中断，查实际产物后完成核对/ZIP，没有删除旧包或宣称未核对产物完成。没有发布/push。
- **接下来：** 优先用户真实反馈。建议先明确Player前往地点的普通交互，最小方案为显式点击即时切换、沿用已有MovePlayer/Kernel CAS/Scene退出/Observation，聊天不移动；P-07移动过程尚待产品结论，本轮没有该入口。再扩展更有辨识度的活动、离线恢复与主动联系；后者必须先明确P-03/P-04，不能由“继续”隐式放开。建议先配置2–3个有区分度的场所及简短常驻公共背景，观察下一常规规划；不为每个地点新建模型任务。

## 前序切片：2026-09-29 公共世界书参与日常规划

- 从干净2a44262 / codex/chat-feedback接续，实际仓库仍为D:\LivingWorld。核对AGENTS/HANDOFF/Director与公共世界书实现后，选择补齐日常规划背景输入。上一轮编译完成不代表用户已验收Director；当前用户只要求继续推进，没有提供本版测试结果。
- 实现前核对[SillyTavern官方World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)、1.19.0/package/AGPL-3.0与Generative Agents当日main plan.py/Apache-2.0。复用项目已有字面激活器、排序/容量、SQLite JSON1/SQLAlchemy和受控模型网关；不复制酒馆源码、不装框架/依赖/另一套RAG或调度器。详见[调查记录](docs/research/2026-09-29-director-background-reuse.md)。
- 自动审批最初两次拒绝新背景外发路径，要求具体数据授权；用户随后明确回复“授权，按上述范围继续（推荐）”，同意本世界已确认、逐条公共的世界书title/content发给其配置模型服务用于已开启Director，隐藏条目/私聊/私人记忆不发送。之后接入获准。另一次审批拒绝将授权追加AGENTS治理指令；采用安全替代，AGENTS.md未改，仅在普通功能/交接文档记录事实，没有绕过拒绝。
- 新director_background reader在SQL先限定World/current accepted/lorebook/逐条Exposure/enabled，再投影title/content、关键词/排序/激活元数据和同书scan_depth；不材料化整本snapshot/source_book/原始来源副本/creator notes/未知extensions。单书展开再索引查公开条目，避免每个Exposure重展开同书；保留未知selectiveLogic的存在标记，不读原始source_entry。只读模型不是可编辑CanonicalContent。
- 把聊天已有激活/排序/最多16条、title/content共12KiB抽到select_common_background共享函数；聊天normal默认和排序保持。后台规划quiet，明确triggers时须允许quiet；planner只扫描一段角色名称＋各自当前地点名称，scanDepth零不触发关键词，其他已支持/未支持条件沿用现有实现。扫描仍有16,384字符硬限，不扫描私聊、persona文本、隐藏正文、递归或向量。最多512条公开启用条目、每条关键词/条件投影16KiB，超量明确停attention且不claim/dispatch模型；单项超12KiB背景按已有预算跳过，必要角色/地点不被省略，完整输入仍64KiB。
- claim持久输入增加lower-trust common_world_background及来源IDs；在开始模型任务前和接纳返回计划前复核选入来源仍公开/当前，变化则停attention，返回计划不接纳，不自动重放。已admitted请求可能计费；已提交事实保留，已接纳旧批不会因后来背景编辑重写。新公开资料等下次常规批次，不额外触发付费replan。无新表/迁移；旧无背景输入的计划兼容。
- 普通界面保留原世界书公开入口、默认隐藏。条目详情与预览新增planning_activation_summary，说明能否参与日常规划，避免normal-only来源误导；API字段可选additive，聊天说明保留。自动活动初次开启提示当前模型服务接收角色资料/公共背景，新增背景容量/格式/版本变化安全错误反馈。没有未来候选或他人私有状态面板。
- **范围：** 本轮只让现有rest/work/leisure及已有地点选择参考公开设定；不创建背景地点，不把素材变WorldTruth/Knowledge，不增加新活动成果、主动联系、Episode、关系或完整离线重建。现有6小时/至少2且50%失效、默认off、费用治理、Kernel/Observation规则不变。
- Ruff lint/format（6份Python）、ESLint/TypeScript与diff检查通过。Core冻结27.00秒；Vite205模块、Rust release22.89秒成功。保留已有tzdata/pysqlite2/MySQLdb可选hidden-import警告，desktop未新增warning；Git文档LF/CRLF提示是已有换行配置，没有改配置。本轮没有新增/修改/运行测试、CI、GUI smoke、迁移、应用启停、真实API、凭据探测或用户DB/配置/密钥操作；源码/编译/哈希不是运行或隔离验收。
- 新包：D:\LivingWorld\artifacts\portable\director-background\dreamtalk\dreamtalk-desktop.exe；desktop 12,423,168 bytes / SHA256 `CC2824EE63FD336C8D4AB916C5341F0EFCB5B150F2B6F3954A49C71A8F9D4AFD`。ZIP 42,724,881 bytes / SHA256 `62B277689CF5BA2843105F602ABDCA6B4F60F7001804207CA6B4BAF1C8FF22FD`；Core SHA256 `DA2C27C7D69BEA7CB7CFF54143D4FB6E92069C4E14211446CC24F5574ABCFE4D`；helper `264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。6份源码、desktop/Core/helper和13份许可核对一致。清单artifacts/director-background-package.json；日志director-background-core-build.log/director-background-desktop-build.log。随包DIRECTOR、EVENTS及原MEMORY/RECALL/STREAMING说明；旧包未覆盖，未发布或push。
- 当前说明已补充DIRECTOR_MODEL/PRODUCT_SURFACE/PRODUCT_SPEC/DIRECTOR_ACTIVITIES；上轮“公共背景未接入”是历史范围，当前以代码和本条为准。DIRECTOR_MODEL底部旧状态明确标为当时亲历事件切片，不能误读为当前Director仍未实现。
- **接下来：** 优先用户真实反馈；下一块建议增加普通地点配置入口及更有辨识度的活动，先核对冻结地点/动作契约和成熟实现，再做清晰切片。离线计划重建仍待补齐；主动联系需先给出统一目的/episode/同理由一次的具体方案，不能隐式放开。建议用简短常驻公共背景体验本版，不声称素材一定出现在活动里；实际质量与授权隔离仍由用户验收。

## 前序切片：2026-09-29 已授权 Director 批量规划与基础日常

- 从干净 `bd50a3c` / `codex/chat-feedback` 接续，实际仓库 `D:\LivingWorld`。用户报告上一轮测试无问题（未列分项）；本轮先调查成熟实现、形成[具体方案](docs/proposals/2026-09-29-director-runtime.md)，用户明确批准“一次开启后自动运行（推荐）”。授权记录覆盖每世界默认关闭、首次后台模型用量、6小时 WorldTime、至少2条且达原批50%失效才提前续批、typed角色日常/move、Kernel权限与不移动Player；没有再索取重复许可。
- 调查 Generative Agents main/Apache-2.0、LangGraph main pyproject1.2.12/MIT、沿用前轮Concordia职责分工。复用现有受控多供应商网关、预算/账本、SQLAlchemy/SQLite/Alembic/Pydantic和单World scheduler/Kernel/Observation；没有安装第二个agent runtime、复制第三方源码或为每个角色建轮询任务。[复用记录](docs/research/2026-09-29-director-plan-reuse.md)。
- 设置新增“世界自动活动”：每世界默认关闭，当前绑定身份首次启用明确授权后台模型用量；同身份关闭/重开保留授权，换绑定不能沿用另一身份授权。safe status只返回enabled/revision/state/error/current-model，不展示未来候选、隐藏地点/私人资料。GET刷新只读；保存CAS，前端请求序号防止旧刷新覆盖刚保存状态，错误保留。失败/空计划/中断不自动重放；显式新规划是新有费用任务。
- 新additive `0025_director_runtime`（settings/plans/candidates），完整旧0024及更早schema形状识别；UUID/Timestamp用String(32)与ORM一致。BEGIN IMMEDIATE一向claim先落库；新计划接受与旧pending取消同事务，当前consent/generation/plan/binding检查拒绝迟到结果重新启用。重启遗留planning标interrupted＋attention，ready候选与已有receipt恢复不重派模型。22个修改/新增Python文件被最终包逐个SHA核对。
- 输入先同World＋已放置角色及必要位置/revision；已接受角色卡通过root replacement链解析，SQL仅白名单抽取description/personality/background，不加载整个snapshot/内嵌世界书/notes/extensions。没有读取角色私聊/记忆/信念或世界书暗线，公共背景尚未作为planner输入。完整覆盖最多16角色/32地点/64候选/64KiB输入，超容量明确停止而非截断。Pydantic严格结构、已有IDs、非重叠、窗口/可用时间/覆盖每角色校验；模型自由文本不成为action。
- 采用当前模型 `director_plan` purpose，输出为8192与模型更低cap；复用已有通用有界操作helper `generate_bounded_text`，保留authoring旧名兼容。单批有限预算独立于聊天额度，可信Token/金额预留、物理retry/fallback/ambiguity与原账本规则不变。没有针对DeepSeek单独实现Director或实际调用提供商。
- 日常新增 `character_routine` v1与固定rest/work/leisure enum，正式注册Kernel。DIRECTOR只能提案匹配accepted candidate的Character动作；writer事务校验授权/世界/身份/时段/revision/占用/地点，不冒充CHARACTER_RUNTIME、不移动Player、不写关系/知识/最终台词。CharacterState CAS、可选旧Scene离开、CharacterRoutineStarted v1、真实观众Observation、candidate active、稳定Action receipt同事务。新event replay handler重建位置/revision，原Observation重建策略保留。本轮有真实开始事件，没有任务成果/完成事件。
- 复用既有每World一个orchestration task，合并queue和Director下一due/占用结束/window_end deadline；最多两个有限模型I/O task。普通候选消费不调用模型，到窗口末或至少2/50%原批invalid才续批；候选提前完成不续批。PAUSED不消费/开启新批；关闭阻止新工作，已admitted模型可能计费。新批保留已开始活动占用直到end，操作性结束不是canonical工作完成。关闭后迟到结果不启用。
- 开始事件接现有owner＋witnessed/event_occurrence白名单投影；仅注册activity枚举与角色/地点ID，未材料化整个事件body。玩家只见自己亲历；单/群聊角色只读自己的亲历。台词提示开始记录不等于仍在活动/已有成果。已有“聊聊这件事”继续由用户发送，没有主动发消息。正常普通存档只有“家”，先体验原地活动；已有多个地点时支持角色移动，不虚构新地点。
- **当前交付边界：** 批量规划＋基础日常开始/位置变化；没有主动联系、Episode、相遇剧情、关系推进、世界书公共背景规划输入、新地点编辑、完整离线活动重建。重开只执行还在有效时段的候选，按当前WorldTime开始；已经错过end的pending expire，不伪造过去观察/成果。窗口外不追补多天计划。这不是完整自主世界交付。
- 源码复核修复初次off及换身份的费用授权绕过、关闭中claim/dispatch竞态、设置刷新覆盖反馈，并收窄角色资料SQL投影。打包后最终启动流程核对发现Director可能早于Host密钥同步；现已等待sync_complete，再由HostControl线程经call_soon_threadsafe唤醒既有World任务，新规划claim/dispatch不早于同步。本轮未探测真实凭据。原中间包director-activities未作为最终交付，最终使用director-activities-final。Ruff lint/format、ESLint/TypeScript、diff检查通过；首版Core冻结22.70秒，凭据同步时序修复后最终Core20.93秒，Vite205模块/Rust release20.76秒成功。保留已有tzdata/pysqlite2/MySQLdb可选hidden-import提示，npm升级notice未处理；未新增desktop编译warning。
- 独立启动入口 `D:\LivingWorld\artifacts\portable\director-activities-final\dreamtalk\dreamtalk-desktop.exe`，desktop12,422,144 bytes / SHA256 `AECF29D89D33B64EE4897B263493BAA36FFFF8B7AECF2E46085E550AB5FD7E17`；ZIP42,696,380 bytes / SHA256 `77771633B45A9E6BD7F8AC106DE2137ABF7430514F9BF510853A23B77FE18B13`。Core SHA256 `CA987F8C9ADCC45329F27ABFCE83FA24C94E3FF6CA73669C040CEE8098AD4D45`；helper保持 `264DF8990752ABB179A3773ACE934F546C69AF99F4C9834EA1286D0D9886FDEA`。22份源码、desktop/Core/helper及13份许可一致；清单 `artifacts/director-package.json`，最终日志director-final-core-build/director-desktop-build.log，随包DIRECTOR及前序回忆/摘要/流式说明。旧包未覆盖。
- 按AGENTS§20未新增/修改/运行测试、CI、GUI smoke、应用启停、provider调用、凭据探测或用户DB/配置/密钥操作；没有运行迁移、历史replay、离线恢复验收。编译/哈希不证明真实模型规划、迁移、事件隔离和生命周期已通过。既有旧mock/schema测试未维护；本地提交，无push/release。
- **交接冲突已明确更新：** DIRECTOR_MODEL旧“全部未实现/阈值无默认/WorldPlan确认未定”、ACTION_RESOLUTION旧“只有move_player/禁止Director角色动作”是旧切片描述，当前以已批准方案和正式Kernel代码为准。更新AGENTS§24、PRODUCT_SPEC P-05/P-16及架构/事件/调度/UI文档；P-17仅本切片已定，P-03/P-04的Outreach仍未定。
- **接下来：** 先由用户打开本版并验收设置开启→规划→亲历事件→角色近况；优先处理真实反馈，再补公共背景/地点与活动丰富度及离线计划衔接，按具体联系目的/episode去重方案接自然主动联系。本轮无需重新确认已批准选择，未来新功能仍先调查成熟实现。

## 前序切片：2026-09-29 已获知事件与角色对话连接

- 从干净 `edc6736` / `codex/chat-feedback` 接续，实际仓库 `D:\LivingWorld`。用户授权继续项目；本轮补齐事件详情和角色自己的事件输入，复用已有“世界事件 → 聊聊这件事”，没有再造入口。
- 调查 Concordia 当日 main README/Apache-2.0 与 SillyTavern 官方 World Info/release AGPL-3.0。采用角色观察与世界执行分工，复用既有 SQLAlchemy/SQLite/Observation/受控聊天网关；不引入另一套 simulation loop、memory/embedding、provider runtime 或复制酒馆源码。[调查与范围](docs/research/2026-09-29-observed-events-reuse.md)。
- 玩家时间线最多100条，SQL先限定 World＋当前绑定Player的 event-target Observation，保留最早获知时间；详情额外要求同owner witnessed＋event_occurrence。仅投影 PlayerMoved/PlayerPlaced/CharacterPlaced v1 的主体/地点白名单 ID，不材料化整个 payload；辅助字段也由同一授权/版本谓词限制。仅有旧普通观察、未知类型/版本、格式错误或缺失引用的事件只保留通用标题，不展示私人信念、关系数值、activity/availability/revision/activation。
- 中文模板和同世界引用名称用于展示，当前名字限160字符并清理控制字符，不是历史名称快照。PlayerPlaced/CharacterPlaced 初始放置仍不自动创建 Observation；没有记录的存档可能继续空时间线，普通 UI 尚无移动操作。本轮没有回填授权或伪造活动。
- 单聊与群聊回复分别从已验证发言Character绑定reader读取自己的亲历事件，最多12条/8KiB序列化数据，作为lower-trust USER内容；先World＋Character＋channel/basis过滤，再白名单/排序/有限读取。group selector不读这些私有事件，不从玩家列表或其他成员复制；读于当前prompt组装，不声称历史消息时点快照。
- 现有“聊聊这件事”草稿优先引用详情，仍由玩家核对发送。事件观察不自动写KnowledgeAssertion、EpisodicMemory或WorldTruth，也不表示已告知玩家。没有额外模型调用/迁移/事件或Activation消费；新增输入仍受原回复硬Token/金额治理。API详情/亲历标记为additive nullable字段，旧标题兼容。
- 初次Ruff因只读缓存路径失败，改用--no-cache；随后修正导入/长行/格式。最终Ruff lint/format、ESLint/TypeScript和diff检查通过。源码复核修正缺失origin及辅助字段授权边界，最终Core编译24.15秒，Vite204模块/Rust release25.80秒成功。保留既有tzdata/pysqlite2/MySQLdb可选hidden-import提示，无新desktop警告。
- 独立包 `D:\LivingWorld\artifacts\portable\observed-events\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\observed-events\dreamtalk.zip`，42,658,639 bytes / SHA256 `5B09E1A57EBAD1DF5FC4E1C595ACEE8BAB72DD56F19113AD6F8208BFB4C65A0D`。9个修改/新增Python源与包内哈希一致；最终Core exe、desktop/helper及13份许可核对一致。日志 `artifacts/observed-events-final-core-build.log` / `artifacts/observed-events-desktop-build.log`，清单 `artifacts/observed-events-package.json`；随包README/EVENTS和前序MEMORY/RECALL/STREAMING，旧体验包未覆盖。
- 按AGENTS§20，没有新增/修改/执行测试、CI、GUI smoke、真实API/凭据探测、应用启停或用户DB/配置/密钥操作。没有运行迁移/历史replay；编译和哈希不是运行/隔离验收。旧流式测试mock未适配的问题仍保留。本地提交，无push/release。
- 用户入口：[本版说明](docs/OBSERVED_EVENTS.md)。关闭旧窗口打开新版 → 世界事件 → 已有亲历详情/话题草稿 → 用户发送；分别核对玩家/角色访问范围、换世界/身份和未亲历角色。无记录时空列表是预期，不能以此声称Director失效或完整世界活动已完成。
- **交接与代码核对：** 上方新能力确实已接入bootstrap/direct/group/player API。旧EVENT_MODEL“事件/队列未实现”、PRODUCT_SURFACE“仅标题”、SCENES旧阶段“聊天未实现”等是历史切片状态，当前已有ActionResolution、scheduler和聊天；本轮补充当前说明。DIRECTOR_MODEL的计划/候选/主动联系仍未实现，与代码一致。可确认会话摘要已完成不代表P-16运行世界计划确认规则已确定。
- **接下来：** 先形成可审阅Director计划契约，明确P-05/P-16/P-17的窗口耗尽、失效重规划、批量计划确认与候选消费；再接Kernel支持的角色活动、相遇和Outreach。不得隐式选择默认窗口、阈值或固定时钟调用模型。当前阶段是可体验聊天/创作＋回忆/摘要＋事件输入连接，完整自主世界尚未完成。

## 前序切片：2026-09-29 可确认会话记忆摘要

- 从干净 `848e628` / `codex/chat-feedback` 接续。用户接受建议继续推进，并在中断后要求从现场继续；中断前静态检查与 Core/desktop 编译已完成，中断后只核对、打包、文档与本地提交，没有重跑编译或进入其他功能。
- 调查 SillyTavern 官方 Summarize（release/AGPL-3.0）和 LangMem 当日 main/pyproject 0.0.30/MIT。采用上一确认摘要＋后续原文的增量模式，复用已有 governed gateway、可信计数/预算/账本、SQLite/SQLAlchemy/Alembic 与 React/native dialog，不安装第二套 agent runtime 或复制酒馆源码。[调查与选择](docs/research/2026-09-29-conversation-summary-reuse.md)。
- 单聊/群聊顶部新增“记忆摘要”：用户点击生成，核对/编辑，预览摘要和本批原文，确认保存；只有确认版本进入本会话后续角色回复。长历史从最早未处理原文按批继续，最多32条/96KiB正文；整条保留不跳过，摘要≤8KiB。生成复用现有模型，无联网搜索，独立任务有限额度，不继承聊天每轮 Token 额度；所有物理 retry/fallback 仍受原治理。没有自动生成/遗忘。
- 手动修正不调用模型，确认形成新版本；旧内容、原文 ID、基础版本与覆盖位置保留。每版只有本批最多32条新增来源，基础链可逐版追溯。源模型发言人标签来自当前运行角色/Player名称（≤160字符），不是历史名称快照，稳定身份仍是原 Message/Turn/Conversation/sender ID。来源表示输入依据，不保证摘要每句话正确。
- 新 authenticated memory snapshot/draft/preview/commit/revision/source routes 复用本地 session；所有操作先验证 World＋当前绑定Player＋Conversation；角色 prompt 另校验固定成员，且只读覆盖位置早于当前玩家消息的确认版本。只在该会话作用：单聊该角色，群聊固定成员；selector不变，不跨会话传播、不读别人的私有记忆。
- 新 additive `0024_conversation_memory`：两张交互表与owner索引；历史 schema校验显式识别新旧revision。BEGIN IMMEDIATE CAS；UUIDclaim先落库，一次dispatch；hash绑定内容/基础版/来源/世界/身份/会话。同一hash确认幂等返回原版本，旧基础草稿不能覆盖较新确认版。它是Conversation summary，不是旧Observation-only EpisodicMemory的扩展；没有WorldTruth/Knowledge/ledger写入。
- 关闭/断线后读取最新状态不会重放模型；生成中关闭只取消前端等待，服务端可能继续，不能承诺取消费用。UI恢复最新草稿，已确认版本可逐个查看；不提供旧草稿历史浏览。已预览的编辑可重开，未预览的本地修改关闭后不保留；读取最新状态保留同一草稿尚未预览的修改。预览源码核对来源后才开放确认，修改使预览失效；繁忙期禁用变更，错误与成功均有明确提示。
- 补充CHAT_MODEL/PRODUCT_SURFACE/EPISODIC_MEMORY/PRODUCT_SPEC当前状态。前序文档“自动摘要/修正未完成”是当时切片范围；现在已实现手动确认的独立会话摘要，仍未实现自动私有记忆、跨会话摘要传播、遗忘和Director世界活动。
- 初次静态检查发现长行/格式、Header默认表达式，已修正；源码审查也修正前端错误码字段，补齐模型发言人名称和草稿owner索引。最终Ruff lint/format与ESLint/TypeScript通过，diff检查通过。Core PyInstaller成功（约25秒），Vite204模块、Rust release22.88秒成功。12个修改Python源与包内哈希一致；helper、desktop及13份许可文件字节一致。保留既有tzdata/pysqlite2/MySQLdb可选hidden-import warnings，无新desktop警告。
- 独立新版 `D:\LivingWorld\artifacts\portable\conversation-summary\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\conversation-summary\dreamtalk.zip`，42,642,878 bytes / SHA256 `DE6B408978934487304F78EA419F3CD5D04530A82B3A8519F70B6882C935D2BA`。日志 `artifacts/conversation-summary-core-build.log` / `artifacts/conversation-summary-desktop-build.log`，清单 `artifacts/conversation-summary-package.json`；随包README/MEMORY以及前序RECALL/STREAMING。旧包未覆盖。
- 按AGENTS§20未新增/修改/执行测试、CI、GUI smoke、provider/credential probes或应用启停。没有真实用户DB/配置/密钥写入，没有运行迁移、旧消息replay、终止用户进程或push/release。现有流式mock未适配问题保留；不能声称测试套件通过。构建/哈希只证明编译与包一致，真实摘要、迁移、断线恢复、并发保存、权限隔离仍待用户验收。
- 用户入口：关闭旧窗口，打开上述exe；首次启动按既有流程自动增量迁移，旧版不认识新schema，不要再用旧程序打开升级后的存档。顶部“记忆摘要”→生成→编辑→预览来源→确认，再聊以核对记忆；手动修正/版本浏览与长历史分批继续可体验。详情随包MEMORY.md。
- 接下来先根据用户实际反馈修正本切片；后续优先调查并推进Director计划消费与可获知世界活动，把角色话题与持续世界连接起来。主动联系episode、隐私和费用语义仍需在各自确定切片中处理，不能用后台随机LLM循环替代。没有需要本轮重新确认的选择；整个持久世界产品尚未完成。

## 前序切片：2026-09-29 聊天回忆检索与原文查看

- 从干净 `3203dac` 接续，正式仓库仍为 `D:\LivingWorld` / `codex/chat-feedback`。用户授权继续推进。本轮交付可查看的共同聊天回忆；独立长期记忆/自动摘要仍未完成，前序流式切片仍待用户运行验收。
- 先核对 AGENTS/HANDOFF、实际记忆/知识/对话实现，调查 Mem0 v2.2.1、Letta memory blocks、SQLite FTS5、jieba、原生 dialog。选择复用既有 SQLite 3.50.4 + 固定 jieba 0.42.1 + 授权分页 + WebView dialog，不新增依赖/模型调用/agent runtime，不复制框架或酒馆源码。[选型与详细契约](docs/research/2026-09-29-chat-recall-view-reuse.md)。
- 单聊/群聊顶部新增“聊天回忆”。在当前会话中搜索关键词，显示原文发言人、时间、位置；“查看前后文”复用既有消息分页最多七条并标明命中；“引用这段，继续聊”只追加可编辑草稿，保留已有输入，UTF-8 超 64 KiB 拒绝。没有模型也能检索/阅读；模型不可用、生成中或待保存时不引用；用户自行确认发送才进入原聊天链路。
- 新 authenticated POST messages/search，256 字符非空 query、可选 strict signed64 before cursor。沿用 World + 绑定 Player + Conversation 的 owner 查询，在读正文/排序前授权；不读别的会话/角色私有记忆或开发者 trace。返回每条原 Message/Turn/sender/source 及扫描/跳过计数和 older cursor；请求词不进入 URL，CLI access logs 原保持关闭。旧 routes/协议并存，没有 schema/migration 或写入。
- 每批最多读 100 条、处理 512 KiB、单条 >8 KiB 跳过，返回最多八条/正文合计32 KiB。授权 DB page 仍会最多材料化 101 × 64 KiB，处理预算不是整个读取硬内存上限。字面 OR 分词/BM25/24不同词/两worker复用既有 ranker；UI 可继续向前分批，最多保留64条结果，明确上限。预算中止从最后消费位置续查，不跳过剩余历史；不是全库全局排名/语义检索/所有命中保证。
- 原生 dialog 提供关闭/Escape；关闭或会话卸载 abort 读请求，不接收过期结果。引用后聚焦输入框；只关闭回忆不会停止已有流式回复。没有新增 prompt 临时字段，原自动 prompt recall 的三页/四条/8KiB、Character owner、group seen、Token/financial/claim 约束保持。
- 实际代码与旧架构文档存在历史状态差异：EPISODIC_MEMORY 的“Developer UI/Agent consumption 延后”是 C007A 当时范围，当前 DeveloperInspectorService 已有 owner memory 查看/记录、角色上下文也已读取自己的记忆。本轮补充现状说明，未扩大普通玩家的私有记忆可见性。Conversation/Message 仍没有变成 Memory evidence/WorldTruth/Knowledge，自动摘要/合并/遗忘/修正规则未定义。
- 初次 Ruff 指出一处长行/格式，已格式化后重新通过；Ruff lint/format、ESLint/TypeScript、源码审阅与 diff 检查通过。Core PyInstaller 构建成功；Vite 203 模块、Rust release（24.83秒）成功。四个修改 Python 源与包内 SHA256 一致；helper/desktop、项目/jieba 和既有第三方许可字节核对通过。保留既有 tzdata/pysqlite2/MySQLdb optional hidden-import warnings，无新 desktop warning。
- 独立包 `D:\LivingWorld\artifacts\portable\chat-recall-view\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\chat-recall-view\dreamtalk.zip`，42,607,569 bytes，SHA256 `B66D16CF072EC0FF0A31C8534E575C091C3488848DD65D8A8BFED619BBA91AAA`。日志 `artifacts/chat-recall-view-core-build.log` / `artifacts/chat-recall-view-desktop-build.log`；核对清单 `artifacts/chat-recall-view-package.json`，随包 README、RECALL 与前序 STREAMING。旧包未覆盖，未终止用户进程。
- 按 AGENTS section 20，本轮没有新增/修改/执行测试、CI、GUI smoke、live-provider/credential probes、应用启停、用户 DB/配置/密钥操作或旧消息 replay。旧流式 mock 未适配的测试问题仍保留，不能声称测试套件通过。编译/哈希不证明运行体验或隔离验收；没有 push/release。
- 用户验收入口：关闭旧窗口，打开上述新 exe → 单聊/群聊顶部“聊天回忆” → 搜索已聊过的关键词 → 查看前后文/追加草稿 → 手动发送；长历史继续检索更早页，换会话/世界确认范围，关闭/Escape/引用聚焦待实际验收。前序流式功能仍在，需模型设置勾选保存启用。
- 下一步优先确定带 Conversation/Message 原文来源的记忆摘要写入、确认和纠正规则，再评估成熟框架接入；随后推进 Director 计划消费/主动世界活动。当前阶段仍是基础聊天/内容创作可体验、记忆能力逐步补齐，不是完整 LivingWorld 已完成。

## 前序切片：2026-09-29 单聊与群聊流式回复

- 从干净 `4303e68` 接续，正式仓库 `D:\LivingWorld` / `codex/chat-feedback`。用户授权继续推进；前序用户已确认内容 API 生成、单聊、群聊 @ / 无 @ 回复。本轮完成流式交付切片，不将编译当作 API 或整个产品验收。
- 复用既有 governed stream、Starlette 1.6.0 与 MIT eventsource-parser 4.1.1（exact pin/lock/原始许可），没有重新实现 provider 流协议、引入 agent 框架或复制酒馆 AGPL 源码。[来源/许可/契约记录](docs/research/2026-09-29-chat-streaming-reuse.md)。
- direct/group 服务沿用单次 claim、权限过滤、hard input/output turn ceiling、financial accounting 与消息提交。角色回复可走既有 stream，selector 保持内部 nonstream；仅显示正文 TextDelta，不泄露选人输出/推理/原始错误。终态结算与校验后才提交，临时文字不写记录/知识/记忆。后续失败保留此前群聊发言。
- 新 authenticated POST direct/group reply/stream 路由与旧 JSON 路由并存。owner 查询在 headers 前；claimed 409，completed 仅交付 durable 消息。8 帧队列、10 秒 heartbeat、固定安全错误；断开时显式关闭迭代器与 shielded producer 清理。仅在 dispatch 前能力规划不支持时采用原 complete delivery，失败后不会转 nonstream 重跑。
- 前端共用 SSE parser/hook，临时气泡、当前发言者、选人阶段、停止生成、near-bottom 自动跟随与 durable-ID 消息合并接通。手动刷新不重复当前气泡，初始历史读取竞态保留新提交。关闭会话会取消请求；保存消息期间关闭视图不会晚启动模型。取消不保证退款或 completed，历史 claimed 不重置；单次 GET/手动状态核对不重新调用模型。
- 模型设置新增“逐步显示回复”开关，复用原保存/restart/rollback/凭据流程。首次设置默认选中；旧配置保持原 false，需用户勾选保存启用，API 密钥可留空沿用。所有既有 native adapter 使用一致 capability/profile；兼容 Chat Completions 开启 include_usage，未知服务不保证支持，可关闭。未改任何真实用户配置/密钥/存档。
- actual payload 的 DeepSeek 官方 framing 与原生 OpenAI count projection 扩至 streaming；不再因 stream flag 退回全模型输入预留。OpenAI exact endpoint/structured/continuation 排除、计数缓存/失败 fallback 不变，DeepSeek helper 不变；Claude/Gemini/代理原可信模型容量路径不变。整轮额度没有自动提高。
- Ruff lint/format、ESLint/TypeScript、source/diff 检查通过；Core PyInstaller 编译成功，Vite 202 模块和 Rust desktop release（20.67 秒）成功。5 个修改 Python 源与包内 SHA256 一致；helper 和 parser 原始许可也一致。初次许可哈希差异仅因换行转换，已按上游 bytes 复制后通过。保留既有可选 tzdata/pysqlite2/MySQLdb hidden-import warnings；desktop 无新 warning。
- 新包 `D:\LivingWorld\artifacts\portable\chat-streaming\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\chat-streaming\dreamtalk.zip`，42,600,226 bytes / SHA256 `F6F33E96069174C7DE49ECFC75541D936743976B4B708D1CAF33B9678F10F721`。日志 `artifacts/chat-streaming-core-build.log` / `artifacts/chat-streaming-desktop-build.log`，清单 `artifacts/chat-streaming-package.json`，随包 `STREAMING.md` 与第三方 notices。旧包未覆盖，用户进程未终止。
- 源码核对发现既有 ChatTranscript/GroupChat 测试 mock 仍期待 generateDirectReply/generateGroupReply，尚未适配新 streaming POST 客户端；按当前约定未修改或运行，不能声称现有测试套件通过，后续需用户授权维护。
- 按 AGENTS section 20 未新增/修改/执行自动测试、CI、browser/desktop smoke、provider/credential probes 或应用启停。没有 schema/migration、旧消息 replay、用户 DB/配置/密钥写入。一次文档写入自动审批超时，授权范围内重试一次成功；没有遗留审批阻塞。无 push/release。
- 待用户验收：关闭旧窗口、打开新版，在设置勾选开关保存，发送新的单聊/无 @ 群聊/@ 群聊，检查逐步显示、正常保存、停止后已保存发言保留、重新打开历史。不同 native/provider/proxy 的真实 terminal usage、自然群聊 STOP 和桌面取消行为尚未验证；已有用户非流式反馈不证明它们。
- 项目仍处基础聊天/内容创作可体验阶段。本轮 streaming 已实现但运行验收待用户；长期独立记忆/语义检索、Director 计划消费/主动事件、完整 AI World Builder 未完成。下一切片先调查成熟记忆方案，再做可检查的角色记忆界面与权限来源链，避免把群聊可见记录直接升为世界事实。

## 前序切片：2026-09-29 群聊验收与 OpenAI 请求预检

- 从干净 `2e3ba85` 接续，正式仓库 `D:\LivingWorld` / `codex/chat-feedback`；用户确认无 @ 群聊现在有人回复。连同前序角色卡/世界书 API 生成、单聊、群聊 @，核心交流流程已有用户实际反馈；不据此声称自然结束、多提供商、长期记忆或整个产品最终验收已完成。
- 复用 OpenAI 官方完整输入计数接口，增加可选 async prepare，再供既有 sync bound/Token 和 financial guard 读取同一结果。接线覆盖私聊、群聊首次/后续选人与角色回复、内容生成、governed 每次物理 retry/fallback。首个准备在 claim 前；物理准备在预留/accounting START 前，并再次检查原 deadline。DB transaction 内不联网；真实 model dispatch/未知 usage/不重放规则保留。
- 仅原生 Responses adapter 的 exact official endpoint/default base、无 structured/streaming/continuation 的文本请求支持。复用 actual payload 的 model/input/truncation；五秒、4 MiB/4 KiB、30秒最多64条 digest/数值缓存，失败也短暂缓存。失败/不支持继续完整模型可信预留，不借用估算。简化 OpenAI UI 提示与实际准入同步。DeepSeek framing、Claude/Gemini/代理原有保守路径不改。
- 已调查 OpenAI SDK/接口、Claude estimate、Gemini countTokens/Interactions；无新依赖、无模板独立重写或许可变化。具体来源/版本/许可/适用条件见 [复用记录](docs/research/2026-09-29-provider-input-preflight.md)。Claude 的估计不能直接当 HARD；Gemini 仍需证明 complete Interactions mapping，不为此扩大本轮切片。
- Ruff lint/format、ESLint/TypeScript 和 diff 检查通过；Core PyInstaller 编译成功，Vite 197 模块及 Rust release（24.85秒）成功。七个修改 Python 源与包内源码 SHA256 一致，DeepSeek helper 与既有 release 一致。保留 `tzdata`、`pysqlite2`、`MySQLdb` 可选 hidden-import 警告；构建不能代替运行验收。
- 独立新版 `D:\LivingWorld\artifacts\portable\provider-preflight\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\provider-preflight\dreamtalk.zip`，42,578,201 bytes / SHA256 `D6CF145CD171EACFC168BB7FB9ECA60C8258B38F0829D0307A4C6FB20436E68E`。日志 `artifacts/provider-preflight-core-build.log`、`artifacts/provider-preflight-desktop-build.log`，核对清单 `artifacts/provider-preflight-package.json`。旧包不覆盖，不终止用户进程。
- 本轮没有 schema/migration、用户 DB/配置/密钥变动、旧消息 replay、测试/CI 变动、自动测试/smoke/付费调用或应用启停。真实 OpenAI 行为待用户使用自己的 API 验收；现有 provider/key 可继续使用，无需为了本轮切换服务；没有 push/release。
- 项目阶段：可体验的基础沉浸聊天/内容创作已打通；完整长期独立记忆、普通 Token streaming、Director 批量计划消费/主动事件、完整 AI World Builder 仍未完成。接下来优先流式聊天体验，之后推进记忆/世界活动的确定切片；未确认 memory evidence/隐藏授权语义不能伪造实现。

## 前序切片：2026-09-28 群聊自动选人修复

- 从干净 `a9ae5e8` 接续，正式目录 `D:\LivingWorld` / `codex/chat-feedback`。用户实际确认：API 生成角色卡/世界书、单人对话、群聊 @ 指定下一位均有效；无 @ 群聊没有回复，截图显示 generic validation failure。上述为用户验收反馈，不是助手自动测试；整个产品尚未完成最终验收。
- 源码发现自动选人的首轮/后续调用都固定 `max_output_tokens=64`，推理模型可在产生角色 ID 前耗尽；@ 跳过首次 selector，但后续 selector 仍失败，符合截图的 incomplete 提示。首轮与后续原有两份 UUID 解析也都拒绝完整 JSON/引号/code-block 包装。未捕获用户原始模型响应，因此不把截断/包装作为已直接观察的唯一根因。只读 mode=ro 数据读取失败，immutable view 没有近期 character_dialogue facts；该磁盘视图可能陈旧，不能据此断言未调用 API。未读密钥或写用户 DB。
- selector 统一 request/result 路径；允许最多 8,192 输出，再受配置的模型/应用 output cap 和原 preflight 剩余额度约束。不是固定消耗，没有自动提高 200,000 整轮额度。每次 selector/角色/retry/fallback 仍共享原 hard budget、trusted input bound、账本和单次 claim。无任何提供商专用分支、没有模型重试或旧消息重放。
- 完整结果仅接受 UUID/后续 STOP、JSON scalar、恰好一个 character_id 字段、或完整单段 text/json/plain fence；拒绝多个/重复/额外键、非字符串、解释性文本、截断、群外 ID 或 >1,024-byte 决策文本。首轮必须选群内角色，不能 STOP；后续可自然 STOP。仍使用当前 claim 的固定成员集，选择输入只含公开已确认 persona/shared transcript；角色生成的私有知识边界未变。
- 群聊 HTTP 将 selector invalid / output_limit 作为固定安全 502 标签返回，其他校验错误继续 generic；UI 区分自动选人与角色台词校验，不泄露模型输出。参考 Microsoft AutoGen SelectorGroupChat 的公开候选、单角色校验和独立选择/回复做法；复用现有 stdlib JSON/UUID、governed gateway、claim/context，没有复制 MIT 源码、安装另一个 agent runtime 或增加依赖。调查/版本/许可证与选择见 [记录](docs/research/2026-09-28-group-selector-fix.md)。
- Ruff lint/format、ESLint/TypeScript、源码 diff 检查通过；Core PyInstaller、Vite 197 模块和 Rust desktop release 成功。包内三个修改 Python 源文件与源 SHA256 一致，原 DeepSeek helper 二进制也一致。按 AGENTS 未新增/修改/执行测试、smoke、GUI 验收或提供商调用，现有测试保留；没有修改用户配置/存档、schema/migration 或终止其进程。
- 独立新版 `D:\LivingWorld\artifacts\portable\group-selector-fix\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\group-selector-fix\dreamtalk.zip`，42,572,567 bytes / SHA256 `EDEAB6AD5827E319464214DD0EBDFABA1ABCF30F48CF2FA8985CA59169D5D74A`。日志 `artifacts/group-selector-fix-core-build.log` / `artifacts/group-selector-fix-desktop-build.log`。旧 default/model-autoconfig 等包未覆盖；保留随包第三方 notices。没有 push/release。
- 接续：用户关闭旧窗口后打开上述 exe，发送一条新的无 @ 群聊消息，核对至少一个角色回应及自然结束，再核对 @ 后后续调度。无需重建角色卡、世界书或重新填写密钥，历史 claimed 回合不自动重跑。若仍失败，新的错误能区分 selector 截断/无有效群内 ID；先看该阶段事实，不默认再改聊天额度。
- 后续工程仍为其他提供商可信请求预检/复用成熟能力；本轮窄范围只修群聊，不扩展其他架构或自动测试。没有需要用户重新决策的产品问题，真实 API 行为待用户验收。

## 前序切片：2026-09-28 自动模型容量与请求预留

- 从 `36567bc` 接续，正式目录 `D:\LivingWorld` / `codex/chat-feedback`。用户同意把常见模型容量自动匹配、手动值移入高级设置、回复长度独立选择，并改善整份模型容量预留造成的聊天门槛。后续用户明确指出耗时过长、过度集中 DeepSeek；应收紧切片、优先成熟通用实现并如实说明每个提供商的完成范围，不能将自动识别容量等同于所有服务已支持按请求预留。
- 复用 models.dev/MIT 的 18 个模型与服务容量快照；React、桌面保存校验和 Core 读取同一 JSON。输入可信容量使用完整 context window，不能使用可能减去最大输出额度的 catalog input 字段。已匹配模型自动填容量；未知服务/模型需高级设置；相同模型 ID 的代理不继承直连预设。当前覆盖的是部分 OpenAI/Claude/Gemini/DeepSeek 型号，并非所有最新型号。
- 设置界面显示简短 2,048 / 标准 8,192 / 较长 16,384 / 自定义回复上限。新设置默认标准；旧自定义输入/输出保留，50,000 会显示为自定义，不自动改配置、额度或密钥。原数值限制扩为输入 10M / 输出 1M，已知模型保存时另校验真实 output cap。旧 managed 文档的识别不套新增 output 校验，因此旧过大值仍可进入编辑修正。配置序列化形状未改。
- DeepSeek 官方直接 endpoint 的四个已核对模型 ID 接入 MIT `deepseek-recipe` / `deepseek-recipe-encoding` Rust 0.1.0（Cargo checksum 固定；published source `b60af4cf40768602e6928772f01eba451483a442`）。官方完整 conversation framing 的 UTF-8 byte 长度是已审核文本 ByteLevel BPE 的保守上界，包含 role/BOS/thinking prefix；不声称精确 Token 数。重用官方 converter/renderer，没有独立写模板或字数比例估算。V4/V4.1 元数据核对来自官方仓库参考 `8cadfede7063c896b944e7bae05daa3549ae97ea`；官方 compare API 对发布提交返回 404，未据此声称两个提交完全相同。详见 [复用/上界依据](docs/research/2026-09-28-model-capacity-request-bounds.md)。
- 同一 `ProviderRequestUsageBounder` 注入 chat preflight、每个 routed physical attempt/retry/fallback 与 Budget Guard。当前只有已核对的 DeepSeek 直接文本调用使用逐请求上界；其他提供商、代理、structured/streaming/image、缺 helper、转换失败、超时等继续 full-model trusted fallback。额度硬约束、单次 claim、accounting START、未知 dispatch hold、禁止自动重放和知识过滤都保留。没有上下文自动压缩/截断、官方 count endpoint 或其他提供商逐请求计数适配；这是明确未完成项。
- Helper 只通过 stdin 获取无密钥请求 body，4 MiB / 5 秒边界；只输出数值或固定错误，Core 丢弃 stderr；最多缓存 64 个 SHA256 digest→数值，不缓存 prompt。打包脚本先编译 helper，PyInstaller 将其放入 `_internal/request-bound/`。随包附带 MIT notices、195 个锁定 Windows 依赖的版本/下载链接/registry checksum inventory 与 123 组许可证文本。许可证网络获取遇到超时/Windows revocation 离线，jsonschema exact revision license 成功取得，number_prefix 使用已获取官方 exact-revision MIT 原文；不把网络错误描述为项目功能错误。
- Ruff lint/format、ESLint/TypeScript、Git diff 静态检查通过；helper Rust release、Vite 197 模块/Rust desktop release 和 Core PyInstaller 构建成功。源与包内三个 Python 文件、JSON、helper 二进制 SHA256 一致。按照 AGENTS 未新增/修改/运行自动测试、smoke、GUI 验收、provider calls，未读取密钥、修改用户 DB、已保存配置或重放消息。既有 UI 测试仍描述旧必填字段/静默 disabled 行为，需用户后续授权维护；构建不能证明 API 回复验收通过。首次 spec lint 因非提升模式无法写 Ruff cache，改为只读 --no-cache 后通过。既有 PyInstaller optional imports 警告保留。
- 新包独立路径 `D:\LivingWorld\artifacts\portable\model-autoconfig\dreamtalk\dreamtalk-desktop.exe`；ZIP `D:\LivingWorld\artifacts\portable\model-autoconfig\dreamtalk.zip`，42,570,087 bytes / SHA256 `61A46CFBBEB9BB8128146F9CF33F10CF18C3C1567E7206C034433532F4BB8EBC`。helper 4,700,160 bytes。默认/旧版本目录均未覆盖；没有启动应用或终止用户进程，没有 push/release。编译日志 `artifacts/model-autoconfig-desktop-build.log` / `artifacts/model-autoconfig-core-build.log`。
- 用户下一步：关闭旧窗口并使用上述新目录，保留已有 API；建议回复长度选“标准”。已保存聊天额度不变；原 200,000 可在已核对 DeepSeek 短上下文下按新上界准入，但不是任意长上下文/群聊/fallback 全轮的完成保证。发送一条新消息验收，历史 pending 不自动重放。
- 工程下一步：优先统一提供商的输入预检能力，调查/复用 OpenAI、Anthropic、Google 的官方计数接口或成熟库，分别核对保证语义，再接入同一 admission/ledger，不按每个模型复制模板。未知服务继续可手动配置；上下文管理估算与 HARD 授权上界必须区分。用户这轮质疑应影响后续范围控制，不能继续无限扩大单提供商实现。

## 前序切片：2026-09-28 聊天未开始的额度准入修复

- 从干净 `7170c0e` 接续；正式目录 `D:\LivingWorld` / `codex/chat-feedback`。用户两条“你是谁”已保存，检查状态为 pending。前序截图输入上界 1,000,000、输出 50,000、聊天额度 200,000；当前聊天源码在 claim/provider 前预留整份模型输入上界，因此该组合必定拒绝。没有把短消息估算当作可信硬界限。
- 发现 UI 的确定冲突：聊天额度输入、应用与持久值恢复均硬限制 <=1,000,000，但模型输入可配置 1,000,000，无法留至少 1 Token 回复空间。解除该 UI 限制至 JavaScript safe integer，保留 Core 既有 int64 ceiling 和整轮 hard budget；未自动提高用户额度或调整模型参数。按上述设置，1,000,001 是首次调用的最小门槛；1,050,000 可预留一次完整 50,000 输出，不保证群聊/fallback 全轮完成。
- 复用已有 registry/bounder/HTTP/feedback：可用性查询返回 route-wide 输入预留及输出上界，私聊和群聊在发送前给出具体额度提示。真正授权仍由原 gateway/bounder 执行；字段仅是 UI guidance。费用准入、可信上界不可得、整轮 Token 不足不再全部混成一个模糊的 422。
- 检查状态时保留当前会话已知失败说明；通用 pending 不再提示无条件反复发送。没有新增失败持久化或新 migration；重启后不猜历史失败原因。已有两轮消息及其 ceiling 不改写、不自动重放；改好全局额度后需发送新消息。
- 官方 DeepSeek recipe 0.1.1/MIT 与 Token 文档调查见 [本轮复用记录](docs/research/2026-09-28-chat-admission-reuse.md)。当前无 Windows wheel，逐请求编码的 hard guarantee 尚未证实，本轮未加入新依赖；更精确预留留待后续，不可声称 200,000 已能容纳 1,000,000 配置上界。
- 本轮没有修改用户数据库、读取 API 密钥、调用付费 API、重放消息或调整已保存配置。读取本机 ready/shutdown 日志未见 llm completion；磁盘配置/DB 视图曾落后于运行实例，不能用它断言用户 DB 损坏或配置未保存。Python Ruff lint/format、ESLint/TypeScript 与代码 `git diff --check` 通过；未新增、修改或运行自动测试、smoke、GUI 验收。
- 打包脚本两次在自动审批超时而未启动，改为新目录中的分步 PyInstaller + release 桌面编译；不覆盖旧包。Core 冻结与 Vite 195 模块 / Rust release 均完成；独立新版启动路径 `D:\LivingWorld\artifacts\portable\chat-admission-fix\dreamtalk\dreamtalk-desktop.exe`，完整 ZIP `D:\LivingWorld\artifacts\portable\chat-admission-fix\dreamtalk.zip`，40,648,147 bytes，SHA256 `383193D730D3ADC1491F01C2E86BF5F38DBDA6D0F5B49AE0B9A86A4C9C2855C5`。包内四个改动 Python 文件和原生 authoring 文件哈希均与源码一致。PyInstaller 既有 tzdata/pysqlite2/MySQLdb 缺少 hidden import 警告仍存在，未运行验收其影响。默认目录与 preview-constructor-fix 均保留旧包；必须打开本轮新路径。用户旧窗口已关闭，助手未终止其进程。
- 用户后续操作：使用本轮新版目录的 exe，在设置把聊天额度改为 1,050,000 并点击“应用”（前提仍为截图的输入/输出设置），然后发送一条新消息。实际回复由用户验收。下面原生预览修复与旧产物记录为历史；不要误拿旧 default/preview 包验收本轮变化。

## 前序切片：2026-09-28 修复原生草稿构造错误

- 用户使用上轮反馈版后，预览显示“未能连接核心”。从干净 `61ee710` 接续，正式目录仍为 `D:\LivingWorld` / `codex/chat-feedback`。没有远程、发布或 push。
- 找到确定的代码错误：`application/content_authoring.py::authored_graph` 末尾使用 `ContentDraft(contents, tuple(assets), tuple(raws))`，但 `application/content.py::ContentDraft` 是 `@dataclass(..., kw_only=True)`，只能使用命名参数。该调用会抛 TypeError，影响手动/生成创建与编辑角色卡、世界书，不是特定 AI 字段或用户模型配置导致。上轮改善反馈位置，却漏查了这个构造调用；本节补足并替代“预览根因尚未知”的结论。
- 新调用为 `ContentDraft(contents=contents, assets=tuple(assets), raw_imports=tuple(raws))`。静态 AST 核对生产代码全部六个 ContentDraft 构造点，均为零位置参数；其他现有导入/包服务本来使用命名参数。
- 当前 Core 在日志 12:30:13 UTC ready、凭据同步完成，仍在运行。原 TypeError 未由 authoring route 处理；检查已安装 Starlette middleware 顺序可见 ServerErrorMiddleware 位于用户 CORS middleware 外层，异常 500 返回路径绕过 CORS，浏览器可把它表现为 fetch 失败。前端此前把非 CoreRequestError 都称为连接失败。这里的浏览器原因是基于源码和界面推断，未捕获用户原始网络响应或执行浏览器验收。
- 复用现有 HTTPException/CORS 与 StructuredLogger：authoring preview 未预期异常返回固定 `editor_preview_failed` / 500，并写入固定 `content_editor / preview_failed` ERROR 事件；不回传异常文本、草稿、用户输入或模型数据。Core composition 传入已有 logger；前端明确显示核心处理预览的内部错误。已知字段/版本/生成依据错误保持原分类；Draft → Preview → 明确哈希确认 → Commit 和 CAS 未改变。
- 本轮没有读取/操作用户数据库、读取 API 凭据、重复生成或修改 API 设置。未新增、修改或执行自动测试、GUI/browser smoke、真实搜索/模型调用；同类构造调用检查为源代码 AST 分析。Python Ruff lint/format、ESLint/TypeScript 及 `git diff --check` 通过。
- 用户旧包仍运行，未由助手终止或替换其目录。本轮复用既有 PyInstaller + release 桌面构建与随包许可步骤，跳过所有 smoke；Core 冻结、Vite 195 模块、Rust release 完成，日志 `artifacts/preview-constructor-fix-build.log`。独立新版 ZIP `D:\LivingWorld\artifacts\portable\preview-constructor-fix\dreamtalk.zip`，40,645,038 bytes / 2026-09-28 12:37:05 UTC，SHA256 `F9E7671819D089B0A0FF96E1B0F09102CCEAD4F5D1896134A1A34D0F7B518814`。desktop exe 12,391,936 bytes / 12:37:01 UTC；Core exe 13,723,248 bytes / 12:36:34 UTC。包内三个改动 Python 源文件哈希均与本轮源码一致。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在，未验收其运行影响。启动新版 `artifacts/portable/preview-constructor-fix/dreamtalk/dreamtalk-desktop.exe`，需要整个目录；默认 `artifacts/portable/dreamtalk/` 保留上轮旧包，不可拿其启动验证此修复。
- 用户接续：关闭旧窗口，再启动上述独立目录的新 exe；进入新建角色卡，使用“检查生成结果”恢复艾莲已有回执，再预览并明确确认保存。实际 UI/保存效果仍由用户验收；不需要重做付费生成。之后处理用户具体反馈，聊天大输入的整轮预留门槛仍未解决。

## 前序切片：2026-09-28 预览与保存的可见反馈

- 用户确认改用正确模型 ID 后实际生成成功，随后反馈长草稿底部“预览并保存”点击无反应。从干净 `5b35137` 接续，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback`；没有远程、发布或 push。
- 核对点击 handler、API client、authoring router、authored graph、现有预览容量/哈希确认/CAS 保存。按钮本来已连接 POST preview；错误仅显示编辑器顶部，预览也在顶部展开，没有滚动定位，长生成依据会掩盖结果。现有前端还会因缺少必填字段静默禁用。日志在 11:55:10 UTC 记录 `chat_completed`，没有记录用户本次 preview 的具体 HTTP 状态，不能将某个接口错误臆断为已复现根因。
- 编辑器现在对预览/保存错误与预览标题执行原生 scrollIntoView + focus；预览显示“尚未保存”状态，确认/返回编辑动作放在内容上下两处。正在准备时在原按钮旁显示状态；名称或条目必填错误改为点击后明确说明。确认成功后父级保存通知自动定位。复用现有 React refs/effects、CoreClient 和 Preview/Commit，不增加表单库、持久机制或依赖。
- 预览错误区分连接失效、不存在/版本冲突、预览容量、生成依据暂不可用、字段校验及 HTTP 状态。router 把 BuilderError 明确映射为 `builder_result_unavailable`，避免与普通字段错误混淆。失败保留编辑器草稿；没有删除生成回执、重复调用模型、绕过来源/哈希确认或直接写运行世界事实。
- 用户应用在检查期间自行正常关闭（日志 12:17:32 UTC），未由助手终止。尝试只读核对 app-data 存储时，运行期间的可见数据库/WAL 组合无法读取；停止后可见基库仍为 0014 且没有 builder 表，与本次成功生成和源码 0023 不对应。未用该可见副本判断用户存档已损坏，未修复/迁移/删除真实数据库；未取得此次预览失败的存储层证据。应以用户后续具体界面状态、正确运行环境日志为准。
- 本轮 ESLint/TypeScript、改动 Python Ruff lint/format 和 `git diff --check` 通过。未新增、修改或执行测试，未启动应用、执行浏览器/桌面 smoke、搜索或模型调用。既有 ContentEditor 测试含“必填缺失按钮 disabled”的旧预期，保留至用户授权测试维护。
- build-only Core 冻结、Vite 195 模块与 Rust release 完成，日志 `artifacts/preview-save-feedback-build.log`。最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,644,878 bytes / 2026-09-28 12:24:41 UTC，SHA256 `32C6383B6ED20F55C6F682752736689B8C6B709026E52FB78996BB4BCDA9FEBB`。desktop exe 12,391,936 bytes / 12:24:36 UTC；Core exe 13,723,086 bytes / 12:24:08 UTC。包内 router 源文件哈希与本轮源码一致。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在，未验收其运行影响。整个目录交付，下方产物为历史版本，构建不等于实际预览/保存成功。
- 用户接续：启动新版本，新建相应类型编辑器后点击“检查生成结果”恢复持久回执，再“预览并保存” → “确认加入当前世界”；不需要重新付费生成。若预览仍被拒绝，新版会定位并显示明确错误，不能宣称未取得的本次接口根因已全部解决。之后继续处理具体反馈，聊天整轮大输入预留门槛仍未解决。

## 前序切片：2026-09-28 资料生成与聊天额度分离

- 用户反馈 150,000/200,000 仍无法生成艾莲角色卡，并明确要求解决为什么资料生成关联聊天每轮额度。从干净 `c1e9730` 接续，正式目录仍为 `D:\LivingWorld`，沿用 `codex/chat-feedback`；没有远程，没有发布或 push。
- 原链路把聊天 ceiling 传入 Builder，再减整个可信模型输入上界；当输入上界较大时，用户提高聊天额度也无法留下输出预算。截图 150,000/200,000 的状态差异来自输入值还没有应用，但这不是预留逻辑的解决方案。
- 删除 ProductApp → WorldImports → ContentEditor → API client 的资料生成聊天额度参数。HTTP 旧 `token_ceiling` 可选/deprecated，兼容旧请求和单次 claim fingerprint，仅影响 receipt identity，不传入生成预算。新客户端只发送 kind/query 与 request ID，恢复/GET 和防重复调用不变。
- 生成请求单次输出 cap 仍为模型限制与 8,192 的较小值；现有 hard bounder 为所有路由候选预留，独立任务容量为最大候选 input+output。继续复用现有 ChatTurnTokenBudget 算术和 governed gateway，retry/fallback 共用一个有限任务 budget；逐调用可信上界、账本/金额 guard、未知结果不重放和 Draft/Preview/Commit 均保留。没有将本地分词估值假定为可信计费上界，也没有真的向模型输入百万 Token。
- 界面明确资料生成独立于聊天，不要求用户提高聊天额度。聊天区显示已应用值与未应用提示。旧失败回执改为明确提示点击“联网生成”开始新请求，“检查生成结果”只读旧请求，不自动付费重试。
- 实现前核对 DeepSeek 官方输出限制协议、tiktoken 官方示例和 LiteLLM token_counter 能力；选择直接复用既有预算/账本，不增加依赖。具体证据、推断和排除方案见[复用决定](docs/research/2026-09-28-generation-budget-reuse.md)。更新原 Builder 复用记录和 PRODUCT_SPEC，同时修正模型设置默认折叠的旧文档。
- 本轮 Python Ruff lint/format、ESLint/TypeScript 和 `git diff --check` 通过；Core/Vite 195 模块/Rust release build-only 成功，日志 `artifacts/independent-generation-budget-build.log`。没有新增/修改/执行测试、browser/desktop smoke、读取用户凭据或调用提供商/搜索。旧 Builder quota 行为与 ModelSetup disabled 行为测试预期待用户授权后同步；没有删除或弱化测试。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,643,073 bytes / 2026-09-28 11:23:35 UTC，SHA256 `1AC7E4D0B58AA87F670704163C897D82C398ED7E04BD917CB99BE6A80819B0DE`。desktop exe 12,391,424 bytes / 11:23:31 UTC；Core exe 13,723,061 bytes / 11:23:05 UTC。整个目录交付，启动入口 `artifacts/portable/dreamtalk/dreamtalk-desktop.exe`。
- 接下来用户启动新版，用新的“联网生成”请求验收实际搜索、API 响应及草稿质量；读取旧失败请求仍返回旧结果。此次资料生成修复不等于聊天自身的大上下文 Token 预留门槛已经解决；该问题仍保留后续。下方上轮关联每轮 ceiling 的描述以本节和实际代码为准。

## 前序切片：2026-09-28 模型保存按钮反馈修复

- 用户反馈“保存模型设置”点击无反应，截图中模型名称为 `deep seek`。从干净 `75108ac` 接续，正式目录仍为 `D:\LivingWorld`，分支 `codex/chat-feedback`；没有远程，没有发布或 push。
- 实际原因是名称含空格未通过已有 frontend/Rust 校验，旧按钮因 `disabled={!valid || saving}` 被静默禁用。截图上方的 Token 额度警告是独立聊天 preflight 限制，本身不阻止保存；没有证据表明这次点击已经发起保存或提供商调用。
- 保存按钮现在只在保存过程中禁用。点击后在表单及具体字段给出有界中文校验反馈，`aria-invalid`/`aria-describedby` 标注对应输入，并将焦点放到第一项错误；不合格字段不会调用 Rust IPC。校验覆盖模型名空白/控制字符/128 UTF-8 字节、密钥必填/4096 字节、完整服务地址和两个整数 Token 上限。服务地址与既有 host 规则对齐：HTTPS 或本机 HTTP，无 userinfo/query/fragment/空白/反斜线。
- 必填输入/输出 Token 上限直接显示，移除高级折叠。说明区分官方可信输入上界与本应用允许的输出 cap，未知值不猜；额度提示明确“模型设置仍可保存”。沿用 React/原生 HTML 表单和现有保存/安全凭据/回滚流程，没有增加表单库、模型预设或自动查询密钥的流程。
- 另核对 [DeepSeek 官方模型文档](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)（2026-09-28）：当前列出的模型 ID 为 `deepseek-flash` 与 `deepseek-v4-pro`，服务地址为 `https://api.deepseek.com`。仅作为用户填写指导，不静默替换模型，也不沿用过期名称或按品牌名猜 API ID。
- 本轮 `npm run lint`（ESLint/TypeScript）和 `git diff --check` 通过；`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功生成 Core/Vite/Rust release，日志 `artifacts/model-setup-feedback-build.log`。既有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在。未新增/修改/执行测试、浏览器/桌面 smoke 或提供商调用，没有读写用户真实模型配置/凭据。既有 ModelSetup 测试的“invalid 按钮 disabled”断言与新交互不同，按用户测试责任保留，需之后授权再维护。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,642,550 bytes / 2026-09-28 10:52:16 UTC，SHA256 `B057B11B11A6E1F89B30AAE54137BD366DF3B48E05074A5D23DC77C2D7938C9E`。desktop exe 12,391,424 bytes / 10:52:12 UTC；Core exe 13,723,075 bytes / 10:51:46 UTC。整个目录交付，旧截图中的折叠区/禁用行为由本节替代；桌面实际保存/重启与聊天仍由用户验收。
- 接下来优先处理可信输入上界与每轮额度的体验门槛。当前规则始终保留整个模型最大计费输入上界，即使短提示也可能超出 50,000 默认额度；输入上限与每轮上限均最多 1,000,000，因此可信输入上界为 1,000,000 的模型无法预留至少一个输出 Token。官方当前 DeepSeek 文档的上下文为 1M；不能只指导用户提高到 1,000,000 或虚填更小上界来声称解决。此次窄范围修复不调整预算/请求边界；应先调查可信逐请求计数/上界与服务端可执行限制的成熟实现，再提出保持整轮硬上限、重试/账本一致性的具体方案。

## 前序切片：2026-09-28 修复核心连接失败

- 用户反馈新版启动显示“核心连接失败”。从干净 `ed5f260` 接续，正式目录仍为 `D:\LivingWorld`，分支 `codex/chat-feedback`；没有远程，没有发布或 push。
- 两次真实失败日志均记录 `migration / alembic_schema_shape_mismatch`。只读检查实际用户数据库游标为 `0014_episodic_memory`；在一次性副本执行同一升级入口后定位为 `content_builder_jobs.created_at`：0023 迁移建成 `TEXT`，但 `UTCTimestampStorage`/ORM 及严格结构校验要求 `VARCHAR(32)`。错误发生在升级后的校验，事务回滚；不是 API 连通性或凭据问题。
- 修正 0023 新表时间列为 `sa.String(32)`，与现有存储类型一致；没有跳过校验、删库、重置存档或改变 API 配置。失败版本没有成功提交 0023，此次修复现有新增迁移即可，无需操作真实库或新建破坏性修复迁移。
- 下方上轮“0023 迁移兼容”描述需要补充：当时仅编译打包，没有执行迁移，实际新表类型不一致导致核心无法启动。上轮构建成功不能作为迁移运行成功的证据；本节取代旧产物信息。
- 本轮按用户故障诊断请求做了有界检查：存档一次性副本从 0014 升级到 0023，严格结构校验通过；修复后冻结 Core 使用另一份隔离副本和空模型配置启动，本地认证 `/system/health` 返回 200 / ready=true，`/system/shutdown` 返回 200，Core 退出码 0，副本最终游标 0023。真实数据库前后 SHA256 一致，临时副本已清理；没有读取真实凭据、调用提供商、执行 DDGS 搜索、自动测试套件或桌面/浏览器验收。
- 初次诊断辅助脚本的 SQLite 连接未及时关闭导致临时目录清理报文件占用；已修正辅助连接关闭并清理旧临时目录，随后有界启动诊断及清理正常完成。该辅助脚本位于聊天工作目录，未进入正式业务源码或测试。
- 改动迁移的 Ruff lint/format 和 `git diff --check` 通过。便携包通过 `uv run --frozen --group packaging python scripts/build-portable.py --build-only` 重新生成，Core/Vite/Rust release 构建成功；日志 `artifacts/core-startup-fix-build.log`。既有 PyInstaller 可选模块警告仍存在，隔离 Core 启动已通过，本轮没有验收聊天/生成效果。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,642,257 bytes / 2026-09-28 10:25:43 UTC，SHA256 `F87CF89CC24A91C70EF8AC820D4305A6B64F8D572806E309B5F4C4793B4DD4F8`。desktop exe 12,390,400 bytes / 10:25:39 UTC；Core exe 13,723,075 bytes / 10:25:12 UTC。直接运行 `artifacts/portable/dreamtalk/dreamtalk-desktop.exe`，或重新解压整个最新 ZIP，保留 Core 子目录；现有 app-data 会由程序正常升级。
- 接下来由用户重新打开新版，继续角色卡/世界书编辑与联网生成体验。实际桌面启动与提供商功能验收仍由用户完成；无需重新填写 API，也不需要删除现有数据库。若仍报错，优先检查新日志时间与是否启动了旧解压包。

## 前序切片：2026-09-28 内容编辑与联网生成

- 用户要求在界面新建/编辑角色卡和世界书，并输入自然语言后调用 API 联网辅助填写。本轮从干净 `d55d31f` 接续，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback`；未配置远程，没有发布或 push。
- 实现前调查 SillyTavern 1.19.0 的公开表单/条目规则、DDGS 9.16.0 与独立 Character Card Generator。选择直接复用 MIT DDGS；沿用既有 Pydantic、模型配置/凭据、governed routing/账本/硬 Token 上限和 ContentDraft/Preview/Commit。未复制 AGPL 酒馆源码，也未增加另一套模型或 agent runtime。具体版本、blob、许可证和决定见[本轮复用记录](docs/research/2026-09-28-content-builder-reuse.md)。
- 设置增加“角色卡与世界书 → 新建角色卡 / 新建世界书”，已有条目有“编辑 / 从文件更新”，原文件导入折叠在“从文件导入”。角色支持名称、描述、性格、背景、情境、说话方式、开场白、示例、标签与备注；世界书支持增删条目、主/次关键词、四种次级逻辑、常驻、启用及排序。手动填写不要求 API。
- 原生草稿直接构造 canonical graph，不伪造文件导入；更新保留兼容扩展、未开放条件、素材和角色内嵌世界书。独立内容身份从初始 revision 开始，既有快照保留；当前编辑器支持单角色卡/单世界书，字段总量最多 256 KiB、最多 128 条，特殊/过大原文件仍可导入。
- 联网只发送用户显式填写的需求，不读取其他世界或隐藏剧情。DDGS 固定 bing/brave/duckduckgo、单引擎 8 秒超时，最多八条去重检索摘要、每条最多 1,000 字符。没有自动请求结果页面。现有模型在一个 content_builder 请求里填入草稿、claims、冲突与待核对项；单次输出最多模型限制与 8,192 Token，物理 retry/fallback 共享用户设置的整轮硬上限。
- 程序验证结构、kind、长度和来源编号；出处支持/冲突判断由模型提出，不能当作全文事实核验。缺少字段依据显示待核对，情境/开场白/示例标记创作建议。源摘要、链接、检索时间和原始生成稿进入 authored preview；用户编辑后明确提示依据对应原始稿。
- 新增独立 `0023_content_builder_jobs` 迁移，兼容校验保留 0022 历史形状。World/request ID/fingerprint 有原子单次 claim，ready/failed 回执持久化。同一 ID 不再次 dispatch；重启遗留请求报告 interrupted，不自动重放。界面保留最近 request ID，“检查生成结果”只 GET；可结束等待继续手动填写。新生成是新的模型调用。
- 保存仍需要确切哈希确认与 replacement CAS，不创建 WorldTruth/Observation/Belief/Knowledge/Memory。角色首次打开聊天才实例化；世界书仍默认隐藏，保存/更新后逐条确认公共背景。
- 本轮静态检查：全 Core Python 源码和构建脚本 Ruff lint 通过，新模块 format check 通过；spec 仅排除 PyInstaller 执行全局名 F821；ESLint/TypeScript、`git diff --check` 通过。没有新增、修改或执行测试，没有启动应用、调用提供商或执行真实 DDGS 搜索验收。旧测试的硬编码 schema head 等预期留待用户授权维护。
- 最终 `uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功，冻结 Core、Vite 195 模块及 Rust release 均完成。构建日志 `artifacts/content-builder-build.log`。Analysis 和包文件包含新 authoring/builder/research 模块、0023 迁移、DDGS 动态搜索引擎、primp.pyd、lxml etree/objectify；MIT/BSD 上游 notices 和 primp SBOM 随包分发。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，40,643,420 bytes / 2026-09-28 10:01:39 UTC；SHA256 `758CEED6E3206AAEAD730AA3F97E0DBDB4431EF888FE801B014A0F44FCC552B3`。desktop exe 12,390,400 bytes / 2026-09-28 10:01:36 UTC；Core exe 13,723,081 bytes / 2026-09-28 10:01:08 UTC。整个目录供用户验收，编译/打包不能证明真实联网/资料质量/隔离或迁移运行验收已通过。
- 构建仍有 jieba 三处 regex SyntaxWarning，以及 tzdata/pysqlite2/MySQLdb hidden-import 警告。当前 179 个 missing-module、2 个 excluded-module 分析项，没有以 livingworld/ddgs/primp/lxml 命名的缺失模块项；新增部分为 lxml 可选/旧兼容分支。跨盘 uv hardlink→copy 和 Git 行尾提示仍存在。原始模块警告在 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，未进行运行验收其影响。
- 接下来由用户按新版入口验收：手动创建/编辑、艾莲角色卡生成、世界书条目生成、预览确认、公开范围与聊天使用、生成结果恢复；优先处理真实反馈。联网依据目前为摘要；未实现头像生成、网页全文核验、来源持续更新或创建完整运行 World 的 Builder。聊天流式输出继续是后续任务。
- 下方较早聊天召回及其他记录保留为历史切片，旧产物信息和“仅导入/Builder 未实现”的表述以本节及实际代码为准。

## 前序切片：2026-09-28 较早聊天原文召回

- 接续起点 `903cf10`，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback`；开始时工作区干净。
- 实现前调查 SQLite FTS5、jieba、Mem0 Python 和 BM25S；选择已有 SQLite FTS5 + 固定 jieba 0.42.1。具体来源、依赖代价和排除方案见[复用记录](docs/research/2026-09-28-chat-recall-reuse.md)。jieba 字典、finalseg 资源和 MIT 许可证纳入冻结/便携包。
- 新增应用层 EarlierChatRecall 和基础设施 Fts5ChatRecallRanker，生产私聊/群聊角色回复已接线。先确认当前角色有权看到当前会话，再用已有 World/Player/Conversation SQL 分页读取更早记录；只在授权候选的临时内存索引上用 BM25 排序。
- 当前玩家文本末尾最多 1,024 字符、24 个分词；最多扫描三页/300 条、512 KiB 原文；最多召回四条、8 KiB 原文及其消息/发送者身份类型与当前显示名/位置/时间出处。角色已有最近上下文的 turn 不重复召回。原文作为 lower-trust 数据，不写入 WorldTruth/Observation/Knowledge/EpisodicMemory。
- 没有额外模型调用、embedding、迁移或持久检索索引；群选人器和公共世界书激活窗口不变，既有 Token 硬上限仍检查最终提示词。本轮不是完整语义检索或自动长期记忆形成。
- 本轮静态检查：改动 Python 源码、构建脚本及 jieba hook 的 Ruff lint/format 通过，`git diff --check` 通过；spec 仅对 PyInstaller 提供的执行全局名排除 F821，实际 spec 编译/打包成功。没有新增、修改或运行测试，没有启动应用或调用提供商。此前世界书测试的历史预期仍待用户授权后维护。
- 本轮 `uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功：冻结 Core、Vite 194 模块和 Rust release 编译完成。清单包含两个新检索模块及 HMM Python 模块；包内只包含 jieba 的 dict.txt/finalseg 数据，没有 lac_small/Paddle 数据。词典 5,071,852 bytes，附完整 MIT 许可证且其随包副本哈希与源文件一致。
- 最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，30,493,996 bytes，2026-09-28 08:31:53 UTC，SHA256 `EA5A3511905B177D358C8E450A397F9CC5783E08159DB2064AEAC76CF039C9D7`。desktop exe 12,386,816 bytes / 2026-09-28 08:31:50 UTC；Core exe 13,325,902 bytes / 2026-09-28 08:31:24 UTC。整个解压目录供用户验收，构建不能替代长对话效果/延迟/隔离验收。
- 构建警告：新增 jieba 三处正则转义 SyntaxWarning（Python 3.13）；原有 tzdata/pysqlite2/MySQLdb hidden-import 警告仍存在。Analysis 记录 166 个 missing-module、2 个 excluded-module 项，无以 livingworld 命名的缺失项。jieba 的可选 pkg_resources 在源码中有 ImportError 文件读取 fallback；本切片明确排除未使用的 lac_small/Paddle。原始记录 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，未运行验收其影响。依赖安装还有跨盘 hardlink→copy 性能提示，Git 有 LF→CRLF 提示，均已记录。
- 下一步先调查并接通现有 provider stream 到聊天界面的可靠呈现，解决 terminal 校验、一次性 claim 和账本一致性；同时优先处理用户验收反馈。召回的同义表达/更远历史及自动记忆形成分别保留后续任务，不把当前词法结果宣称为完整长期记忆。
- 下方世界书基础激活和聊天反馈保留为历史切片；产物以本节完成后的最新记录为准。

## 前序切片：2026-09-28 世界书基础激活

- 接续起点为 `f5dce91`，正式目录 `D:\LivingWorld`，沿用 `codex/chat-feedback` 分支。开始时工作区干净；没有创建新的旧工作克隆。
- 已完成成熟方案调查：SillyTavern 1.19.0 的公开基础规则、Character Foundry 0.5.0 的格式能力；后者没有运行时激活器。本轮复用现有权限读取、规范化字段与聊天上下文，未新增依赖、模型调用、持久字段或数据库迁移。见[复用记录](docs/research/2026-09-28-lore-activation-reuse.md)。
- 公共世界书从“命中优先、未命中可填充”改为基础条件激活：常驻、主关键词、四种次级逻辑、大小写、完整单词及有界会话历史扫描。公开是访问权限，不等于本轮必定注入。私聊和群聊共享同一规则；群内前面的已保存台词可触发后面的角色背景。
- 来源扫描深度通过同一 accepted 快照的 LoreCollection 读取，默认两条，最多 32 条/16,384 个原始字符。仍限制 16 条背景及 12 KiB，保留 lower-trust 数据和世界隔离。
- 未支持的正则/模板、概率、时序、互斥组、角色筛选等条件不会被忽略后照常注入；条目详情显示具体支持范围/暂不参与原因和次级关键词。向量、完整递归、源插入位置及隐藏角色专属授权未接入。
- 现有测试的“公共条目无条件进入提示词”预期需要在用户授权测试维护后同步；本轮没有改动或运行测试，不以旧测试证明新激活规则。构建与静态检查结果在本节补充。
- 本轮静态检查：改动 Python 文件 Ruff lint 通过，新增激活模块/持久读取格式检查通过；`npm run lint`（ESLint + TypeScript）及 `git diff --check` 通过。没有新增、修改或运行测试，没有启动应用或调用提供商。
- 本轮交付：`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功，冻结 Core、Vite 生产构建与 Rust release 均完成；PyInstaller Analysis 清单含 `livingworld.application.lore_activation`。最新 ZIP `D:\LivingWorld\artifacts\portable\dreamtalk.zip`，27824584 bytes，2026-09-28 07:27:52 UTC，SHA256 `E5E264F85AB4A73359DCBCBCC09784D3E7429A4B2B6224C425978EDD8C9258A2`。整个解压目录供用户验收，构建不能替代运行效果确认。
- 构建仍有 `tzdata`、`pysqlite2`、`MySQLdb` hidden-import 警告及 162 项平台/可选库/静态符号等 missing-module 分析项；无以 `livingworld` 命名的缺失模块项。原始记录 `artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`，本轮未验证其运行影响。
- 下方聊天状态反馈及其他旧记录是历史切片；旧产物哈希以本节后续记录为准。

## 前序切片：2026-09-28 聊天状态反馈

- 用户已授权自行选择技术方案并继续开发；每个新功能实现前先调查成熟项目，记录具体复用决定。规则已写入 AGENTS.md。
- 正式工作目录为 `D:\LivingWorld`，本地分支 `codex/chat-feedback`；不再使用旧工作克隆。开始接续时仍须核对实际 Git 状态。
- API client 接通现有 FastAPI `detail` 的有界机器标签；私聊/群聊区分保存、等待回复和检查状态，提供中文的模型、预算、校验、生成、账本异常提示。
- “检查回复状态”读取当前会话最近玩家消息的已有 GET，重新打开会话后仍可操作；不重放模型。群聊生成等待期间串行读取有界消息页，每次读取结束后间隔两秒，让已经保存的发言陆续出现；连续两次读取失败后暂停，手动刷新可恢复；离开会话或请求结束后停止读取。
- 尚未接通 Token 流式输出，尚未持久记录群轮停止原因；`completed` 只表示本轮终结，不能推断是自然停止。未增加依赖、数据库迁移或测试；未运行运行时/提供商验收。
- 本轮验证：`npm run lint`（ESLint + TypeScript）和 `git diff --check` 通过；`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功生成前端、Rust 发布版与冻结 Core。没有运行测试、便携包 smoke 或提供商调用；实际效果由用户带自己的 API 验收。
- 最新便携包：`D:\LivingWorld\artifacts\portable\dreamtalk.zip`，27,814,276 bytes，2026-09-28 06:55:33 UTC；SHA256 `59B1076CDBFF2D6AEEA0AAF020E464B1604E3BDF4094D16A08A34002F3C103E3`。解压后运行 `dreamtalk\dreamtalk-desktop.exe`。此产物信息覆盖下方历史产物哈希。
- PyInstaller 分析仍产生平台分支、可选依赖及属性符号等 missing-module 警告，未出现以 `livingworld` 命名的缺失模块项。原始记录：`artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`。构建成功不能替代运行验收，不宣称运行无警告。
- 复用调查和边界见 [本轮决定](docs/research/2026-09-28-chat-feedback-reuse.md)。下方“本轮仅文档交接”及基线描述保留为上次交接的历史记录，以此最新接续和实际代码为准。

## 1. 当前目标与上下文

用户要求先把核心聊天体验、导入、世界隔离和设置的真实效果完善到可亲自验收，然后会带自己的 API、角色卡、世界书试用。项目还没有最终验收，不应宣布完工。当前优先级是可用的沉浸聊天，而不是继续堆架构或准备 GitHub 发布。

最近讨论集中在两点：

- 世界书如何真正参与聊天，同时排除默认隐藏的暗线；群聊中所有参与角色应能参考已经发出的消息。
- 不重复造轮子。已取消“必须独立实现”的限制，允许评估成熟项目/组件；现有适配器没有因此被删除，也没有引入 SillyTavern 运行依赖。

原始交接轮是**文档交接任务**，只更新 AGENTS.md 并创建 HANDOFF.md，没有修改业务代码；之后的业务进展以顶部最新切片为准。完成后新对话应继续产品开发，不再向用户索取已明确的四标签布局、群聊 Token 规则或世界隔离要求。

## 2. 仓库与代码基线

本轮写入前已实际检查两处 Git 仓库，它们均为 `master`，工作树和暂存区干净，HEAD 一致：

```text
1e7843cd71f557a0db2b5a4ecfa01bb9ccaaf17d
feat: prioritize relevant public lore in chat context
```

这是本次交接的**业务代码基线**；本轮后续文档提交不改变业务实现。

| 位置 | 本轮实际用途 |
| --- | --- |
| `D:\LivingWorld` | 用户的正式交付仓库；本轮检查时没有配置 Git remote，未连接 GitHub。 |
| `C:\Users\zhang\.codex\visualizations\2026\09\15\01a0a4e1-d243-7fc2-86dc-5a29a37df3ce\livingworld-work` | 本次受限环境允许写入的工作克隆；`origin` 指向 `D:\LivingWorld`。不是云端仓库。 |

若新对话可直接写 D 盘，优先在那里工作。若权限仍限制 D 盘写入，沿用工作克隆，先核对两边状态/哈希，在工作克隆提交后通过明确路径的 `git pull --ff-only` 同步 D 盘；不要覆盖 D 盘的新修改、强推或重写历史。构建产物属于 ignored 文件，Git 同步不会自动复制它们。

开始接续时执行：

```powershell
Set-Location D:\LivingWorld
git status --short
git log --oneline -8
git diff --stat
git diff --cached --stat
```

检查是否有另一任务正在修改相同文件，不把用户/其他任务的修改混入自己的提交。不要根据本文件推测活动进程已经退出；本轮没有启动或关闭应用。

## 3. 已完成到什么程度

以下“已实现”依据本轮源码读取，**不等于本轮实际运行或用户验收通过**。

| 能力 | 实际实现与当前界限 |
| --- | --- |
| 运行底座 | React/TypeScript/Vite、Tauri v2 Windows 壳、Python/FastAPI Core、随机 loopback 端口、认证发现与启停、SQLite/Alembic、日志、既有 CI 均存在。 |
| 普通界面 | PC 宽度的中文聊天 / 通讯录 / 设置 / 我；创建切换世界、暂停恢复、倍率、可用/忙碌、个人资料、当前世界导入和已知事件入口已接入 API。 |
| 身份与内容 | 每世界绑定本地 Player；默认从“家”进入；角色卡/世界书预览确认与独立更新；当前世界通讯录；首次打开聊天才创建/复用运行时 Character。 |
| 私聊 | 持久 Conversation、Player Message、turn、一次性 dispatch claim、角色生成与受控持久回复；页面发送、读取和错误提示已接线。 |
| 群聊 | 选择两个或以上角色建群；固定成员、共享持久记录、独立选人器、`@` 首位指定、逐条角色回复、整轮共享 Token 上限、完成标记。不是永久自主角色聊天。 |
| 聊天阅读 | `react-markdown` 安全渲染、回车发送/Shift+回车换行及输入法保护、自动滚动/历史位置处理、最近消息分页和“加载更早消息”。 |
| 世界书背景 | 世界书条目默认隐藏；当前世界逐条设为公共后，还须满足常驻或支持的关键词条件才进入聊天。已有次级条件及有界历史扫描，未实现完整酒馆激活。详见最新接续及第 5 节。 |
| 群聊知情 | 群成员即使没发言，也能在之后的私聊/其他群聊上下文读取自身参与群的有界消息窗口。不是自动 Knowledge/Truth/Memory 写入。 |
| 角色记忆 | C-007A 的 owner-scoped、Observation 证据支持的 EpisodicMemory 已存在，私聊/群聊回复读取本角色的有界记忆；另有当前会话的有界较早原文词法召回；尚未实现 EpisodicMemory 长期整理、语义检索或自动聊天记忆形成。 |
| LLM 底座 | OpenAI-compatible Chat、OpenAI Responses、Anthropic Messages、Gemini Interactions 四种 adapter；非流式/流式基础契约、structured validation、retry、routing、usage/pricing、financial budget、session credentials 已有。 |
| 内容兼容 | Character Card V2/V3、PNG/JSON 读取，Lorebook 标准化，原始兼容数据保留，外部 JSON 导出和 `.lwcontent` authored-content package 已有。并非完整酒馆兼容。 |
| 世界运行底座 | 确定性命令、行动、Scene、事件、Observation、tickless scheduler、sparse activation、clock reconciliation/catch-up、账本/回放和 CAS 已有；正式行动 registry 目前只有 `move_player` v1。 |
| 开发者工具 | `?developer=1` 可选择 Inspector 页面；相关 Core 开发 API 仍需显式 developer mode。它不是普通界面或自动 Activation consumer。 |
| 本地交付 | 已有随附冻结 Python Core 的 Windows 便携目录与 ZIP；无需使用者安装开发语言。没有签名安装包、自动更新或 GitHub 发布。 |

**明确未完成：** 完整自主 Character Agent、Director 批量计划/Event Reservoir 的生产执行与主动剧情、Activation consumer、自动知识传播、长期记忆整理/语义检索、完整 AI World Builder（当前角色卡/世界书摘要生成已实现）、Checkpoint/Timeline Branch 产品能力、`.lworld` 运行世界包、cloud sync/marketplace、完整模型管理、普通聊天页的流式输出，以及完整酒馆世界书激活行为。不要因为 docs 说 Stage 2–5 已冻结，就推断这些产品功能也已完成。

## 4. 本轮与紧邻前序工作的文件变化

### 本轮只改两份文档

| 文件 | 修改 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 同步最新优先级、自主推进/局部跳过、用户负责测试、三段式汇报、成熟组件复用、PC 聊天规则及验收前不发布；删除旧的“一切不确定立即停”与强制逐任务停止/自动测试冲突规则。 |
| [HANDOFF.md](HANDOFF.md) | 当前现场、入口、限制、近期改动、构建证据、继续顺序与易误解处。 |

没有业务、数据库迁移、测试或构建脚本变更。本轮没有重建便携版。

### 前序已提交的最近切片

下面来自实际 `git show`，不是本轮未提交工作：

| 提交 | 文件与用途 |
| --- | --- |
| `1e7843c` | `application/chat_context.py`：公共 lore 相关性排序，私聊传入本轮玩家文本；`application/group_chat_context.py`：群聊角色回复复用该排序；`docs/architecture/CHAT_MODEL.md`：记录真实范围和限制。 |
| `309719c` | `apps/web/src/GroupChat.tsx`：点击唯一命名群成员插入 `@名字`，保留光标位置并检查输入长度；`apps/web/src/product.css`：简洁样式；`CHAT_MODEL.md`：记录交互。不改服务端选人语义。 |
| `1b57f6b` | `AGENTS.md` 及 `docs/architecture/ADR/0001_reuse_mature_projects.md`：允许评估成熟组件；ADR 索引及 `ARCHITECTURE_REVIEW_001.md`：保留历史、标注被替代的独立实现限制。 |
| `7009288` | `scripts/build-portable.py` 和 `README.md`：加入 `--build-only`，允许构建而不隐式运行 smoke。默认脚本仍含自检。 |
| `6bfbb06` | HTTP CORS 修正为允许 `PUT`，否则桌面公共世界书开关的预检请求会失败。不要退回只有 GET/POST 的配置。 |

更早的 `64b6413` 已建立公共 lore 与群消息可见性；`5980f92`、`d7ca0b8` 已建立有界上下文读取/消息分页。继续前用 Git 查看需要修改的具体文件，不重新实现这些切片。

## 5. 接续工作需要知道的实际实现

### 5.1 从前端到 Core

```text
apps/web/src/main.tsx → App.tsx
  → connection.ts / CoreClient
  → ProductApp.tsx
    → WorldContent.tsx / ProfileEditor.tsx / ModelSetup.tsx
    → ChatTranscript.tsx / GroupChat.tsx
  → adapters/http/{worlds,profiles,world_content,player_events,chat_conversations,chat_messages}.py
  → application services
  → infrastructure/persistence adapters
```

- 桌面连接通过 Tauri `core_connection` 返回 endpoint/token/generation，浏览器开发连接通过 `virtual:core-connection`；UI 不硬编码 Core 端口。
- `App.tsx` health 成功后调用 `report_ui_ready`。Tauri 主窗口初始隐藏，不能把 Core ready 与 UI ready 混为一谈。
- API 协议从 `domain/api_contract.json` 集中读取，目前 `api_protocol = 1`。Tauri 的 dev UI 端口 1420 不是 Core 端口。
- `ProductApp.tsx` 默认整轮额度为 50,000，可设置至 JavaScript safe integer（Core 仍校验 int64）；沿用 `livingworld.chat.turnTokenCeiling` 和 `livingworld.lastWorldId` localStorage 键。
- 模型配置 UI 在 `ModelSetup.tsx`；Rust IPC/config/credential 操作在 `src-tauri/src/lib.rs`、`llm_config.rs`、`credentials.rs`、`supervisor.rs`，不存在独立 `model_setup.rs`。

### 5.2 消息、claim 与角色生成

```text
打开联系人 → ChatConversationService → 世界内稳定 Character/Conversation
保存玩家消息 → ChatMessageService → SqlAlchemyChatMessageStore → pending turn
请求回复 → DirectChatReplyService / GroupChatReplyService
  → 上下文与 route/token preflight
  → 持久一次性 claim
  → governed gateway.generate(..., turn_budget=同一对象)
  → 校验 → durable reply / group completion
```

- HTTP 前缀为 `/api/v1/worlds/{world_id}/conversations`，需 bearer；发送还需 `X-Request-Id`。
- 私聊保存：`POST /{conversation_id}/messages`；群聊保存：`POST /{conversation_id}/group-messages`。二者返回 202 pending，不等于模型已经发言。
- 生成分别使用 `POST /{conversation_id}/turns/{turn_id}/reply` 和 `/group-turns/{turn_id}/reply`；对应 GET 可读 pending/claimed/completed。已完成结果读取不再次付费生成。
- UI 使用 `GET /{conversation_id}/messages/page`，默认 50、最大 100，游标 `before_position`；旧的完整消息读接口仍保留，不能让普通页面退回每次读全部历史。
- claim **不可重新领取**。模型失败、HTTP timeout 或重启后的 claimed turn 不自动 replay。UI 可查询一次状态，不自动再次生成。部分群回复已经持久提交时保留它们。
- 私聊及角色群回复只接受匹配 invocation 的非空、有界文本，finish 为 STOP 或 REFUSAL；截断不是成功回复。群选择器只接受合法成员 ID，已有回复后可返回 STOP。
- 群回复当前另外有 32 条安全上限；选择请求输出最多 8,192 Token，受模型设置和整轮剩余额度约束。`@` 只绕过首次选人调用，不禁止本轮随后选择其他人。
- 当前回复服务用 **`generate()`**，不是 `stream()`。基础 SSE adapters 已有，不代表 UI 已逐字流式显示。接通流式时不能破坏一次性 claim、终端校验、账本和未知用量处理。

### 5.3 聊天上下文

直接入口为 `application/chat_context.py::DirectChatContextBuilder`；群入口为 `group_chat_context.py::GroupChatContextBuilder`，共享公共背景、记忆及历史窗口工具。

- 角色人格从当前世界 accepted import replacement lineage 解析；更新卡片不换 runtime Character 或丢失聊天。
- 本地通用/世界资料都提供给角色，system 明确世界专属描述优先。没有自动语义冲突合并器。
- `private_chat_memories` 当前最多 12 条、内容累计 8 KiB；按 Character owner 读取，不是 RAG。
- prompt transcript 按完整 turn 截取，最多 32 条消息/96 KiB，不裁掉当前 turn；持久层有有界读取，不为 prompt 加载全部历史。
- `application/chat_recall.py` / `infrastructure/chat_retrieval.py` 在最近窗口之外召回当前会话原文；先授权、三页/300 条/512 KiB 扫描、最多四条/8 KiB 注入。FTS5 + jieba 词法排序，带出处、无新证据记忆或持久索引，详细范围见最新接续。
- 本角色曾参与的群消息读取默认最多 32 条，再受 8 KiB 内容预算约束；另一个群回复时排除当前群以避免重复输入。群选人器不拿任何角色私有记忆。
- 角色卡 `first_mes` 仅作有界语气示例（8 KiB），不是自动发出的开场消息。
- 导入文本、背景、个人资料、消息都是 lower-trust data。世界书/角色卡中的作者指令不是新增 privileged system instruction。

### 5.4 公共世界书为有界基础激活

- `SqlAlchemyWorldContentStore.list_common_lore` 先限定指定世界、当前 accepted 版本及明确公开的条目；匹配不能授予隐藏条目权限。`CommonLoreEntry` 可附带同快照的所属 LoreCollection 供读取扫描深度。
- `application/lore_activation.py` 消费已规范化的常驻、主/次级关键词、大小写、完整单词和扫描深度。`common_chat_lore` 私聊使用当前可见 transcript，群聊使用包含已保存发言的当前群 transcript；不扫描另一个会话或背景正文。
- 默认最近两条消息，条目 scanDepth 覆盖书 scan_depth，最多 32 条/16,384 个原始字符。零深度不触发普通关键词；常驻不依赖关键词。四种已识别次级模式生效，空次级列表不附加条件；未知模式不猜测。
- 未命中条目不再填入剩余背景。关键词命中优先于常驻，其后 priority 降序、order 升序、稳定 ID 排序；最多 16 条、title/content 共 12 KiB，超预算跳过。ignoreBudget 不绕开限制。
- 正则/模板关键词及尚未支持的概率、时序、互斥组、角色筛选等条件使条目暂不参与聊天，界面解释原因。向量检索、递归扩展、源插入位置及脚本不执行；不是完整 ST World Info 兼容。
- 内容 GET/预览增加只读 activation_summary、secondary_keywords；无数据库迁移。公共标记仍按 `(world_id, import_id, entry_id)` 保存，替换导入后需要对新版本显式开放。

### 5.5 Token、预算和模型配置

- `ChatTurnTokenBudget` 是本轮串行使用的内存预留对象；玩家 Message/turn 保存原始额度、claim 防止重启重新开始。同一群轮中的选人和回复共享一个对象，并传入底层物理 retry/fallback。
- 必须有 `HARD_UPPER_BOUND`。已核对 DeepSeek 官方文本 framing 与 OpenAI 原生 Responses 完整输入计数可逐请求预留；其他形状/提供商及计数失败按模型输入上界预留，不是按短 prompt 猜输入长度。
- usage 不完整时保守消耗预留并关闭本轮；超过上界时报告完整性问题，不把事实用量改小。
- `bootstrap/llm_runtime.py::_chat_reply_configuration` 只选唯一合格模型或显式 `character_dialogue` 的 BALANCED route；多模型无路由时不猜。每个候选都需可信 limits；可用性还依 route policy 检查 session credential。
- 桌面简化模型设置面向 managed single configuration，可创建/更新并通过 supervisor 重启 Core；不会在保存配置时测试 key 或生成回复。高级配置不能被简化表单默默覆盖。
- 四种 adapter 的“有实现”不保证任意代理地址/模型都兼容。浏览器没有桌面的 OS credential IPC，不能把桌面设置能力宣传成浏览器完全相同。
- 已有 financial Budget Guard/usage ledger 和聊天 Token 上限是两种不同约束。预算按 requested ModelRef 归属，reported model 可用于实际定价。不要改成 requested OR reported budget matching。
- 账本 START 失败不得调用模型；模型执行后 FINALIZE 失败不能重放模型、不能伪造零费用，持久 START 保持 INCOMPLETE。routing 已有 invocation 级共享 monotonic deadline，fallback 不重置。

### 5.6 Canonical state、记忆与迁移

- `WorldTime` 是逻辑 epoch 的整数微秒；真实时间用 UTC-aware datetime。两者不可隐式互换。前端显示用 BigInt/字符串，不经过浮点微秒。
- Alembic 是唯一迁移 authority，当前源码 head 为 `0022_world_common_lore`。legacy `schema_version`/`migration_history` 是兼容审计，不是另一套 runner；ambiguous legacy 状态 fail closed。
- `0017` 世界快照、`0018` conversations、`0019` messages、`0020` dispatch、`0021` group completion、`0022` common lore 已存在。不要重新创建同名机制或凭旧 Stage 文档猜 schema head。
- 普通移动唯一入口为 `ActionResolutionService`；兼容 `MovePlayer` 适配进去。初始化放置与玩家行动不是同一语义。
- CreateWorld commit 后经 lifecycle port 注册 WorldSimulationRuntime；运行时失败标 degraded，不把已提交世界谎称 rolled back。
- `RecordEpisodicMemory` 要求真实、同世界且该 Character 获准的 Observation 证据。普通聊天目前不生成这些证据，不自动写 EpisodicMemory。不能为实现“独立记忆”伪造 Observation 或自动把消息断言为事实。
- Player 的置顶事件 feed 先按绑定 Player 的 event Observation 授权；安全标题能力有限。无已知事件时为空，禁止用假剧情填补。

## 6. 已确认决策与理由：避免重新询问

长期约束见 AGENTS；这里记录接续实现时最易误判的决定：

| 决策 | 原因/实现影响 |
| --- | --- |
| 世界专属内容是确认快照 | 同卡/同书在多个世界使用不能串改；替换沿 lineage 保留身份与历史。 |
| 首次开聊才建 Character | 导入只是创作内容；通讯录先可见，不触发后台角色或付费活动。 |
| 群聊独立选人 | Director 的 batch-planner contract 不能被逐句选人调用改变；`@` 确定首位。 |
| 输入+输出整轮硬上限，可信保守预留 | 防止多角色、选人、retry/fallback 累计爆量；用户接受宁可提前停。 |
| 公共背景可共知，暗线默认禁止 | 导入不等于授予角色所有知识；关键词 relevance 排在权限过滤之后。 |
| 所有固定群成员看到消息 | 沉默成员不会因没回复就遗漏群消息；消息内容仍可能是假话。 |
| 台词直接发送，持久创作预览确认 | 避免聊天逐条确认，保留 authored content 的审查边界。 |
| 不再要求独立实现 | 优先效果和维护成本；[ADR-0001](docs/architecture/ADR/0001_reuse_mature_projects.md) 已替代旧 review 的该限制，未更改 Apache-2.0。 |

## 7. 不应重复的路径与历史问题

- 不能把 `cargo test` 留下的桌面 executable 当作正式 custom-protocol 产物。历史曾出现 Core/supervisor ready 但无 ui_ready；正确正式命令在第 10 节。本轮没有再次 smoke，也不声称历史原因已再次验证。
- 不反复启动窗口/点击/第三次无新证据重试同一失败。保留 artifact 路径、修改时间、安全 stdout/stderr 与实际等待条件后再判断。
- `uv` 默认 cache 访问曾在本受限会话被拒绝，最近打包改用已有 `.venv\Scripts\python.exe` 调用同一脚本。不要把 cache 权限问题误判为项目代码坏了或循环重装依赖。
- 默认 `build:portable` 含 standalone smoke 和 Rust supervisor test；“只打包”需 `--build-only`，不要绕过用户负责测试的决定。
- 不沿用 legacy MovePlayer 独立写 PlayerMoved，不添加自动 Activation→action 或 Observation→Memory 来拼演示链路。[CODEBASE_AUDIT.md](docs/architecture/CODEBASE_AUDIT.md) 的 Q-001A disposition 已记录原因和修复。
- 对未知/缺少模型 bounds、含糊的 `@`、未知 provider usage，不能用“看起来够用”放行。
- 不把原始 ST world-info regex、脚本、私有字段直接执行，不把 raw compatibility 数据当 privileged prompt，也不为“完全兼容”破坏 canonical invariant。
- 不直接粘贴需要不同许可义务的代码后仍宣称全部 Apache-2.0；目前实际复用的是公开行为/规范及适合的既有依赖，如 `react-markdown`，不是一个已嵌入的 ST runtime。

## 8. 尚未完成、风险与技术债

### 用户体验缺口

1. **长期独立记忆尚不完整。** 已有 owner-scoped EpisodicMemory、有界近期窗口及当前会话较早原文词法召回；普通聊天尚未形成长期证据记忆。召回仅扫描窗口前最多三页，不支持同义/指代和无限历史；别将持久 Message 与完整记忆系统混为一谈。
2. **世界书与酒馆能力仍有差距。** 当前支持有界基础条件激活，向量、递归、概率/时序和源注入位置尚未接入；隐藏背景没有角色专属授权传播路径。不能宣称已实现 ST 的所有功能。
3. **Director 和主动事件尚未生产接通。** 现有世界时间、scheduler 和事件账本不能自己生成丰富剧情；event feed 当前只有有限安全标题。
4. **聊天仍是整段生成后出现。** 缺少普通界面流式输出；群聊可能有多次选人和生成耗时。
5. **保守 bounds 配置对普通用户仍有门槛。** 常见型号已复用容量预设，未知型号/服务仍需高级手动核对；逐请求预留目前只覆盖已核对 DeepSeek/OpenAI 直连文本子集，其他模型/形状仍有门槛。
6. **未知结果/claimed turn 缺少完整恢复 UX。** 当前不重放可防重复付费，但用户可能看到已存玩家消息却没回复；完善明确状态说明，不能偷偷清除 claim。
7. **模型设置仅有简化管理。** 多 provider/route 高级管理、tools、真实代理兼容验收、云端/多用户身份不完整。

### 文档和维护风险

- `docs/architecture/PRODUCT_SURFACE.md` 个人资料部分仍有旧阶段“未实现 prompt assembly”句子；现在 `chat_context.py`/`group_chat_context.py` 已组装资料。后续可局部修正文档，别因此再写一套上下文。
- `CHAT_MODEL.md` 的少量早期段落仍写“API opens/lists only”，后文已描述 send/reply。以真实 endpoint、当前服务和后续段落为准。
- `CODEBASE_AUDIT.md` 保留旧 A-001～A-005 的 FIX_NOW 文字供审计历史，顶部 disposition 已解决；Q-001B Inspector 已在代码中，不应重新宣告阻塞。DEFER 中的大 command handler、广 UoW、schema compatibility matrix、provider pipelines、全 ledger replay、large ORM/supervisor 等债务仍不能说已全消除。
- 便携版未签名/无自动更新；本机历史 `livingworld_core` wheel 文件比最近业务代码旧，不能当最新 dreamtalk wheel 分发。
- 本轮未确认新的可复现业务 bug；“尚未运行验证”不是“已知无 bug”。旧 Python 应用错误弹窗的本机原因没有本轮证据，不应编造已修好或已复现的结论。

需要用户判断但**尚未在当前切片解决**的边界，应在有具体设计时汇总：新 chat-memory evidence/形成路径、隐藏设定如何授权到特定角色、World Plan/event narration 的详细产品语义。先推进其他确定工作，不重新询问第 6 节已确认项。

## 9. 验证与现存产物

### 本轮实际完成的核对

- Git status/log/diff/cached diff；D 盘与工作克隆业务基线一致且写入前 clean。
- 阅读主要 UI、API、chat/context/reply/budget、bootstrap、public lore persistence/migration、memory、Tauri 配置/入口和构建脚本。
- 核对现存 ZIP 的 SHA-256、exe 修改时间及开发依赖目录存在。
- 本轮仅文档编辑，不跑 Python/前端/Rust 测试、smoke、付费 API，不启动应用，不重新构建。文档写入后的 `git diff --check` 无问题；链接脚本检查 535 个本地目标，0 broken（111 个外部 URL 仅计数，未在线验证）。

前序对话曾报告最近的 Web build 与 `build-portable.py --build-only` 成功；本轮重新确认了产物存在，但未复跑构建、未取得本轮运行验收证据。不要引用旧测试数量作为当前代码全部通过的证明，也不要把“配置可保存”当作“API 真实调用成功”。

现存可供用户试用的文件（2026-09-28 核对）：

```text
D:\LivingWorld\artifacts\portable\dreamtalk.zip
D:\LivingWorld\artifacts\portable\dreamtalk\dreamtalk-desktop.exe
D:\LivingWorld\artifacts\portable\dreamtalk\core\dreamtalk-core.exe

ZIP SHA256:
4B186D95477E26F97DF8652AC5CC3400BC9FC6FB98F5A55ACCA434F7CF5638D8

desktop exe LastWriteTimeUtc: 2026-09-27 15:54:43Z
core exe LastWriteTimeUtc:    2026-09-27 15:54:17Z
```

该 ZIP 没有在本轮确认到一个内嵌源码 commit marker；不能仅由时间戳保证可执行文件与任意后续 HEAD 完全一致。两份文档的本轮更新不需要重打包。运行时需整个解压目录及 WebView2，不能只复制桌面 exe。

用户尚需自行验收：自己的 provider/key/model 的实际聊天，角色卡/世界书导入与公共开关效果，群聊选人和整轮上限，切换世界隔离，重启后数据，暂停/倍率/availability 和设置更新。没有授权因此自动发送付费验证调用。

## 10. 关键命令与调试入口

开发依赖见 README：Python 3.12+、uv、Node 24+、Rust/MSVC/WebView2。缺依赖才安装；本轮 D 盘 `.venv` 与 `node_modules` 存在。

在实际开发仓库根目录：

```powershell
# 启动选一个，不同时抢占 UI dev 端口
npm run dev:desktop
npm run dev:web
npm run dev:core

# 必要时构建；这些不是用户验收结果
npm run build:web
npm run build:desktop
npm run build:portable -- --build-only

# 若 uv cache 权限仍阻塞，且现有 venv 含 PyInstaller
.\.venv\Scripts\python.exe scripts\build-portable.py --build-only

# 文档/差异静态检查，不是业务测试
.\.venv\Scripts\python.exe scripts\check-doc-links.py
git diff --check
```

`build:desktop` 已在 package.json 中带 `--debug --no-bundle --features custom-protocol`；不要手拼替代命令。portable 脚本依次冻结 Core、正式 release 构建桌面、复制 `core/` 并 ZIP；`--build-only` 跳过生命周期检查。

认证/bootstrap/runtime 入口：`bootstrap/cli.py`、`bootstrap/reader.py`、`application/runtime.py`、`infrastructure/database.py`；Rust `supervisor.rs`；React `connection.ts`。排查 Core→Supervisor→UI 时区分 `core_ready`、`supervisor_ready`、`ui_ready` 和 shutdown，记录实际启动的 artifact，不泄露 bootstrap secret/bearer/API key。

应用数据保存到 Tauri app-data（identifier 仍为 `app.livingworld.desktop`）；独立 Core/browser 开发 launcher 使用历史 `%LOCALAPPDATA%/LivingWorld/development`。不要把数据库放到源码/安装/便携目录，不因改名自行迁移数据。

相关架构阅读顺序：

1. [CHAT_MODEL.md](docs/architecture/CHAT_MODEL.md) 与 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md) 已确认补充。
2. [PRODUCT_SURFACE.md](docs/architecture/PRODUCT_SURFACE.md)、[PRODUCT.md](PRODUCT.md)、[LLM_PRODUCTION_COMPOSITION.md](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)。
3. 按当前改动选择 [EPISODIC_MEMORY.md](docs/architecture/EPISODIC_MEMORY.md)、[LLM_ROUTING.md](docs/architecture/LLM_ROUTING.md)、[LLM_BUDGET_GUARD.md](docs/architecture/LLM_BUDGET_GUARD.md)、[LLM_ACCOUNTING.md](docs/architecture/LLM_ACCOUNTING.md)、[PERSISTENCE_MODEL.md](docs/architecture/PERSISTENCE_MODEL.md)。
4. 借鉴世界书时查 ADR-0001 中的官方 ST World Info 来源；要引用具体源码/依赖时重新核对项目版本与许可，而不是相信聊天记忆中的“它可以复制”。

## 11. 下一步优先顺序

以下是基于当前缺口的接续建议，不是额外冻结的架构方案；每个新功能仍先调查成熟实现：

1. **接通聊天流式呈现。** 复用已有 provider stream adapter/contracts，先解决 terminal 校验、claim、预算账本、未知 usage 和取消的一致性；半截台词不成为 durable success。同时优先处理用户已复现的验收问题，不替用户运行测试。
2. **完善整轮结束说明。** 目前群聊可显示已保存的逐条发言，但 completed 不能区分自然 STOP、Token 不足和安全条数上限；先形成具体有界持久/接口方案再实现，不能只凭状态猜原因。
3. **评估召回效果和更远历史。** 当前词法原文召回已接线，用户真实长对话反馈到来后再评估噪声、同义词和三页之外历史；优先成熟可控方案，保持授权先于排序。聊天自动形成 EpisodicMemory 的 Observation 证据路径须单独给出具体设计，不改变 C-007A。
4. **改善模型设置和世界书体验。** 复用现有 ModelSetup/registry 和基础 lore 激活；补 route/bounds 说明，未知模型上界不猜。世界书向量、递归、时序和隐藏角色授权先明确范围，不重复已实现的基础关键词能力。
5. **之后再补世界话题生产。** Director 在 batch-plan/reservoir 边界内推进，借助已有 scheduler/Kernel 提交合法事件；群选人器仍独立，hidden facts 不泄漏。
6. **持续提供最新便携产物。** 有可编译业务变更时使用 build-only，明确未验证处；完整验收通过并获用户明确批准后才进行 GitHub push/release。

## 12. 最容易破坏的地方

- `livingworld` 模块、Tauri identifier、storage keys、协议 derivation 和格式后缀是兼容标识，不能搜索替换成 dreamtalk。
- 公开 lore、群消息可见和角色私有 Memory 是三类输入，不能做一个“全世界上下文”查询绕过授权。
- accepted 卡片、runtime Character、Conversation、WorldTruth 是不同生命周期；不能靠导入就创建所有后台角色/事件。
- Input+output 的 Token ceiling 是**整轮**，不是每人/每次调用；重新建 budget 或重置 fallback deadline 会破坏约束。
- Message 的普通幂等保存与模型的不可重领 claim 是不同保护；“重试保存”不能变成“再次请求模型”。
- `LLMResponse` 是非流式完整结果；`TextDelta` 是流式内容；`LLMStreamCompletion` 只含 terminal accounting metadata，不能把整段文本塞回 completion。
- 长期记忆未完成不代表可以读取别人的记忆补齐；历史消息已持久化也不代表每轮都读全量。
- 旧文档的阶段限制、FIX_NOW 描述、独立实现限制需结合后续确认与当前代码，不把已解除的历史条件重新当作阻塞。
- 没跑测试就写“未测试”，只有 build 就写“构建成功”；不要把可执行文件存在、health ready 或旧测试通过说成用户体验已验收。
