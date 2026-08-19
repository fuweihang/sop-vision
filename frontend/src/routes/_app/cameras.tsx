import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/cameras")({
  component: CamerasPage,
});

function CamerasPage() {
  return (
    <section aria-labelledby="cameras-title">
      <h1 id="cameras-title">Cameras</h1>
      <p>Camera management will be available here.</p>
    </section>
  );
}
