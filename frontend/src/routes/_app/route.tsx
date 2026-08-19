import { createFileRoute } from "@tanstack/react-router";

import { AppShell } from "@/components/app-shell/app-shell";

export const Route = createFileRoute("/_app")({
  component: AppShell,
});
