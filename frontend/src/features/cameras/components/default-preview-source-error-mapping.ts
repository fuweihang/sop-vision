import { classifyCameraWriteFailure } from "@/features/cameras/api/camera-write-failure";

export interface DefaultPreviewSourceFeedback {
  readonly kind: "error" | "unknown";
  readonly title: string;
  readonly message: string;
}

/** 默认源单选只显示固定中文提示，不转发服务端 detail 或字段内容。 */
export function mapDefaultPreviewSourceFailure(
  error: unknown,
): DefaultPreviewSourceFeedback {
  const classification = classifyCameraWriteFailure(error);

  if (classification.kind === "unknown") {
    return {
      kind: "unknown",
      title: "默认源设置结果未知",
      message:
        "服务端可能已经保存了选择，正在重新读取摄像头详情；读取完成前不会显示未经确认的新默认源。",
    };
  }

  if (classification.kind === "camera-not-found") {
    return {
      kind: "error",
      title: "未能设置默认预览源",
      message: "该摄像头不存在或已被删除。",
    };
  }

  if (classification.kind === "validation") {
    return {
      kind: "error",
      title: "未能设置默认预览源",
      message: "该视频源已不存在或不属于当前摄像头，请刷新后重试。",
    };
  }

  return {
    kind: "error",
    title: "未能设置默认预览源",
    message: "当前摄像头配置无效，请联系管理员检查服务端数据。",
  };
}
