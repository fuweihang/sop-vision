import {
  AlertCircleIcon,
  ArrowLeft01Icon,
  ReloadIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { Link, type ErrorComponentProps } from "@tanstack/react-router";
import { useState } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

export type RouteReturnTarget = "/" | "/cameras" | "/tasks";

export interface RouteErrorProps extends Pick<ErrorComponentProps, "reset"> {
  title: string;
  description: string;
  onRetry: () => Promise<void> | void;
  returnLabel: string;
  returnTo: RouteReturnTarget;
}

export function RouteError({
  title,
  description,
  onRetry,
  reset,
  returnLabel,
  returnTo,
}: RouteErrorProps) {
  const [isRetrying, setIsRetrying] = useState(false);

  async function handleRetry() {
    setIsRetrying(true);
    reset();

    try {
      await onRetry();
    } finally {
      setIsRetrying(false);
    }
  }

  return (
    <PageContainer>
      <PageHeader title={title} description={description} />
      <Alert variant="destructive" className="max-w-2xl">
        <HugeiconsIcon icon={AlertCircleIcon} strokeWidth={2} />
        <AlertTitle>页面内容暂时不可用</AlertTitle>
        <AlertDescription>
          <p>你可以重试加载，或返回一个确定的页面继续操作。</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={() => void handleRetry()}
              disabled={isRetrying}
            >
              {isRetrying ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <HugeiconsIcon
                  data-icon="inline-start"
                  icon={ReloadIcon}
                  strokeWidth={2}
                />
              )}
              {isRetrying ? "正在重试" : "重试"}
            </Button>
            <Link
              to={returnTo}
              preload="intent"
              className={buttonVariants({ variant: "outline" })}
            >
              <HugeiconsIcon
                data-icon="inline-start"
                icon={ArrowLeft01Icon}
                strokeWidth={2}
              />
              {returnLabel}
            </Link>
          </div>
        </AlertDescription>
      </Alert>
    </PageContainer>
  );
}
