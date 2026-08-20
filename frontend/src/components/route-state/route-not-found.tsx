import {
  ArrowLeft01Icon,
  Camera01Icon,
  Search01Icon,
  Task01Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { Link } from "@tanstack/react-router";

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
import type { RouteReturnTarget } from "@/components/route-state/route-error";

export type RouteNotFoundKind = "page" | "camera" | "task";

export interface RouteNotFoundProps {
  kind: RouteNotFoundKind;
  title: string;
  description: string;
  returnLabel: string;
  returnTo: RouteReturnTarget;
}

const notFoundIcons = {
  page: Search01Icon,
  camera: Camera01Icon,
  task: Task01Icon,
};

export function RouteNotFound({
  kind,
  title,
  description,
  returnLabel,
  returnTo,
}: RouteNotFoundProps) {
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
          <Link to={returnTo} preload="intent" className={buttonVariants()}>
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
