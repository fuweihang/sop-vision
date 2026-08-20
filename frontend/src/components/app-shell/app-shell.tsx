import { Outlet } from "@tanstack/react-router";

import { AppHeader } from "@/components/app-shell/app-header";
import { AppSidebar } from "@/components/app-shell/app-sidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getSidebarDefaultOpen } from "@/lib/sidebar-preference";

export function AppShell() {
  return (
    <TooltipProvider>
      <SidebarProvider defaultOpen={getSidebarDefaultOpen()}>
        <AppSidebar />
        <SidebarInset className="min-w-0">
          <AppHeader />
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
