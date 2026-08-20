import { useRouterState } from "@tanstack/react-router";
import { useEffect } from "react";

import { useSidebar } from "@/components/ui/sidebar";

export function SidebarRouteSync() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const { isMobile, setOpenMobile } = useSidebar();

  useEffect(() => {
    setOpenMobile(false);
  }, [pathname, setOpenMobile]);

  useEffect(() => {
    if (!isMobile) {
      setOpenMobile(false);
    }
  }, [isMobile, setOpenMobile]);

  return null;
}
