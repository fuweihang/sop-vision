import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/cameras")({
  staticData: {
    breadcrumb: "摄像头",
  },
  component: CamerasLayout,
});

function CamerasLayout() {
  return <Outlet />;
}
