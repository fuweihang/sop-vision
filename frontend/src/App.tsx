import { RouterProvider } from "@tanstack/react-router";
import { TanStackDevtools } from "@tanstack/react-devtools";
import { ReactQueryDevtoolsPanel } from "@tanstack/react-query-devtools";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { queryClient } from "@/lib/query-client";
import { router } from "@/lib/router";
import { enableApiMocking } from "@/mocks/enable-api-mocking";
import { AppProviders } from "@/providers/app-providers";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("未找到 Root");
}

// 开发场景必须先完成 Service Worker 注册；否则首个查询可能绕过 Mock 访问真实 Backend。
await enableApiMocking();

createRoot(rootElement).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
      <TanStackDevtools
        config={{ position: "bottom-right" }}
        plugins={[
          {
            name: "TanStack Query",
            render: <ReactQueryDevtoolsPanel client={queryClient} />,
          },
          {
            name: "TanStack Router",
            render: <TanStackRouterDevtoolsPanel router={router} />,
          },
        ]}
      />
    </AppProviders>
  </StrictMode>,
);
