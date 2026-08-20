import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps extends Omit<
  ComponentProps<"header">,
  "title"
> {
  title: string;
  description: string;
  actions?: ReactNode;
}

export function PageHeader({
  title,
  description,
  actions,
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
        <h1 className="text-2xl font-semibold tracking-tight text-balance break-words">
          {title}
        </h1>
        <p className="text-muted-foreground text-sm text-pretty">
          {description}
        </p>
      </div>
      {actions === undefined || actions === null ? null : (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      )}
    </header>
  );
}
