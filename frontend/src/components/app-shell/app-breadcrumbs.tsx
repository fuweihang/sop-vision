import { Link, useMatches } from "@tanstack/react-router";
import { Fragment } from "react";

import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  resolveBreadcrumbItems,
  type ShellBreadcrumbItem,
} from "@/lib/route-meta";

type DisplayBreadcrumbItem = ShellBreadcrumbItem | "ellipsis";

function compressBreadcrumbItems(
  items: readonly ShellBreadcrumbItem[],
): DisplayBreadcrumbItem[] {
  if (items.length <= 3) {
    return [...items];
  }

  const firstItem = items[0];
  const currentItem = items.at(-1);

  return firstItem === undefined || currentItem === undefined
    ? []
    : [firstItem, "ellipsis", currentItem];
}

export function AppBreadcrumbs() {
  const matches = useMatches();
  const items = resolveBreadcrumbItems(matches);
  const displayItems = compressBreadcrumbItems(items);

  return (
    <Breadcrumb className="min-w-0 max-w-full">
      <BreadcrumbList className="min-w-0 flex-nowrap overflow-hidden whitespace-nowrap">
        {displayItems.map((item, index) => {
          const isCurrent = index === displayItems.length - 1;

          return (
            <Fragment
              key={item === "ellipsis" ? "breadcrumb-ellipsis" : item.routeId}
            >
              {index > 0 && <BreadcrumbSeparator className="shrink-0" />}
              {item === "ellipsis" ? (
                <BreadcrumbItem className="shrink-0">
                  <BreadcrumbEllipsis />
                </BreadcrumbItem>
              ) : (
                <BreadcrumbItem className="min-w-0">
                  {isCurrent ? (
                    <BreadcrumbPage className="block truncate">
                      {item.label}
                    </BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink
                      className="block truncate"
                      render={
                        item.renderLink?.({}) ?? <Link to={item.pathname} />
                      }
                    >
                      {item.label}
                    </BreadcrumbLink>
                  )}
                </BreadcrumbItem>
              )}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
