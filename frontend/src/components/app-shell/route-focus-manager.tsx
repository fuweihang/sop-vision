import { useRouterState } from "@tanstack/react-router";
import { useEffect, useRef } from "react";

function isVisible(element: HTMLElement) {
  if (!element.isConnected) {
    return false;
  }

  for (
    let current: HTMLElement | null = element;
    current !== null;
    current = current.parentElement
  ) {
    if (
      current.hidden ||
      current.hasAttribute("inert") ||
      current.getAttribute("aria-hidden") === "true"
    ) {
      return false;
    }

    const style = window.getComputedStyle(current);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.visibility === "collapse" ||
      style.contentVisibility === "hidden"
    ) {
      return false;
    }
  }

  return true;
}

function findFirstVisible(elements: NodeListOf<HTMLElement>) {
  return Array.from(elements).find(isVisible);
}

export function RouteFocusManager() {
  const pathname = useRouterState({
    // 新路由匹配项渲染完成后，resolvedLocation 才会发生变化。
    select: (state) =>
      state.resolvedLocation?.pathname ?? state.location.pathname,
  });
  const previousPathname = useRef(pathname);

  useEffect(() => {
    if (previousPathname.current === pathname) {
      return;
    }

    previousPathname.current = pathname;

    const animationFrame = window.requestAnimationFrame(() => {
      const mainContent = document.getElementById("main-content");
      if (!(mainContent instanceof HTMLElement)) {
        return;
      }

      const routeTarget = findFirstVisible(
        mainContent.querySelectorAll<HTMLElement>("[data-route-focus]"),
      );
      const pageHeading = findFirstVisible(
        mainContent.querySelectorAll<HTMLElement>("h1"),
      );

      // Router 会在 onRendered 阶段恢复滚动；preventScroll 可避免焦点交接
      // 再次触发滚动并与其竞争。
      (routeTarget ?? pageHeading)?.focus({ preventScroll: true });
    });

    return () => window.cancelAnimationFrame(animationFrame);
  }, [pathname]);

  return null;
}
