import { CoreRequestError } from "@dreamtalk/api-client";

export function contentImportError(failure: unknown): string {
  const suffix = "文件内容尚未保存。";
  if (!(failure instanceof CoreRequestError)) return `无法连接资料服务，请稍后重新选择文件。${suffix}`;
  const field = failure.path ? `（${failure.path}）` : "";
  if (failure.status === 409) return "该内容已更新，请重新打开管理页面并选择最新版本。";
  if (failure.status === 401 || failure.status === 403) return `资料服务连接已失效，请重新打开应用后重试。${suffix}`;
  if (failure.code === "preview_capacity_reached") return `待确认的预览已满，请先完成或取消已有预览，再选择文件。${suffix}`;
  if (failure.code === "character_card_archive_size_limit") return `CHARX 展开总量超过 128 MiB。${suffix}`;
  if (failure.code?.includes("size_limit") || failure.code === "import_too_large") return `文件或解码后的 JSON 超过 32 MiB。${suffix}`;
  if (failure.code?.includes("depth_limit")) return `JSON 嵌套超过 64 层，无法安全读取${field}。${suffix}`;
  if (failure.code?.includes("entry_limit") || failure.code?.includes("chunk_limit") || failure.code === "lorebook_entry_count_limit") return `文件包含的条目或数据块超过 10,000 个。${suffix}`;
  if (failure.code === "character_card_name_not_representable") return `角色名称缺失、为空或不是文本${field}。${suffix}`;
  if (failure.code?.includes("duplicate") || failure.code === "ambiguous_character_card_chunks") return `文件存在重复字段或冲突的角色数据，请核对来源版本${field}。${suffix}`;
  if (failure.code?.includes("unsupported_character_card")) return `暂时无法识别这张卡的格式或版本${field}；支持 V1/V2/V3 JSON、PNG 和 CHARX，以及旧 Pygmalion JSON。${suffix}`;
  if (failure.code?.includes("archive")) return `CHARX 包无法读取，缺少 card.json 或包含不安全的归档结构。${suffix}`;
  if (failure.code?.includes("png") || failure.code?.includes("apng") || failure.code?.includes("base64") || failure.code === "missing_character_card_chunk") return `图片中的角色数据缺失或损坏${field}，请使用原始角色卡文件。${suffix}`;
  if (failure.code?.includes("json")) return `JSON 内容无法解析${field}，请核对原始文件是否完整。${suffix}`;
  if (failure.status === 422) return `文件字段结构无法读取${field}；角色设定等正文应为文本。${suffix}`;
  return `资料服务暂时无法处理文件，请稍后重试。${suffix}`;
}

export function contentImportWarning(code: string): string {
  if (code === "character_card_v2_fallback_review_required") return "PNG 中的 V3 数据无法读取；下面展示的是 V2 数据。请核对，并明确确认使用 V2。";
  if (code === "character_card_book_preserved_only") return "附带世界书无法启用，完整原文已保留；本次只导入可用的角色内容。";
  if (code === "character_card_book_entry_preserved_only") return "这条附带世界书内容无法启用，原文仍保留，其他可用条目可以导入。";
  if (code === "character_card_asset_preserved_only" || code === "character_card_charx_assets_reference_only" || code === "character_card_assets_reference_only") return "附件数据已保留；未提取的图片、音频或其他资源不会自动启用。";
  if (code === "character_card_legacy_converted") return "已按旧版角色卡格式转换，原始文件完整保留。";
  if (code === "character_card_empty_book_normalized") return "空世界书字段已按“未附带世界书”处理。";
  if (code === "character_card_optional_field_preserved") return "附加字段无法完整映射，已保留原文，不影响角色主体导入。";
  if (code === "character_card_unused_chunk_unreadable") return "图片中未采用的另一份角色数据无法读取；本次有效数据和原文件均保留。";
  if (code === "character_card_field_normalized" || code === "character_card_book_field_normalized" || code === "character_card_base64_normalized") return "已兼容处理缺失字段、空值或旧版写法，原始数据仍保留。";
  if (code === "lore_activation_metadata_preserved_inert") return "导入不会执行触发设定；聊天支持范围见各条目说明。";
  if (code.includes("blank_tags")) return "空白标签已从角色标签中省略，原值仍保留。";
  if (code.includes("empty_content")) return "空白条目未启用，原文仍保留。";
  if (code.includes("secondary_keys")) return "含义不明确的次级关键词已保留，未作猜测转换。";
  if (code === "character_card_opaque_extensions") return "酒馆扩展数据已保留，插件脚本和专有功能不会自动执行。";
  return "存在兼容性差异，原始数据仍保留，请核对预览内容。";
}

export function groupImportWarnings(warnings: { code: string; path: string }[]) {
  const groups = new Map<string, { code: string; paths: string[]; count: number }>();
  for (const warning of warnings) {
    let group = groups.get(warning.code);
    if (!group) { group = { code: warning.code, paths: [], count: 0 }; groups.set(warning.code, group); }
    ++group.count;
    if (warning.path) group.paths.push(warning.path);
  }
  return [...groups.values()];
}
