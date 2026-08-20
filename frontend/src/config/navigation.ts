import { CameraVideoIcon, Task01Icon } from "@hugeicons/core-free-icons";
import type { IconSvgElement } from "@hugeicons/react";

export interface MainNavigationItem {
  label: string;
  icon: IconSvgElement;
  to: "/cameras" | "/tasks";
}

export const mainNavigation = [
  {
    label: "摄像头",
    icon: CameraVideoIcon,
    to: "/cameras",
  },
  {
    label: "检测任务",
    icon: Task01Icon,
    to: "/tasks",
  },
] as const satisfies readonly MainNavigationItem[];
