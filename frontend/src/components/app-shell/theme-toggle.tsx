import { Moon02Icon, Sun03Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const nextTheme = isDarkTheme ? "light" : "dark";
  const actionLabel = isDarkTheme ? "切换为浅色主题" : "切换为深色主题";

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={actionLabel}
            onClick={() => setTheme(nextTheme)}
          />
        }
      >
        <HugeiconsIcon
          data-icon="inline-start"
          icon={isDarkTheme ? Sun03Icon : Moon02Icon}
          strokeWidth={2}
        />
      </TooltipTrigger>
      <TooltipContent>{actionLabel}</TooltipContent>
    </Tooltip>
  );
}
