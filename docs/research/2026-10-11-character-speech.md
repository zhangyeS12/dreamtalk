# IndexTTS 2.5 角色配音复用调查

日期：2026-10-11。任务为已批准角色音色卡、角色映射和回复后自动配音；保留 React／Core／Tauri 架构。不增加文字模型调用，不集成其他玩法。

## 来源与选择

| 来源、版本 | 许可／使用边界 | 实际复用及理由 |
| --- | --- | --- |
| [官方 IndexTTS](https://github.com/index-tts/index-tts)、[中文说明](https://github.com/index-tts/index-tts/blob/main/docs/README_zh.md)，2.5（官方记录 2026-08-10 发布） | [Bilibili Model Use License](https://github.com/index-tts/index-tts/blob/main/LICENSE)，不是本仓库 Apache-2.0 | 独立可选进程调用原生 IndexTTS2 推理；不复制原生推理源码、不分发权重，不让无显卡用户承担 Torch／CUDA 依赖 |
| 用户指定的 [官方 Demo](https://huggingface.co/spaces/IndexTeam/IndexTTS-2.5-Demo)、[公开源码](https://huggingface.co/spaces/IndexTeam/IndexTTS-2.5-Demo/raw/main/webui.py) | 官方演示与 Hugging Face 使用规则；免费资源无持续可用保证 | 复用公开 Gradio HTTP 协议，已有 httpx 上传／提交／读取结果；不用浏览器自动点击，不复制 Gradio 或模型源码 |
| [Gradio API](https://huggingface.co/docs/hub/spaces-api-endpoints)、[ZeroGPU 配额](https://huggingface.co/docs/hub/spaces-zerogpu) | 账户额度与 credits 规则随平台变化 | 限匿名或已核实免费个人账户；不发送 PRO Token，避免把“免费”变成 credits 消费 |
| [优云智算 2.5 官方 API](https://www.compshare.cn/docs/minimax-h3/api/text-to-speech-api) | 外部云服务账号／费用由用户承担；不复制服务实现 | 上传参考音频、保存账号音色、一次提交任务、读结果；价格／余额查询、幂等键和 signed URL 传输按其契约。只纳入明确写 2.5 的接口，不把 2.0 服务当成 2.5 |
| [TinyTag](https://github.com/tinytag/tinytag)，固定 2.2.1 | MIT，许可保存在 [本地副本](../licenses/tinytag-2.2.1-LICENSE-MIT.txt) | 纯 Python 读取 WAV／MP3 时长、声道及采样率，不加载图像／文本标签。新增依赖仅此一个；比引入音频推理框架轻，现有 Pillow 不处理音频 |

参考音色以短录音和配置为跨路线载荷，不假设不同平台 voice ID 可互通。平台 ID 只作为当前世界、当前凭据引用和音频 digest 的私有缓存，不进入音色卡。原生参考文本、情感策略并非各接口完全等价；首版不宣称高级参数完整兼容。

## 实际接口核对

只读取官方演示公共配置，没有上传音频或调用 gen_single：当前 Gradio 5.45.0，命名入口 gen_single，26 个输入，前四项为 radio/audio/textbox/dropdown。实现按配置默认值组装、替换参考音频／台词／语言／时长倍率；输入数量或首部类型变化即停止，不猜新参数。时长倍率使用语速的倒数。

本地桥接复用官方原生 infer_v2_5；云端按公开计价字段、snake_case 请求和任务状态读取。任何源码／配置核对都不等于真实模型、额度、账号或网络兼容验收。

## 维护与成本

Core 只增加 TinyTag 和 HTTP 适配，不携带数 GB 的语音模型。数据库增加作者配置、绑定、一次性任务回执、派生音频缓存及云音色映射；与 canonical 事件、知识和聊天记忆分开。

免费演示接口和外部云价格需持续维护。生成提交不自动重试、不更换路线；未知结果保留回执。云音色创建结果未知时，后续相同创建幂等键可能被平台拒绝，需要用户核对平台状态，不能据此盲目补造另一份音色或重发原语音任务。

普通播放只在前台当前聊天运行。音频缓存上限与 Blob URL 释放有明确边界；本地独立模型服务加载后是否保留显存由服务生命周期决定，退出 dreamtalk 不代表自动关闭用户另行启动的模型服务。
