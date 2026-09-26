# Production LLM Composition — C-005E5

状态：Stage 4 的 provider-neutral contracts、四个协议 adapter、retry、routing、accounting、pricing、budget 与桌面凭据边界已经接入一个生产 composition root。启动和确定性测试不访问 provider 网络，也不验证凭据有效性。

## 1. 最终运行图

```text
Tauri Rust host
├── CoreSupervisor
├── keyring-backed NativeCredentialStore
└── bounded, one-way stdin control channel
        ↓
Python Core bootstrap
└── ProductionLLMRuntime
    ├── SessionCredentialProvider
    ├── four configured single-attempt adapters
    ├── ModelRegistry + RoutingConfiguration
    ├── RetryPolicy + shared route deadline
    ├── PricingCatalog + UsageBounder
    ├── SqlAlchemyBudgetGuard + AccountingRepository
    └── RoutedModelGateway
```

[llm_runtime.py](../../services/core/src/livingworld/bootstrap/llm_runtime.py) 是唯一生产组装入口。它按显式 `AdapterKind` 创建 OpenAI-compatible Chat Completions、Anthropic Messages、Gemini Interactions 和 OpenAI Responses adapter。应用层只得到受治理的 `RoutedModelGateway`；没有直接快速调用 provider 的分支。每个已启用 ModelRef 的 adapter/client 在启动时创建一次，由 `ProductionLLMRuntime` 持有并在 Core 关闭时 `aclose()`。凭据在每次 provider request 前按 `SecretRef` 解析，不写入 HTTP client 默认 headers。

## 2. 非秘密配置 v1

桌面配置路径为 app-data `config/llm.json`，格式版本为 `1`。它是不可变的进程级 operational snapshot；C-005E5 不监视文件，也不把配置写入 WorldEvent、WorldTruth、Knowledge、Content、Memory 或 `.lwcontent`。

| 字段 | 含义 |
| --- | --- |
| `version` | 必须为 `1` |
| `providers` | ProviderId、AdapterKind、可选 base URL、SecretRef、timeout；不含密钥 |
| `models` | exact ModelRef、enabled、能力、可信 usage limits、adapter profile、可选 pricing envelope |
| `routes` | purpose 可选覆盖、FAST/BALANCED/BEST、确定候选顺序、允许的 fallback 类别 |
| `execution_policy` | bounded attempts、backoff、共享 elapsed deadline、typed retry switches |
| `pricing_catalog` | source-labelled effective-dated schedules、rates、aliases；价格是 Decimal data |

解析器拒绝重复 JSON key、秘密字段名、未知字段/adapter、重复身份、悬空或 disabled route、capability/profile 不一致、无效 limits/SecretRef/retry/pricing reference。诊断只返回固定错误码，不回显被拒绝的内容。model id 是 opaque string；组装和路由不搜索 `gpt`、`claude`、`gemini` 或其他名称片段。空配置合法，对应 `UNCONFIGURED`。结构损坏使 LLM 子系统为 `DEGRADED`，不会阻止 World/content/database Core 启动，也不会触发 provider 调用。

## 3. 桌面凭据边界

Rust 使用 `keyring` 4.2 的 v1 API，通过 target-native backend 访问 Windows Credential Manager、macOS Keychain 或 Linux Secret Service/keyring。service namespace 固定为 `LivingWorld`，account identity 是 canonical lowercase UUID `SecretRef`。没有 Stronghold、shell command 或 JSON/TOML/SQLite/`.env` fallback。native store 不可用时返回 `secure_storage_unavailable`；不会降级为明文文件。

Tauri 只公开：

- `credential_put(secret_ref, secret)`
- `credential_status(secret_ref)` → `configured | missing | secure_store_unavailable`
- `credential_delete(secret_ref)`

没有返回明文的 `getSecret` command。`resolve` 只供 Rust supervisor 内部启动/重启 provisioning。开发和确定性测试显式注入 `MemoryCredentialStore`；Python 仅认识 provider-neutral `SessionCredentialProvider`，不知道 OS keychain。Headless 部署若未来需要环境或外部 secret manager，必须显式提供另一实现，不能自动落入桌面或测试模式。

## 4. Rust → Python 私有控制协议

sidecar stdin 保留为 Tauri host 到 Python Core 的单向 privileged channel。它不是 WebView IPC、shell、通用 RPC、SQL 或文件操作接口。共享的 [host_control_contract.json](../../services/core/src/livingworld/bootstrap/host_control_contract.json) 定义：

```text
4-byte unsigned big-endian JSON byte length
bounded JSON body (maximum 8192 bytes)
protocol version = 1
message = credential_upsert | credential_remove | credential_sync_complete
SecretRef maximum = 36 UTF-8 bytes
secret maximum = 4096 UTF-8 bytes
```

消息采用 exact-field validation。未知 type、额外字段、非法 UUID、截断、无效 UTF-8/JSON 与过大 frame 均 fail closed；日志只记录固定 protocol event，不记录 frame/body。CLI 参数、环境、bootstrap、ready、URL 和 stdout 都不携带 API key。Python 从 unbuffered OS pipe 读取；Rust 在 shutdown 前先关闭 writer，Core 有 bounded listener join，避免解释器退出时与 buffered reader 竞态。

## 5. 启动、状态、rotation 与删除

```text
host validates safe config envelope
→ spawn Core with config path only
→ bootstrap/ready/authenticated health
→ host resolves configured SecretRefs
→ credential_upsert for values that exist
→ credential_sync_complete
→ authenticated health reports final LLM state
```

`/system/health.llm_status` 是 `ready | partially_configured | unconfigured | degraded`。缺某个 key 只令对应 candidate 本地不可用；explicit ModelRef 不会偷换模型，profile route 也只有显式允许 `candidate_unavailable` 才可继续。missing credential 在 budget/accounting START 和 provider network 前失败。

rotation 先写 native store，再替换 Core session value；已 dispatch request 不改变。删除先移除 native copy，再移除 Core session value；若控制 channel 不能确认删除，host 终止该 Core session，避免继续使用旧值。历史 accounting 不删除。Core restart 丢失全部 Python session values，由 supervisor 从 native store 重新 provision；秘密不在 Python 持久化。这里保证最小持有期、无持久化/日志/无关序列化，不声称 Python RAM 可完美擦除。

## 6. 网络、费用与可选 smoke

启动不进行 model discovery、key test 或 generation。每次 routed call 都经过 registry → route → candidate-local retry → fresh budget admission/reservation + accounting START → adapter → accounting FINAL/settlement。PricingCatalog 是配置数据；缺可信价格时 ordinary policy 可按既有规则执行，而 HARD monetary admission fail closed。

[live-llm-smoke.py](../../scripts/live-llm-smoke.py) 与 pytest/CI 分离。它必须同时获得 `--enable-live-provider`、exact provider/model、config/data-dir 和显式 credential environment variable name；输出最多 512 个 response characters，max output 限制为 1–64，并明确警告可能产生外部费用。仅仅设置环境变量不会启用网络。C-005E5 没有运行该脚本。

## 7. 首次聊天模型设置

桌面“设置 → 聊天模型”在配置仍为空且 Core 报告 `unconfigured` 时，允许明确选择四种已支持的 adapter 之一、填写 exact model ID、必要的兼容服务地址、API key，以及由用户核对的单次输入计费与输出 Token 上界。高级 Token 参数默认折叠，但缺少可信上界时不能保存。这个入口只建立一条可用聊天模型配置，不进行模型发现、凭据试用或有费用的调用；浏览器开发入口只读。已有配置不由该入口覆盖。

Rust 将 key 写入 native credential store，将不含 key 的 v1 配置原子写入 app-data `config/llm.json`，随后重启 Core 并以 authenticated health 确认 `ready`。如果重启或加载失败，恢复原配置并重启原 Core；恢复失败则报告固定错误码。页面成功后重新连接 Core。用户填写的 usage limits 是显式配置，不是应用推测的 provider 事实；选择与核实相应模型的可信上界仍是配置者责任。该流程未配置价格，因此需要可信价格的 HARD 金额预算仍会拒绝无可验证定价的调用。

## 8. 范围与迁移

首次设置以外的模型编辑/轮换 UI、online discovery/pricing、tool/vision/audio 不在本入口范围内。LLM operational configuration/credentials 不进入 canonical world/content state。C-005E5 本身未新增表；其 Alembic head 为 `0010_llm_budget_guard`。
