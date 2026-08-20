import { AppMainNavigation } from "@/components/app-shell/app-main-navigation";
import { AppSidebarHeader } from "@/components/app-shell/app-sidebar-header";
import { Sidebar, SidebarContent } from "@/components/ui/sidebar";

export function AppSidebar() {
  return (
    <Sidebar
      side="left"
      variant="sidebar"
      collapsible="icon"
      aria-label="主导航"
      mobileTitle="主导航"
      mobileDescription="显示移动端主导航。"
    >
      <AppSidebarHeader />
      <SidebarContent>
        <AppMainNavigation />
      </SidebarContent>
    </Sidebar>
  );
}
