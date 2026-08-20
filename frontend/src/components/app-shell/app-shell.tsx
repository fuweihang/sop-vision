import { Outlet } from "@tanstack/react-router";

import { AppHeader } from "@/components/app-shell/app-header";
import { AppSidebar } from "@/components/app-shell/app-sidebar";
import { RouteFocusManager } from "@/components/app-shell/route-focus-manager";
import { SidebarRouteSync } from "@/components/app-shell/sidebar-route-sync";
import { SkipToContent } from "@/components/app-shell/skip-to-content";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getSidebarDefaultOpen } from "@/lib/sidebar-preference";

export function AppShell() {
  return (
    <TooltipProvider>
      <SidebarProvider defaultOpen={getSidebarDefaultOpen()}>
        <SkipToContent />
        <SidebarRouteSync />
        <RouteFocusManager />
        <AppSidebar />
        <SidebarInset id="main-content" tabIndex={-1} className="min-w-0">
          <AppHeader />
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
