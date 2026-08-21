import { CameraVideoIcon, Task01Icon } from "@hugeicons/core-free-icons";
import { linkOptions } from "@tanstack/react-router";

export const mainNavigation = [
  {
    label: "摄像头",
    icon: CameraVideoIcon,
    linkOptions: linkOptions({ to: "/cameras" }),
  },
  {
    label: "检测任务",
    icon: Task01Icon,
    linkOptions: linkOptions({ to: "/tasks" }),
  },
] as const;
