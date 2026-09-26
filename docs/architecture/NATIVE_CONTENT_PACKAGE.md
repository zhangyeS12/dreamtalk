# dreamtalk Content Package — C-004D2

**`.lwcontent` = portable authored content。`.lworld` = reserved future runtime-world/state package。**

```text
content package != backup
content package != running world
hash integrity != publisher authentication
filesystem blobs + SQLite != one ACID transaction
```

## 1. 边界与版本

集中定义：[content_packages.py](../../services/core/src/livingworld/application/content_packages.py)。`LWCONTENT_PACKAGE_FORMAT=1`、identity=`livingworld.content.package`；版本轴独立于 `LIVINGWORLD_CONTENT_VERSION`、`api_protocol`、Alembic cursor 与未来 `.lworld` format。typed PackageId 是独立 UUID，不决定 contained canonical IDs。

包可以包含 CharacterDefinition、WorldContent、LoreCollection、owned LoreEntry、canonical bindings、ContentAsset 元数据、本地 blob 和 RawImportEnvelope 来源。它不读取/包含 Runtime World、WorldClock、WorldEvent、CommandReceipt、Player/Presence、CharacterState、Relationship、Truth/Belief/PlayerKnowledge、Observation、runtime memory、Director plan、环境配置或凭证。内容不实例化运行角色/世界，不授予知识，不执行作者指令、模板、regex 或资产。

## 2. ZIP 布局与 manifest

物理容器是 ZIP；当前 writer 使用 stored regular entries。reader 接受 regular files/directories 的非分卷 ZIP stored/deflated；不支持 ZIP64 end records、加密及其他压缩编码。entry ordering 不影响正确性，directory entries 不承载成员语义。

```text
manifest.json
content/characters/<CharacterDefinitionId>.json
content/worlds/<WorldContentId>.json
content/lore_collections/<LoreCollectionId>.json
content/lore/<LoreEntryId>.json
assets/sha256/<digest>
sources/<RawImportId>/original
```

writer 生成上述安全名称；reader 使用 manifest 的 typed identity/path，不能从 ZIP filename 猜 ID/type。不同 typed kinds 即使有相同 UUID 也保持独立。shared canonical 对象仅一个 member；同 digest 的资产 bytes 仅一个 ZIP entry。

manifest v1 字段：

| 字段 | 定义 |
| --- | --- |
| format / format_version | 格式身份与独立包版本 |
| package_id / created_at_utc | 调用方提供的 typed UUID、aware time 归一化 UTC；不采样系统时间 |
| canonical_content_version | 当前 supported min=max=1，由集中 canonical version 常量产生 |
| roots | 显式选择的 kind/id；不是全库自动导出 |
| members | kind、typed canonical id、revision、semantic_hash、path、size、SHA-256 |
| assets | 完整 canonical ContentAsset metadata；optional blob 的 digest/size/package path；media type 来自 metadata |
| sources | RawImportId、provenance、unknown_extensions、原 bytes 的 path/size/SHA-256 |
| bindings | 从 canonical references 推导的内容关系，导入时必须完全一致 |
| integrity | SHA-256 algorithm 与确定性 semantic package hash |

canonical roots 复用 [serialization.py](../../services/core/src/livingworld/domain/content/serialization.py)，没有 ORM/第二套 root JSON。member bytes 必须与 canonical serialization 一致。Asset/source metadata 复用同一 canonical 编码和解码规则。manifest 不存本地绝对路径或非 canonical DB row ID；可识别的 local path 引用返回 typed compatibility error，不能为便携性悄悄改写 canonical 内容。

## 3. 依赖闭包

[PackageService](../../services/core/src/livingworld/application/package_service.py) 接收 caller-selected roots，通过 content repository 读取 canonical dependencies；不访问运行世界 store。

```text
CharacterDefinition / WorldContent
→ lore_collection_ids → LoreCollection → owned LoreEntries
→ direct lore_entry_ids → entry owner collection → its members
→ AssetReferences → metadata / approved hash blobs
→ provenance / asset raw reference → source artifacts
```

WorldContent 增加 typed lore_collection_ids，与 CharacterDefinition 校验一致；既有 direct-entry references 原样保留，可共存。旧 WorldContent 缺字段表示空引用，空集合仍省略编码，旧 JSON/hash 不重写。

所有 referenced canonical dependencies 必须包含；v1 不实现 external/unresolved reference 模式。缺失引用是 typed error，不 silently drop。集合/条目 owner 与成员精确一致，shared dependencies 按 typed ID 去重；不 include 无关库内容。legacy unbound entry 无法 safely portable 时返回 `legacy_unbound_lore_not_portable`，不造集合，不 re-home。

## 4. 资产与原始来源

ContentAsset 保持不可变引用/元数据；新 [ContentAssetStore](../../services/core/src/livingworld/infrastructure/packages/asset_store.py) port/adapter 存放显式提供、已校验的 immutable bytes：app-data `content-assets/sha256/<prefix>/<digest>`，身份不是 original filename。当前 blob binding 以 ContentAssetId 关联 digest/size；同 digest 多 ID 复用同一个文件，不同 bytes 不同 hash。

临时 bytes 在该 store staging 目录写完、flush/fsync，再通过 exclusive hard link 发布完整 regular file并移除 staging link；已经存在的 blob 重新验证，绝不覆盖/自动修复损坏文件。数据目录不在 source tree，受控路径链拒绝 symlink/junction。app 层只处理 bytes/digest/typed ID，不操作 OS path。现有 bootstrap 的 app-data composition 继续沿用。

export 只读 selected graph 的本地 blob bindings；引用远端资产仍是 metadata/reference-only warning，不 HTTP fetch、不读 source URI、不解码 data URL/PNG、不自动物化卡片资产。import 对 included bytes 实算 SHA-256，先物化，提交之后 DB binding 才使其语义可达。

sources 仅通过 content repository 读取 selected graph 的 RawImportEnvelope，保留 original bytes/provenance/未知外部数据。当前明确注册 portable authored-source families：CCv2、CCv3、ST World Info；其他分类明确失败，不能把 runtime log/config/私密素材作为通用 filesystem source。没有 arbitrary path reader。完整 raw source 是不可信证据，不覆盖 canonical。当前 graph 的 raw provenance 依赖要求包含来源，不支持剥离来源后伪装其 provenance。

## 5. 三方冲突与 accepted baseline

[Package repository](../../services/core/src/livingworld/infrastructure/persistence/package_repository.py) 保存 local AcceptedImportBaseline：unique `(content_kind,content_id)`、accepted_semantic_hash、accepted_at_utc，以及 optional source_package_id/hash。这是本地 import/conflict evidence，非 canonical authored content、ContentRevision、编辑历史或 runtime state；不参加 canonical hash，不导出。

L=local hash，I=incoming hash，B=accepted baseline：

| 条件 | Preview state |
| --- | --- |
| local missing | NEW |
| L == I | IDENTICAL |
| no B，L != I | DIFFERENT_NO_BASELINE |
| L != B，I == B | LOCAL_MODIFIED |
| L == B，I != B | INCOMING_DIFFERENT |
| L != B，I != B，L != I | DIVERGED |

hash 沿用现有完整 canonical snapshot 语义，包含 typed kind/id、revision 和 provenance；revision 大小不选择 winner。

非 NEW/IDENTICAL 成员必须显式 `KEEP_LOCAL` 或 `REPLACE_WITH_INCOMING`；没有默认覆盖/merge/changed-ID duplicate。IMPORT_AS_COPY 未实现。

NEW 和经过 reviewed Preview Commit 接受的 IDENTICAL 建立/刷新 baseline；REPLACE 使用 incoming committed hash 更新 baseline；KEEP_LOCAL 完全保留原 baseline。KEPT 内容的实际 dependencies 仍需有效，mixed decisions 破坏闭包/归属时明确失败。RawImportId/ContentAssetId/blob binding 只允许同 ID exact reuse，不覆盖不同证据。替换不得重指定 entry ownership 或隐式删除旧 owned members；不支持这种 destructive normalization，整批失败。

native acceptance 是专用 snapshot operation：保留 imported revisions，包括新库非零 revision 或显式接受较低 revision；不伪装成日常编辑。日常 ContentService.save 继续要求 absent/revision=0 或 exact next revision。Preview 同时绑定 package、local snapshot 与 baseline，DB transaction 中重读检查；stale Preview 明确失败，不自动 retry。

## 6. 导入与提交

```text
bytes → container security → manifest/version → member integrity
→ canonical serialization/graph → local conflict analysis → Draft/Preview
→ reviewed hash + explicit decisions → verified asset materialization
→ one content/binding/accepted-baseline SQLite transaction
```

Preview 提供 summary（package format/id、content counts/types、assets/sources 数量、unresolved refs、实际 archive/uncompressed size），以及独立的 warnings 和六种 conflict state。严格闭包时 unresolved refs 为空。解析与 Preview 不写 DB/资产。

所有 canonical DB 内容、blob bindings、被接受的 baseline 更新共享同一 BEGIN IMMEDIATE transaction；失败全部 rollback。资产 bytes 与 SQLite 不具备跨文件系统 ACID：DB 失败后可留下不可达 immutable orphan blob，不使内容可见，不留下 missing-file binding。future garbage collection deferred。没有 runtime WorldEvent/CommandReceipt。

export 返回 bytes、PackageDraft、只读 summary（identity/version/member counts 和实际 archive size）、warnings、semantic hash、`.lwcontent` 与 `application/vnd.livingworld.content+zip`。未记录 container read statistics 的 export draft 不声称 uncompressed size，summary 中为 null；解析后 Preview 提供实际值。不写用户自选文件路径，没有 save dialog/UI。

## 7. ZIP 与完整性防护

[LwContentAdapter](../../services/core/src/livingworld/infrastructure/packages/lwcontent.py) 在 ZipFile 分配 member list 前核对 central-directory 实际记录数，随后同时核验元数据与 bounded streaming：

- POSIX package paths，拒绝 absolute、drive/UNC、backslash、NUL、空 segment、`.`/`..`；原始未被 ZipInfo NUL 截断的名称也检查。
- duplicate normalized paths（含 manifest、file/directory collision）hard failure，不 last-wins。
- 只 regular file/directory；symlink/device/FIFO/socket、加密/unsupported encoding 拒绝；不 extract/extractall。
- exactly one manifest；所有 files 必须被 manifest 使用，缺失/额外歧义文件拒绝；重复 content member path 拒绝。
- PackageLimits 集中 defaults：10,000 entries、4 MiB manifest、32 MiB single entry、256 MiB total/physical archive、200 compression ratio、JSON depth 64、64 KiB read chunks。均是可配置资源策略，不是不可变格式常量。
- manifest/member strict UTF-8 JSON、duplicate keys/nonfinite values/未知 canonical fields 拒绝；newer format 在 v1 shape interpretation 前明确 unsupported，不部分导入。
- 每个 member/blob/source 读取实算 SHA-256，并核对 descriptor size；canonical semantic hash、bindings 与 package semantic hash 再校验。

manifest 不 hash 自己。semantic package hash 来源为独立确定性 input：format/content version、PackageId/UTC time、排序 selected root identities、ContentDraft.preview_hash 与排序 blob identity/hash/size。它覆盖 authored data/provenance/来源 hash/asset metadata；排除 ZIP order/timestamps、transport size 与 local baseline。相同 content/options/bytes 产生同 manifest/member JSON/hash；不承诺跨工具/版本 binary ZIP reproducibility。

SHA-256 是完整性校验，**不是 publisher authentication**。可重算 hash 的发送者仍不可信；签名、PKI、publisher trust 留待后续。

## 8. 验证与 deferred scope

测试：[native package/Stage 3](../../tests/application/test_native_content_package.py)、[migration/blob store](../../tests/persistence/test_package_persistence.py)、[architecture](../../tests/core/test_architecture.py)。覆盖 native/external/native/external/ST round-trip、restart、shared closure、六种冲突、exact no-op、baseline rules、stale Preview、资产/DB failure、orphan semantics、攻击 ZIP、metadata/stream limits、来源与 canary 隔离。

Alembic [0008](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0008_native_content_packages.py) 只增加两个本地表，不存 ZIP structure，不改旧 canonical JSON/hash/rows、runtime schema、ledger/audit。详见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。没有新依赖、GUI smoke 或 network download。

未实现内容运行实例化、automatic Lore→Truth/Belief、activation、prompt assembly、Memory/RAG、Director/Agent/LLM/Builder、checkpoint/branch、`.lworld`、backup、cloud/marketplace、final UI。Stage 4 未开始。总验收见 [STAGE_3_ACCEPTANCE.md](STAGE_3_ACCEPTANCE.md)。
