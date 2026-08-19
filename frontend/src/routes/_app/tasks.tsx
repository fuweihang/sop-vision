import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/tasks")({
  component: TasksPage,
});

function TasksPage() {
  return (
    <section aria-labelledby="tasks-title">
      <h1 id="tasks-title">Tasks</h1>
      <p>Task management will be available here.</p>
    </section>
  );
}
