import type { ComponentProps } from "react";

import { PageContainer } from "@/components/layout/page-container";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

/**
 * Pending 只描述页面的信息结构，不绑定 Camera、Task 或具体 CRUD。
 *
 * `card-list` 对应带媒体预览的资源卡片；`table-list` 对应字段稳定的数据表。后续领域可以复用
 * 这两种骨架，同时仍由各路由提供面向用户的加载文案。
 */
export type RoutePendingVariant = "card-list" | "table-list" | "detail";

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
    <div className="flex min-w-0 items-center gap-3">
      <RouteSkeleton className="h-8 min-w-0 flex-1" />
      <RouteSkeleton className="h-8 w-24 shrink-0" />
    </div>
  );
}

/**
 * 卡片骨架保留原型的 16:9 预览、名称/状态、地址和在线统计层级。
 *
 * 520px/1200px 是原型冻结的 Card Grid 重排点；使用完整静态类名，确保 Tailwind v4 能在
 * 构建时发现任意断点，并避免通过 JavaScript 猜测视口。
 */
function CardListSkeleton() {
  return (
    <>
      <ToolbarSkeleton />
      <div className="grid grid-cols-1 gap-4 min-[520px]:grid-cols-2 min-[1200px]:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Card key={index} className="gap-0 py-0">
            <CardContent className="p-0">
              <RouteSkeleton className="aspect-video w-full rounded-none" />
            </CardContent>
            <CardHeader className="gap-2 py-4">
              <RouteSkeleton className="h-4 w-2/3 max-w-40" />
              <CardAction>
                <RouteSkeleton className="h-5 w-14" />
              </CardAction>
              <RouteSkeleton className="h-3 w-1/2 max-w-32" />
            </CardHeader>
            <CardContent className="pb-4">
              <RouteSkeleton className="h-3 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

function TableRowSkeleton() {
  return (
    <TableRow>
      <TableCell>
        <div className="flex min-w-44 flex-col gap-2">
          <RouteSkeleton className="h-4 w-32" />
          <RouteSkeleton className="h-3 w-44" />
        </div>
      </TableCell>
      <TableCell>
        <RouteSkeleton className="h-4 w-36" />
      </TableCell>
      <TableCell>
        <RouteSkeleton className="h-4 w-28" />
      </TableCell>
      <TableCell>
        <RouteSkeleton className="h-5 w-14" />
      </TableCell>
      <TableCell>
        <RouteSkeleton className="ml-auto size-5" />
      </TableCell>
    </TableRow>
  );
}

function CompactTableRowSkeleton() {
  const fields = ["任务", "摄像头源", "算法", "状态", "查看"];

  return (
    <div className="flex flex-col gap-2 px-4 py-3">
      {fields.map((field, index) => (
        <div
          key={field}
          className="grid grid-cols-[6rem_minmax(0,1fr)] items-center gap-3 py-1"
        >
          <RouteSkeleton className="h-3 w-14" />
          <div className="flex min-w-0 flex-col gap-2">
            <RouteSkeleton
              className={cn(
                "h-4",
                index === 0 ? "w-2/3" : "w-1/2",
                index === 4 ? "w-5" : undefined,
              )}
            />
            {index === 0 ? <RouteSkeleton className="h-3 w-4/5" /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

/** 表格骨架在宽屏保留原型五列表头，900px 以下切换为带字段标签节奏的堆叠行。 */
function TableListSkeleton() {
  return (
    <>
      <PageHeadingSkeleton />
      <ToolbarSkeleton />
      <Card className="gap-0 py-0">
        <CardContent className="hidden p-0 min-[901px]:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>任务名称</TableHead>
                <TableHead>摄像头源</TableHead>
                <TableHead>算法</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>
                  <span className="sr-only">查看</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Array.from({ length: 5 }, (_, index) => (
                <TableRowSkeleton key={index} />
              ))}
            </TableBody>
          </Table>
        </CardContent>
        <CardContent className="divide-y p-0 min-[901px]:hidden">
          {Array.from({ length: 3 }, (_, index) => (
            <CompactTableRowSkeleton key={index} />
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
      <div className="grid gap-6 min-[1200px]:grid-cols-[minmax(0,1.65fr)_minmax(18rem,0.75fr)]">
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
        {variant === "card-list" ? <CardListSkeleton /> : null}
        {variant === "table-list" ? <TableListSkeleton /> : null}
        {variant === "detail" ? <DetailSkeleton /> : null}
      </div>
    </PageContainer>
  );
}
