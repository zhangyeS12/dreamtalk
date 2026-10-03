# 2026-10-03 Windows原生库导入卡顿：证据与复用

## 成熟工具

临时安装[py-spy0.4.1](https://github.com/benfred/py-spy)到可写的独立诊断目录；只用dump --pid --json，不使用--locals，未对进程注入代码或保存内存转储。它读取当前Python线程调用位置，不需要重启用户程序。工具不进入项目依赖或便携包，许可以临时wheel原始许可证为准。

## 确认与推断

现场主线程停在ThreadPoolExecutor.submit/start等待；另一个线程在semantic_chat_retrieval._decode/_historical导入NumPy multiarray原生扩展，桌面host-control线程正读stdin。新版路径已由Get-Process.Path确认，不带凭据的本地存活接口4秒超时，不读主存档或密钥。启动后没有继续增长的CPU也与等待一致。

[NumPy问题#24290](https://github.com/numpy/numpy/issues/24290)给出了Windows子进程读stdin与首次NumPy导入并存时永久卡住的复现条件。本项目采用同样的stdin管道结构，现场也停在首次导入，因此优先去除该条件；上游旧环境并不是对本机NumPy2.5.3/CPython3.13.7内部锁的直接验证。[#24833](https://github.com/numpy/numpy/issues/24833)讨论的是子解释器，当前应用没有子解释器，不把它作为本次根因。

## 最小修复

沿现有标准库/NumPy/FastEmbed流程，在Core首次准备数据库/工作线程及stdin监听之前完成原生库导入；模型权重和向量缓存仍按需使用。失败明确记录并仅回退关键词，不在运行期重复失败的原生导入。不替换库、不新增进程服务、不改变Kernel或历史权限。保留线程超时作为慢推理的降级措施，但不再把它当作能救活同步堵塞主线程的保障。

本次仅授权的临时诊断可以验证启动顺序与本地响应；真实聊天和历史记忆仍由用户验收，不增加模型测试费用。
