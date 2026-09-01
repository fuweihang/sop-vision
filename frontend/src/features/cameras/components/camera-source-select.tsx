import { useEffect, useId } from "react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CameraDetail } from "@/features/cameras/api/cameras-api";
import { isCameraSourcePlayable } from "@/features/cameras/components/camera-preview-selection";
import { useVideoControlsVisibility } from "@/features/video/components/video-controls";
import { useVideoSurface } from "@/features/video/components/video-surface";

type CameraSourceDetail = CameraDetail["sources"][number];

interface CameraSourceSelectProps {
  sources: CameraSourceDetail[];
  sourceId: string;
  onSourceChange: (sourceId: string) => void;
}

/** Camera 专用临时 Source 选择器；只改变当前页面状态，不调用默认源修改接口。 */
export function CameraSourceSelect({
  sources,
  sourceId,
  onSourceChange,
}: CameraSourceSelectProps) {
  const layerId = useId();
  const {
    actions: { setFloatingLayerOpen },
  } = useVideoControlsVisibility();
  const {
    meta: { containerElement },
  } = useVideoSurface();
  const items = sources.map((source) => ({
    label: source.name,
    value: source.source_id,
  }));

  useEffect(
    () => () => setFloatingLayerOpen(layerId, false),
    [layerId, setFloatingLayerOpen],
  );

  return (
    <Select
      items={items}
      value={sourceId}
      onValueChange={(value) => {
        if (value !== null) {
          onSourceChange(value);
        }
      }}
      onOpenChange={(open) => setFloatingLayerOpen(layerId, open)}
      modal={false}
    >
      <SelectTrigger
        aria-label="切换预览源"
        size="sm"
        variant="overlay"
        className="max-w-36 sm:max-w-48"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent
        portalContainer={containerElement}
        side="top"
        align="end"
        alignItemWithTrigger={false}
      >
        <SelectGroup>
          {sources.map((source) => (
            <SelectItem
              key={source.source_id}
              value={source.source_id}
              disabled={!isCameraSourcePlayable(source)}
            >
              <span className="min-w-0 flex-1 truncate">{source.name}</span>
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
