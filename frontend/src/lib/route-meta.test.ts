import {
  createFileRoute,
  type MakeRouteMatchUnion,
} from "@tanstack/react-router";
import { createElement } from "react";
import { expect, test } from "vitest";

import {
  getLoaderDataLabelOrParam,
  resolveBackItem,
  resolveBreadcrumbItems,
  type ShellLinkRenderer,
  type ShellRouteMatch,
} from "@/lib/route-meta";

const renderItemsLink: ShellLinkRenderer = (props) => createElement("a", props);
const renderItemLink: ShellLinkRenderer = (props) => createElement("a", props);

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
          renderLink: renderItemsLink,
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
      renderLink: renderItemsLink,
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

test("保留在路由定义处完成类型检查的特殊链接渲染器", () => {
  const items = resolveBreadcrumbItems([
    createMatch({
      staticData: {
        breadcrumb: {
          label: "Item details",
          renderLink: renderItemLink,
        },
      },
    }),
  ]);

  expect(items[0]?.renderLink).toBe(renderItemLink);
});

test("从最深层匹配项解析返回元数据", () => {
  const parentBack = {
    label: "Back to items",
    renderLink: renderItemsLink,
  };
  const itemBack = {
    label: "Back to item",
    renderLink: renderItemLink,
  };

  expect(
    resolveBackItem([
      createMatch({
        staticData: {
          back: parentBack,
        },
      }),
      createMatch({
        staticData: {
          back: itemBack,
        },
      }),
    ]),
  ).toBe(itemBack);
});

test("没有返回元数据时不产生返回项", () => {
  expect(resolveBackItem([createMatch()])).toBeUndefined();
});

test("createFileRoute 接受扩展后的静态数据协议", () => {
  const route = createFileRoute("/")({
    staticData: {
      breadcrumb: {
        label: ({ pathname }) => pathname,
        renderLink: renderItemsLink,
      },
      back: {
        label: "Back to home",
        renderLink: renderItemsLink,
      },
    },
  });

  expect(route.options.staticData?.back?.label).toBe("Back to home");
});

test("接受 useMatches 返回的匹配项联合类型", () => {
  const matches: MakeRouteMatchUnion[] = [];

  expect(resolveBreadcrumbItems(matches)).toEqual([]);
});
