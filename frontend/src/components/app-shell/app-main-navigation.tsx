import { HugeiconsIcon } from "@hugeicons/react";
import { Link, useMatchRoute } from "@tanstack/react-router";

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { mainNavigation } from "@/config/navigation";

export function AppMainNavigation() {
  const matchRoute = useMatchRoute();

  return (
    <SidebarGroup>
      <SidebarGroupContent>
        <nav aria-label="主菜单">
          <SidebarMenu className="gap-1">
            {mainNavigation.map((item) => {
              const isActive = Boolean(
                matchRoute({ to: item.linkOptions.to, fuzzy: true }),
              );

              return (
                <SidebarMenuItem key={item.linkOptions.to}>
                  <SidebarMenuButton
                    render={
                      <Link
                        {...item.linkOptions}
                        aria-current={isActive ? "page" : undefined}
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
