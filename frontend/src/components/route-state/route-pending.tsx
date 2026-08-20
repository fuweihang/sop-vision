import type { ComponentProps } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type RoutePendingVariant = "camera-list" | "task-list" | "detail";

export interface RoutePendingProps {
  label: string;
  variant: RoutePendingVariant;
}

function RouteSkeleton({
  className,
  ...props
}: ComponentProps<typeof Skeleton>) {
  return (
    <Skeleton
      className={cn("motion-reduce:animate-none", className)}
      {...props}
    />
  );
}

function PageHeadingSkeleton() {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <RouteSkeleton className="h-7 w-40 max-w-full" />
      <RouteSkeleton className="h-4 w-72 max-w-full" />
    </div>
  );
}

function ToolbarSkeleton() {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <RouteSkeleton className="h-8 w-full sm:max-w-sm" />
      <RouteSkeleton className="h-8 w-24" />
    </div>
  );
}

function CameraListSkeleton() {
  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeadingSkeleton />
        <RouteSkeleton className="hidden h-8 w-24 sm:block" />
      </div>
      <ToolbarSkeleton />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Card key={index} className="overflow-hidden py-0">
            <RouteSkeleton className="aspect-video w-full rounded-none" />
            <CardHeader className="gap-2 py-4">
              <RouteSkeleton className="h-4 w-2/3" />
              <RouteSkeleton className="h-3 w-1/2" />
            </CardHeader>
            <CardContent className="flex justify-between gap-4 pb-4">
              <RouteSkeleton className="h-3 w-20" />
              <RouteSkeleton className="h-3 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

function TaskListSkeleton() {
  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHeadingSkeleton />
        <RouteSkeleton className="hidden h-8 w-24 sm:block" />
      </div>
      <ToolbarSkeleton />
      <Card>
        <CardHeader>
          <div className="flex gap-4">
            <RouteSkeleton className="h-4 flex-1" />
            <RouteSkeleton className="hidden h-4 w-32 sm:block" />
            <RouteSkeleton className="hidden h-4 w-24 md:block" />
            <RouteSkeleton className="h-4 w-16" />
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {Array.from({ length: 5 }, (_, index) => (
            <div key={index} className="flex items-center gap-4">
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <RouteSkeleton className="h-4 w-2/3" />
                <RouteSkeleton className="h-3 w-1/2" />
              </div>
              <RouteSkeleton className="hidden h-4 w-32 sm:block" />
              <RouteSkeleton className="hidden h-4 w-24 md:block" />
              <RouteSkeleton className="h-6 w-16" />
            </div>
          ))}
        </CardContent>
      </Card>
    </>
  );
}

function DetailSkeleton() {
  return (
    <>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <PageHeadingSkeleton />
        <div className="flex gap-2">
          <RouteSkeleton className="h-8 w-24" />
          <RouteSkeleton className="h-8 w-24" />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.65fr)_minmax(18rem,0.75fr)]">
        <Card className="overflow-hidden py-0">
          <CardContent className="p-0">
            <RouteSkeleton className="aspect-video w-full rounded-none" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="gap-2">
            <RouteSkeleton className="h-5 w-28" />
            <RouteSkeleton className="h-3 w-44 max-w-full" />
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {Array.from({ length: 5 }, (_, index) => (
              <div key={index} className="flex justify-between gap-4">
                <RouteSkeleton className="h-4 w-20" />
                <RouteSkeleton className="h-4 w-28" />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader className="gap-2">
          <RouteSkeleton className="h-5 w-36" />
          <RouteSkeleton className="h-3 w-60 max-w-full" />
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {Array.from({ length: 3 }, (_, index) => (
            <RouteSkeleton key={index} className="h-8 w-full" />
          ))}
        </CardContent>
      </Card>
    </>
  );
}

export function RoutePending({ label, variant }: RoutePendingProps) {
  return (
    <PageContainer
      role="status"
      aria-label={label}
      aria-live="polite"
      aria-busy="true"
    >
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="contents">
        {variant === "camera-list" ? <CameraListSkeleton /> : null}
        {variant === "task-list" ? <TaskListSkeleton /> : null}
        {variant === "detail" ? <DetailSkeleton /> : null}
      </div>
    </PageContainer>
  );
}
