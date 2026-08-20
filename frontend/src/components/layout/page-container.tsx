import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function PageContainer({ className, ...props }: ComponentProps<"main">) {
  return (
    <main
      className={cn("flex min-w-0 flex-col gap-6 p-4 md:p-6", className)}
      {...props}
    />
  );
}
