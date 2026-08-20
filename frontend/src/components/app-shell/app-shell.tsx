import { Outlet } from "@tanstack/react-router";

import { AppSidebar } from "@/components/app-shell/app-sidebar";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getSidebarDefaultOpen } from "@/lib/sidebar-preference";

export function AppShell() {
  return (
    <TooltipProvider>
      <SidebarProvider defaultOpen={getSidebarDefaultOpen()}>
        <AppSidebar />
        <SidebarInset className="min-w-0">
          <header className="sticky top-0 z-30 flex h-14 items-center border-b bg-background px-4 md:hidden">
            <SidebarTrigger aria-label="打开主导航" />
          </header>
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
