# 本地三面封面：成熟实现与接入决定（2026-10-03）

用户确认0.1.12书架效果后，批准两种封面：文字标题同步正面/书脊；正面/书脊/背面本地图片上传、比例裁剪、立体预览及保存，保留正面左上角dreamtalk。正面必选、其余可选；图片标题可关闭。封面标题与真实世界名分开，原图和裁剪参数留在本机。

## 采用的成熟实现

- [react-easy-crop 6.2.3](https://github.com/ValentinH/react-easy-crop/tree/v6.2.3)：精确锁定6.2.3，React/ReactDOM声明兼容>=16.4，现有React19可用。拖动、滚轮、触控、缩放和键盘移动直接使用组件；比例通过aspect，恢复通过initialCroppedAreaPercentages。保存百分比避免像素整数舍入累积。独立固定尺寸裁剪区，无弹窗缩放入场；disableAutomaticStylesInjection加显式CSS导入，沿用既有CSP。本地许可[MIT](../licenses/react-easy-crop-6.2.3-LICENSE.txt)与transitive normalize-wheel1.0.1的[BSD原始许可](../licenses/normalize-wheel-1.0.1-LICENSE.txt)随包分发。
- [Pillow 12.3.0 Image模块](https://pillow.readthedocs.io/en/stable/reference/Image.html)：精确锁定12.3.0。现有Core依赖无图片解码/重采样实现，因此使用Pillow的格式限定、verify、EXIF方向、rotate、LANCZOS resize与WebP编码；不写图像编解码器。完整wheel[MIT-CMU及随附codec许可](../licenses/Pillow-12.3.0-LICENSE.txt)原样保存，PyInstaller自带PIL hook收集JPEG/PNG/WebP支持，并包含pillow元数据。
- [Tauri Windows dragDropEnabled](https://v2.tauri.app/reference/config/#windowconfig)：官方明确Windows需禁用原生drag-drop handler才能使用HTML5文件拖放。本版main窗口设置false，上传交给浏览器File/Input/DragEvent，维持文件选择入口，不新增任意路径读取权限。img-src加入blob:以展示受认证读取的本地图片，session token不进入URL。
- [FilePond插件](https://pqina.nl/filepond/plugins/)与[Cropper.js](https://fengyuanchen.github.io/cropperjs/)用于比较；本需求每次编辑一面，现有input加drop区域够用，react-easy-crop已覆盖交互，不引入完整上传框架、商业编辑器或另一个渲染栈。

Canvas只把成熟组件返回的选区绘制成内存预览，不承担手势或存储。正式展示图由Core重新解码原图并按同一百分比/90度旋转生成，后台不会信任前端上传的展示图或文件名。

## 本地存储与范围

复用现有FileContentAssetStore不可变SHA256资产、大小/哈希核对及排除符号链接/目录联接的路径规则，不另建任意文件服务。原图和WebP展示图共用content-assets目录。新增world_covers（展示JSON、revision）及world_cover_images（世界作用域、digest/size/type/dimensions），0030仅追加表；历史0029和更早的shape显式保留。

封面元数据不进入canonical命令、事件、authored lore/package/replay或模型上下文。所有HTTP走既有Bearer认证；图片只能通过该世界已登记的摘要读取，不能凭另一个世界或其他内容的hash读取文件。原图每张<=10MiB，<=20MP，边长<=10000，动画拒绝；按真实解码格式核对，百分比有限、有界且保留目标比例。单次只执行一项解码处理，异步线程不阻塞世界调度。

保存沿用乐观revision的CAS，不覆盖其他窗口修改。丢失响应只读核对revision、模式/标题及三面来源/裁剪，不自动重写。原图/参数重读后可再编辑；取消只放弃展示草稿，不更新正式封面。哈希文件暂不自动清理，不删除潜在共享资产；后续可在明确引用计数和存档备份规则后增加本地素材清理。

## 验证边界

只做静态源码/Git diff、ESLint/TypeScript、Ruff/AST、必要release编译与打包文件哈希。使用现有build-portable.py --build-only，新增--output-name生成全新完整目录、保留旧包，不运行内嵌烟测。用户明确保留测试与验收责任，因此未改动/运行既有测试，未启动GUI/应用/浏览器、读写真实存档/凭据/自启动，未调用模型。实际裁剪和重启保存需用户验收，不能以成功编译代替。
