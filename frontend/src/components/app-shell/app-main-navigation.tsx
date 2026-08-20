import { HugeiconsIcon } from "@hugeicons/react";
import { Link, useMatchRoute } from "@tanstack/react-router";

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { mainNavigation } from "@/config/navigation";

export function AppMainNavigation() {
  const matchRoute = useMatchRoute();
  const { setOpenMobile } = useSidebar();

  return (
    <SidebarGroup>
      <SidebarGroupContent>
        <nav aria-label="主菜单">
          <SidebarMenu>
            {mainNavigation.map((item) => {
              const isActive = Boolean(
                matchRoute({ to: item.to, fuzzy: true }),
              );

              return (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    render={
                      <Link
                        to={item.to}
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => setOpenMobile(false)}
                      />
                    }
                    isActive={isActive}
                    tooltip={item.label}
                  >
                    <HugeiconsIcon icon={item.icon} strokeWidth={2} />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </nav>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
