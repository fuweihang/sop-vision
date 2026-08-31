import { Edit02Icon, PlayIcon, StopIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";

import { Button } from "@/components/ui/button";
interface CameraPreviewActionProps {
  available: boolean;
  previewRequested: boolean;
  onPreviewRequestedChange: (requested: boolean) => void;
}

export function CameraPreviewAction({
  available,
  previewRequested,
  onPreviewRequestedChange,
}: CameraPreviewActionProps) {
  const isStopping = available && previewRequested;

  return (
    <Button
      type="button"
      variant="outline"
      disabled={!available}
      onClick={() => onPreviewRequestedChange(!previewRequested)}
    >
      <HugeiconsIcon
        icon={isStopping ? StopIcon : PlayIcon}
        strokeWidth={2}
        data-icon="inline-start"
      />
      {isStopping ? "停止预览" : "开始预览"}
    </Button>
  );
}

export function CameraDetailActions({
  available,
  previewRequested,
  onPreviewRequestedChange,
}: {
  available: boolean;
  previewRequested: boolean;
  onPreviewRequestedChange: (requested: boolean) => void;
}) {
  return (
    <>
      <span id="camera-detail-placeholder-actions" className="sr-only">
        编辑摄像头功能暂未实现
      </span>
      <CameraPreviewAction
        available={available}
        previewRequested={previewRequested}
        onPreviewRequestedChange={onPreviewRequestedChange}
      />
      <Button
        type="button"
        variant="outline"
        disabled
        aria-describedby="camera-detail-placeholder-actions"
      >
        <HugeiconsIcon
          icon={Edit02Icon}
          strokeWidth={2}
          data-icon="inline-start"
        />
        编辑摄像头
      </Button>
    </>
  );
}
