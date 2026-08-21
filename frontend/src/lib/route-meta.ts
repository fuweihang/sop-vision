import type { ComponentProps, ReactElement } from "react";

/**
 * StaticDataRouteOption 本身不携带具体路由的泛型，因此在协议边界使用 unknown。
 * 各业务路由应在标签解析器中通过类型守卫收窄 loaderData 和 params。
 */
export type ShellMatchParams = Readonly<Record<string, unknown>>;

export interface ShellRouteMatchContext {
  routeId: string;
  pathname: string;
  params: ShellMatchParams;
  loaderData?: unknown;
}

export type ShellLinkPresentationProps = Pick<
  ComponentProps<"a">,
  "aria-label" | "children" | "className"
>;

export type ShellLinkRenderer = (
  props: ShellLinkPresentationProps,
) => ReactElement;

export type ShellBreadcrumbLabel =
  string | ((match: ShellRouteMatchContext) => string);

export interface ShellBreadcrumbDefinition {
  label: ShellBreadcrumbLabel;
  /** 特殊目标必须在路由定义处渲染 Link，以保留 Router 的完整类型推断。 */
  renderLink?: ShellLinkRenderer;
}

export type ShellBreadcrumb = string | ShellBreadcrumbDefinition;

export interface ShellBackDefinition {
  /** 返回链接或按钮使用的可访问名称。 */
  label: string;
  renderLink: ShellLinkRenderer;
}

export interface ShellRouteMeta {
  breadcrumb?: ShellBreadcrumb;
  back?: ShellBackDefinition;
}

/**
 * 扩展 TanStack Router 的全局 staticData 协议。
 * 两个字段均为可选，未声明 Shell 元数据的路由不需要提供空对象。
 */
declare module "@tanstack/react-router" {
  interface StaticDataRouteOption {
    breadcrumb?: ShellBreadcrumb;
    back?: ShellBackDefinition;
  }
}

export interface ShellRouteMatch extends ShellRouteMatchContext {
  staticData: ShellRouteMeta;
}

export interface ShellBreadcrumbItem {
  routeId: string;
  pathname: string;
  label: string;
  renderLink?: ShellLinkRenderer;
}

export type ShellBackItem = ShellBackDefinition;

/** 按 useMatches() 的父到子顺序解析有 breadcrumb 元数据的 match。 */
export function resolveBreadcrumbItems(
  matches: readonly ShellRouteMatch[],
): ShellBreadcrumbItem[] {
  return matches.flatMap((match) => {
    const breadcrumb = match.staticData.breadcrumb;

    if (breadcrumb === undefined) {
      return [];
    }

    const definition =
      typeof breadcrumb === "string" ? { label: breadcrumb } : breadcrumb;
    const label =
      typeof definition.label === "function"
        ? definition.label(match)
        : definition.label;
    const baseItem = {
      routeId: match.routeId,
      pathname: match.pathname,
      label,
    };

    return definition.renderLink === undefined
      ? [baseItem]
      : [
          {
            ...baseItem,
            renderLink: definition.renderLink,
          },
        ];
  });
}

/** 从最深层匹配开始查找返回元数据，保证子路由可以覆盖父路由定义。 */
export function resolveBackItem(
  matches: readonly ShellRouteMatch[],
): ShellBackItem | undefined {
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const match = matches[index];
    const back = match?.staticData.back;

    if (match !== undefined && back !== undefined) {
      return back;
    }
  }

  return undefined;
}

/**
 * 动态详情优先使用 loaderData 标签；数据尚未就绪时退回到路由参数。
 * 两者都不存在时返回 undefined，由具体路由决定最终的静态兜底文案。
 */
export function getLoaderDataLabelOrParam(
  match: ShellRouteMatchContext,
  selectLoaderDataLabel: (loaderData: unknown) => string | undefined,
  fallbackParam: string,
): string | undefined {
  const loaderDataLabel = selectLoaderDataLabel(match.loaderData);

  if (loaderDataLabel !== undefined) {
    return loaderDataLabel;
  }

  const param = match.params[fallbackParam];

  return typeof param === "string" || typeof param === "number"
    ? String(param)
    : undefined;
}
