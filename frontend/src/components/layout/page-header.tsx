import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps extends Omit<
  ComponentProps<"header">,
  "title"
> {
  title: string;
  description: string;
  actions?: ReactNode;
  /** 页面可以在窄屏调整操作组对齐方式，不需要复制 PageHeader 结构。 */
  actionsClassName?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  actionsClassName,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
      {...props}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h1
          data-route-focus
          tabIndex={-1}
          className="text-2xl font-semibold tracking-tight text-balance wrap-break-word"
        >
          {title}
        </h1>
        <p className="text-muted-foreground text-sm text-pretty">
          {description}
        </p>
      </div>
      {actions === undefined || actions === null ? null : (
        <div
          className={cn(
            "flex shrink-0 flex-wrap items-center gap-2",
            actionsClassName,
          )}
        >
          {actions}
        </div>
      )}
    </header>
  );
}
