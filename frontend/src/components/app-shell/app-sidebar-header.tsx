import { Link } from "@tanstack/react-router";

import {
  SidebarHeader,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";

const BRAND_LABEL = "AI 行为识别与预警系统";

export function AppSidebarHeader() {
  const { open } = useSidebar();
  const triggerLabel = open ? "折叠侧边栏" : "展开侧边栏";

  return (
    <SidebarHeader className="flex-row items-center gap-1 group-data-[collapsible=icon]:flex-col">
      <Link
        to="/cameras"
        aria-label={BRAND_LABEL}
        className="flex h-10 min-w-0 flex-1 items-center gap-2 overflow-hidden rounded-md px-1.5 outline-hidden hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:flex-none group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
      >
        <img
          src="/brand/sop-vision-logo.png"
          alt=""
          className="h-5 w-11 shrink-0 object-contain group-data-[collapsible=icon]:w-7"
        />
        <span className="truncate text-sm font-semibold group-data-[collapsible=icon]:hidden">
          AI 行为识别与预警系统
        </span>
      </Link>
      <SidebarTrigger
        aria-label={triggerLabel}
        aria-expanded={open}
        title={triggerLabel}
        className="hidden shrink-0 md:inline-flex"
      />
    </SidebarHeader>
  );
}
