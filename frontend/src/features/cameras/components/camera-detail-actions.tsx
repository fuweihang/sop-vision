import { Edit02Icon, PlayIcon, StopIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { AxiosInstance } from "axios";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { CameraDetail } from "@/features/cameras/api/cameras-api";
import { CameraEditDialog } from "@/features/cameras/components/camera-edit-dialog";
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
  camera,
  apiClient,
  available,
  previewRequested,
  onPreviewRequestedChange,
}: {
  camera: CameraDetail;
  apiClient: AxiosInstance;
  available: boolean;
  previewRequested: boolean;
  onPreviewRequestedChange: (requested: boolean) => void;
}) {
  const editTriggerRef = useRef<HTMLButtonElement>(null);
  const [editing, setEditing] = useState(false);

  return (
    <>
      <CameraPreviewAction
        available={available}
        previewRequested={previewRequested}
        onPreviewRequestedChange={onPreviewRequestedChange}
      />
      <Button
        ref={editTriggerRef}
        type="button"
        variant="outline"
        onClick={() => setEditing(true)}
      >
        <HugeiconsIcon
          icon={Edit02Icon}
          strokeWidth={2}
          data-icon="inline-start"
        />
        编辑摄像头
      </Button>
      {editing ? (
        <CameraEditDialog
          camera={camera}
          apiClient={apiClient}
          onClosed={() => {
            setEditing(false);
            // Dialog 采用外部触发按钮并在关闭后卸载，显式恢复焦点以保持与 Base UI Trigger 一致。
            requestAnimationFrame(() => editTriggerRef.current?.focus());
          }}
        />
      ) : null}
    </>
  );
}
