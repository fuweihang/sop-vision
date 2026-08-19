import { QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { Toaster } from "@/components/ui/sonner";
import { queryClient } from "@/lib/query-client";
import { ThemeProvider } from "@/providers/theme-provider";

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        {children}
        <Toaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
