import { AlertCircleIcon, ReloadIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export interface PageEmptyStateProps {
  /** 区分系统确实无数据与当前筛选无匹配，便于页面测试和可观测性稳定识别。 */
  kind: "empty" | "no-results";
  title: string;
  description: string;
  media: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * 数据为空和搜索无结果共用同一视觉 primitive，但由调用方提供不同文案与恢复动作。
 *
 * 组件不推断查询条件，也不内置“创建”“清除搜索”等 CRUD 行为，避免 Foundation 公共层知道
 * 具体资源；`kind` 只保留两个页面状态的稳定语义。
 */
export function PageEmptyState({
  kind,
  title,
  description,
  media,
  action,
  className,
}: PageEmptyStateProps) {
  return (
    <Empty
      data-page-state={kind}
      className={cn("min-h-88 border-0", className)}
    >
      <EmptyHeader>
        <EmptyMedia variant="icon">{media}</EmptyMedia>
        <EmptyTitle>
          <h2>{title}</h2>
        </EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {action === undefined || action === null ? null : (
        <EmptyContent>{action}</EmptyContent>
      )}
    </Empty>
  );
}

export interface PageRecoverableErrorProps {
  title: string;
  description: string;
  onRetry: () => void;
  retryLabel?: string;
  isRetrying?: boolean;
  className?: string;
}

/** 首次请求失败时替换内容区域，并始终给出明确且可重复触发的恢复动作。 */
export function PageRecoverableError({
  title,
  description,
  onRetry,
  retryLabel = "重试",
  isRetrying = false,
  className,
}: PageRecoverableErrorProps) {
  return (
    <Alert
      variant="destructive"
      aria-busy={isRetrying}
      className={cn("max-w-2xl", className)}
    >
      <HugeiconsIcon icon={AlertCircleIcon} strokeWidth={2} />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <p>{description}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          disabled={isRetrying}
          onClick={onRetry}
        >
          {isRetrying ? (
            <Spinner data-icon="inline-start" aria-hidden="true" />
          ) : (
            <HugeiconsIcon
              data-icon="inline-start"
              icon={ReloadIcon}
              strokeWidth={2}
            />
          )}
          {isRetrying ? "正在重试" : retryLabel}
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export type PageBackgroundStatusProps =
  | { state: "idle" }
  | { state: "refreshing"; label: string }
  | {
      state: "error";
      title: string;
      description: string;
      onRetry: () => void;
      retryLabel?: string;
    };

/**
 * 后台状态只提供非阻塞反馈，不拥有或替换页面内容。
 *
 * 调用方把它与已经渲染的数据并列组合，因此刷新或刷新失败都不会卸载旧内容。首次无数据的
 * 错误必须使用 `PageRecoverableError`，不能把后台错误误用成完整页面错误。
 */
export function PageBackgroundStatus(props: PageBackgroundStatusProps) {
  if (props.state === "idle") {
    return null;
  }

  if (props.state === "refreshing") {
    return (
      <div
        data-page-state="background-refreshing"
        role="status"
        aria-label={props.label}
        aria-live="polite"
        className="flex min-h-8 items-center gap-2 text-sm text-muted-foreground"
      >
        <Spinner aria-hidden="true" />
        <span>{props.label}</span>
      </div>
    );
  }

  return (
    <Alert
      data-page-state="background-error"
      variant="destructive"
      className="max-w-2xl"
    >
      <HugeiconsIcon icon={AlertCircleIcon} strokeWidth={2} />
      <AlertTitle>{props.title}</AlertTitle>
      <AlertDescription>
        <p>{props.description}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={props.onRetry}
        >
          <HugeiconsIcon
            data-icon="inline-start"
            icon={ReloadIcon}
            strokeWidth={2}
          />
          {props.retryLabel ?? "重新刷新"}
        </Button>
      </AlertDescription>
    </Alert>
  );
}
