import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/cameras")({
  staticData: {
    breadcrumb: "摄像头",
  },
  component: CamerasPage,
});

function CamerasPage() {
  return (
    <section aria-labelledby="cameras-title">
      <h1 id="cameras-title">摄像头</h1>
      <p>摄像头管理功能将在此提供。</p>
    </section>
  );
}
