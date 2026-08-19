import { RouterProvider } from "@tanstack/react-router";
import { TanStackDevtools } from "@tanstack/react-devtools";
import { ReactQueryDevtoolsPanel } from "@tanstack/react-query-devtools";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { queryClient } from "@/lib/query-client";
import { router } from "@/lib/router";
import { AppProviders } from "@/providers/app-providers";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element not found");
}

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
