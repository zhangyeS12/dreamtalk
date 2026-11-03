import { CoreRequestError } from "@dreamtalk/api-client";
import { contentImportError } from "../../contentImportFeedback";
export function libraryFailure(error: unknown) {
  if (error instanceof CoreRequestError) {
    if (error.code === "card_share_version_unsupported") return "这张完整角色卡使用了当前版本尚不支持的格式，请更新 dreamtalk 后再导入。";
    if (error.code === "card_share_size_limit") return "完整角色卡超过32 MiB上限。请使用较小的卡面原图后再分享。";
    if (error.code?.startsWith("card_share_")) return "完整角色卡文件不完整或内容无法核对，请向分享者重新获取原始 CHARX 文件。";
    if (error.code === "card_library_already_added") return "这张卡已经加入这个世界，可在世界内的通讯录查看。";
    if (error.code === "card_library_location_pending") return "角色内容已加入，但初始地点尚未设置成功。可保持“无”后再次确认，或检查所选地点；不会重复添加。";
    if (error.status === 409) return "资料已被其他编辑更新。当前草稿保留，请关闭并重新读取后核对。";
    if (error.code?.includes("preview_expired")) return "预览已过期，请返回重新预览。";
    if (error.code === "preview_capacity_reached") return "请先完成或取消另一个资料预览，再进行此操作。";
    if (error.status === 413 || error.status === 422) return contentImportError(error).replaceAll("当前世界", "卡库");
  }
  return "操作结果暂未确认。当前草稿保留，可再次确认核对同一次请求，或重新读取已保存内容。";
}
