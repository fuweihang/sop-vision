import { Link } from "@tanstack/react-router";

import { buttonVariants } from "@/components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import type {
  CameraPage,
  NormalizedCameraListQuery,
} from "@/features/cameras/api/cameras-api";
import { cameraPageCount } from "@/features/cameras/components/camera-list-pagination-model";

interface CameraListPaginationProps {
  page: Pick<CameraPage, "page" | "page_size" | "total">;
  search: NormalizedCameraListQuery;
}

function pageSearch(
  search: NormalizedCameraListQuery,
  page: number,
  pageSize: number,
): NormalizedCameraListQuery {
  return { ...search, page, page_size: pageSize };
}

/** MVP 分页只呈现上一页、当前页/总页数和下一页，不生成页码窗口或跳页控件。 */
export function CameraListPagination({
  page,
  search,
}: CameraListPaginationProps) {
  const totalPages = cameraPageCount(page.total, page.page_size);
  const hasPreviousPage = page.page > 1;
  const hasNextPage = page.page < totalPages;

  if (totalPages <= 1) {
    return null;
  }

  return (
    <Pagination aria-label="摄像头列表分页">
      <PaginationContent>
        {hasPreviousPage ? (
          <PaginationItem>
            <PaginationPrevious
              render={
                <Link
                  to="/cameras"
                  search={pageSearch(search, page.page - 1, page.page_size)}
                  preload="intent"
                />
              }
            />
          </PaginationItem>
        ) : null}
        <PaginationItem>
          <span
            aria-current="page"
            className={buttonVariants({ variant: "outline", size: "default" })}
          >
            第 {page.page} / {totalPages} 页
          </span>
        </PaginationItem>
        {hasNextPage ? (
          <PaginationItem>
            <PaginationNext
              render={
                <Link
                  to="/cameras"
                  search={pageSearch(search, page.page + 1, page.page_size)}
                  preload="intent"
                />
              }
            />
          </PaginationItem>
        ) : null}
      </PaginationContent>
    </Pagination>
  );
}

interface CameraOutOfRangeActionsProps {
  page: Pick<CameraPage, "page" | "page_size">;
  search: NormalizedCameraListQuery;
}

/** 越界页不自动跳转，让 URL 与 API 返回保持可见，并提供用户明确选择的恢复路径。 */
export function CameraOutOfRangeActions({
  page,
  search,
}: CameraOutOfRangeActionsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      <Link
        to="/cameras"
        search={pageSearch(search, 1, page.page_size)}
        preload="intent"
        className={buttonVariants()}
      >
        返回第一页
      </Link>
      {page.page > 1 ? (
        <Link
          to="/cameras"
          search={pageSearch(search, page.page - 1, page.page_size)}
          preload="intent"
          className={buttonVariants({ variant: "outline" })}
        >
          返回上一页
        </Link>
      ) : null}
    </div>
  );
}
