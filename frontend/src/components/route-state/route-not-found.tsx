import {
  ArrowLeft01Icon,
  Camera01Icon,
  Search01Icon,
  Task01Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Link,
  type RegisteredRouter,
  type ValidateLinkOptions,
} from "@tanstack/react-router";
import type { ReactNode } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { buttonVariants } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
export type RouteNotFoundKind = "page" | "camera" | "task";

export interface RouteNotFoundProps<
  TRouter extends RegisteredRouter = RegisteredRouter,
  TOptions = unknown,
> {
  kind: RouteNotFoundKind;
  title: string;
  description: string;
  returnLabel: string;
  returnLinkOptions: ValidateLinkOptions<TRouter, TOptions>;
}

const notFoundIcons = {
  page: Search01Icon,
  camera: Camera01Icon,
  task: Task01Icon,
};

export function RouteNotFound<TRouter extends RegisteredRouter, TOptions>(
  props: RouteNotFoundProps<TRouter, TOptions>,
): ReactNode;
export function RouteNotFound({
  kind,
  title,
  description,
  returnLabel,
  returnLinkOptions,
}: RouteNotFoundProps): ReactNode {
  return (
    <PageContainer>
      <Empty className="min-h-88">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HugeiconsIcon icon={notFoundIcons[kind]} strokeWidth={2} />
          </EmptyMedia>
          <EmptyTitle>
            <h1 data-route-focus tabIndex={-1}>
              {title}
            </h1>
          </EmptyTitle>
          <EmptyDescription>{description}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Link
            {...returnLinkOptions}
            preload="intent"
            className={buttonVariants()}
          >
            <HugeiconsIcon
              data-icon="inline-start"
              icon={ArrowLeft01Icon}
              strokeWidth={2}
            />
            {returnLabel}
          </Link>
        </EmptyContent>
      </Empty>
    </PageContainer>
  );
}
