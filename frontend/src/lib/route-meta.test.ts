import {
  createFileRoute,
  type MakeRouteMatchUnion,
} from "@tanstack/react-router";
import { expect, test } from "vitest";

import {
  getLoaderDataLabelOrParam,
  resolveBackItem,
  resolveBreadcrumbItems,
  type ShellRouteMatch,
} from "@/lib/route-meta";

function createMatch(
  overrides: Partial<ShellRouteMatch> = {},
): ShellRouteMatch {
  return {
    routeId: "/items/$itemId",
    pathname: "/items/item-42",
    params: { itemId: "item-42" },
    staticData: {},
    ...overrides,
  };
}

test("解析静态面包屑并省略没有元数据的匹配项", () => {
  const items = resolveBreadcrumbItems([
    createMatch({ routeId: "__root__", pathname: "/" }),
    createMatch({
      routeId: "/items",
      pathname: "/items",
      staticData: {
        breadcrumb: {
          label: "Items",
          target: { to: "/items" },
        },
      },
    }),
    createMatch({ staticData: { breadcrumb: "Item details" } }),
  ]);

  expect(items).toEqual([
    {
      routeId: "/items",
      pathname: "/items",
      label: "Items",
      target: { to: "/items" },
    },
    {
      routeId: "/items/$itemId",
      pathname: "/items/item-42",
      label: "Item details",
    },
  ]);
});

test("从 loader 数据解析动态标签", () => {
  const items = resolveBreadcrumbItems([
    createMatch({
      loaderData: { name: "Inspection SOP" },
      staticData: {
        breadcrumb: {
          label: (match) =>
            getLoaderDataLabelOrParam(
              match,
              (loaderData) =>
                typeof loaderData === "object" &&
                loaderData !== null &&
                "name" in loaderData &&
                typeof loaderData.name === "string"
                  ? loaderData.name
                  : undefined,
              "itemId",
            ) ?? "Item details",
        },
      },
    }),
  ]);

  expect(items[0]?.label).toBe("Inspection SOP");
});

test("loader 数据缺失时回退使用路由参数", () => {
  const match = createMatch();

  expect(getLoaderDataLabelOrParam(match, () => undefined, "itemId")).toBe(
    "item-42",
  );
});

test("从当前匹配项解析目标参数", () => {
  const items = resolveBreadcrumbItems([
    createMatch({
      staticData: {
        breadcrumb: {
          label: "Item details",
          target: {
            to: "/items/$itemId",
            params: (match) => ({ itemId: String(match.params.itemId) }),
          },
        },
      },
    }),
  ]);

  expect(items[0]?.target).toEqual({
    to: "/items/$itemId",
    params: { itemId: "item-42" },
  });
});

test("从最深层匹配项解析返回元数据", () => {
  expect(
    resolveBackItem([
      createMatch({
        staticData: {
          back: { to: "/items", label: "Back to items" },
        },
      }),
      createMatch({
        staticData: {
          back: {
            to: "/items/$itemId",
            params: { itemId: "item-42" },
            label: "Back to item",
          },
        },
      }),
    ]),
  ).toEqual({
    to: "/items/$itemId",
    params: { itemId: "item-42" },
    label: "Back to item",
  });
});

test("没有返回元数据时不产生返回项", () => {
  expect(resolveBackItem([createMatch()])).toBeUndefined();
});

test("createFileRoute 接受扩展后的静态数据协议", () => {
  const route = createFileRoute("/")({
    staticData: {
      breadcrumb: {
        label: ({ pathname }) => pathname,
        target: { to: "/" },
      },
      back: {
        to: "/",
        label: "Back to home",
      },
    },
  });

  expect(route.options.staticData?.back?.label).toBe("Back to home");
});

test("接受 useMatches 返回的匹配项联合类型", () => {
  const matches: MakeRouteMatchUnion[] = [];

  expect(resolveBreadcrumbItems(matches)).toEqual([]);
});
