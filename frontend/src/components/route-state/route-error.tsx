import {
  AlertCircleIcon,
  ArrowLeft01Icon,
  ReloadIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Link,
  type RegisteredRouter,
  type ValidateLinkOptions,
  useRouter,
} from "@tanstack/react-router";
import type { ReactNode } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";

export interface RouteErrorProps<
  TRouter extends RegisteredRouter = RegisteredRouter,
  TOptions = unknown,
> {
  title: string;
  description: string;
  returnLabel: string;
  returnLinkOptions: ValidateLinkOptions<TRouter, TOptions>;
}

export function RouteError<TRouter extends RegisteredRouter, TOptions>(
  props: RouteErrorProps<TRouter, TOptions>,
): ReactNode;
export function RouteError({
  title,
  description,
  returnLabel,
  returnLinkOptions,
}: RouteErrorProps): ReactNode {
  const router = useRouter();

  return (
    <PageContainer>
      <PageHeader title={title} description={description} />
      <Alert variant="destructive" className="max-w-2xl">
        <HugeiconsIcon icon={AlertCircleIcon} strokeWidth={2} />
        <AlertTitle>页面内容暂时不可用</AlertTitle>
        <AlertDescription>
          <p>你可以重试加载，或返回一个确定的页面继续操作。</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" onClick={() => void router.invalidate()}>
              <HugeiconsIcon
                data-icon="inline-start"
                icon={ReloadIcon}
                strokeWidth={2}
              />
              重试
            </Button>
            <Link
              {...returnLinkOptions}
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
