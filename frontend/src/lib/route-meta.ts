/** Shell 只接受站内绝对路由地址，避免把相对地址的解析语义带入元数据。 */
export type ShellRoutePath = `/${string}`;

/**
 * StaticDataRouteOption 本身不携带具体路由的泛型，因此在协议边界使用 unknown。
 * 各业务路由应在标签解析器中通过类型守卫收窄 loaderData 和 params。
 */
export type ShellMatchParams = Readonly<Record<string, unknown>>;

export type ShellRouteTargetParams = Readonly<Record<string, string>>;

export interface ShellRouteMatchContext {
  routeId: string;
  pathname: string;
  params: ShellMatchParams;
  loaderData?: unknown;
}

export type ShellRouteTargetParamsResolver = (
  match: ShellRouteMatchContext,
) => ShellRouteTargetParams;

export interface ShellRouteTarget {
  to: ShellRoutePath;
  /** 动态目标可从当前 match 提取参数，解析后再交给路由适配层。 */
  params?: ShellRouteTargetParams | ShellRouteTargetParamsResolver;
}

export interface ResolvedShellRouteTarget {
  to: ShellRoutePath;
  params?: ShellRouteTargetParams;
}

export type ShellBreadcrumbLabel =
  string | ((match: ShellRouteMatchContext) => string);

export interface ShellBreadcrumbDefinition {
  label: ShellBreadcrumbLabel;
  target?: ShellRouteTarget;
}

export type ShellBreadcrumb = string | ShellBreadcrumbDefinition;

export interface ShellBackDefinition extends ShellRouteTarget {
  /** 返回链接或按钮使用的可访问名称。 */
  label: string;
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
  target?: ResolvedShellRouteTarget;
}

export function resolveShellRouteTarget(
  target: ShellRouteTarget,
  match: ShellRouteMatchContext,
): ResolvedShellRouteTarget {
  const params =
    typeof target.params === "function" ? target.params(match) : target.params;

  return params === undefined ? { to: target.to } : { to: target.to, params };
}

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

    return definition.target === undefined
      ? [baseItem]
      : [
          {
            ...baseItem,
            target: resolveShellRouteTarget(definition.target, match),
          },
        ];
  });
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
