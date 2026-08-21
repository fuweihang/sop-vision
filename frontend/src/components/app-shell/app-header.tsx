import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useMatches } from "@tanstack/react-router";

import { AppBreadcrumbs } from "@/components/app-shell/app-breadcrumbs";
import { ThemeToggle } from "@/components/app-shell/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { resolveBackItem } from "@/lib/route-meta";

function RouteBackLink() {
  const matches = useMatches();
  const backItem = resolveBackItem(matches);

  if (backItem === undefined) {
    return null;
  }

  return backItem.renderLink({
    "aria-label": backItem.label,
    className: buttonVariants({ variant: "ghost", size: "icon" }),
    children: (
      <HugeiconsIcon
        data-icon="inline-start"
        icon={ArrowLeft01Icon}
        strokeWidth={2}
      />
    ),
  });
}

export function AppHeader() {
  return (
    <header
      data-slot="app-header"
      className="sticky top-0 z-30 grid h-14 shrink-0 grid-cols-[minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)] items-center border-b border-border bg-background px-4 md:px-6"
    >
      <div
        data-slot="app-header-leading"
        className="flex min-w-0 items-center gap-1 justify-self-start"
      >
        <SidebarTrigger className="md:hidden" aria-label="打开主导航" />
        <RouteBackLink />
      </div>
      <div
        data-slot="app-header-center"
        className="flex min-w-0 justify-center overflow-hidden justify-self-stretch"
      >
        <AppBreadcrumbs />
      </div>
      <div
        data-slot="app-header-trailing"
        className="flex items-center justify-self-end"
      >
        <ThemeToggle />
      </div>
    </header>
  );
}
