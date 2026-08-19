import {
  createFileRoute,
  type MakeRouteMatchUnion,
} from "@tanstack/react-router";
import { expect, test } from "vitest";

import {
  getLoaderDataLabelOrParam,
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

test("resolves static breadcrumbs and omits matches without metadata", () => {
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

test("resolves a dynamic label from loader data", () => {
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

test("falls back to a route param when loader data is missing", () => {
  const match = createMatch();

  expect(getLoaderDataLabelOrParam(match, () => undefined, "itemId")).toBe(
    "item-42",
  );
});

test("resolves target params from the current match", () => {
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

test("createFileRoute accepts the augmented static data protocol", () => {
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

test("accepts the match union returned by useMatches", () => {
  const matches: MakeRouteMatchUnion[] = [];

  expect(resolveBreadcrumbItems(matches)).toEqual([]);
});
