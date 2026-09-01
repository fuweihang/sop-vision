import { useEffect, useId } from "react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CameraSourceDetail } from "@/features/cameras/api/cameras-api";
import { isCameraSourcePlayable } from "@/features/cameras/components/camera-preview-selection";
import { useVideoControlsVisibility } from "@/features/video/components/video-controls";
import { useVideoSurface } from "@/features/video/components/video-surface";

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
  const selectedSourceName = sources.find(
    (source) => source.source_id === sourceId,
  )?.name;

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
        className="
          w-fit max-w-36 overflow-hidden sm:max-w-48
          **:data-[slot=select-value]:block
          **:data-[slot=select-value]:min-w-0
          **:data-[slot=select-value]:truncate
          [&>svg]:shrink-0
        "
      >
        <SelectValue title={selectedSourceName} />
      </SelectTrigger>
      <SelectContent
        portalContainer={containerElement}
        side="top"
        align="end"
        alignItemWithTrigger={false}
        className="max-w-(--available-width)"
      >
        <SelectGroup>
          {sources.map((source) => (
            <SelectItem
              key={source.source_id}
              value={source.source_id}
              disabled={!isCameraSourcePlayable(source)}
              className="
                min-w-0 overflow-hidden
                [&>div]:min-w-0
                [&>div]:shrink
                [&>div]:overflow-hidden
              "
            >
              {/* Base UI 的 ItemText 默认禁止收缩，因此由 SelectItem 局部覆盖直接子 div；
                  不修改共享 Select，也能让任意长度的中英文名称在当前弹层宽度内单行省略。 */}
              <span className="min-w-0 flex-1 truncate" title={source.name}>
                {source.name}
              </span>
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
