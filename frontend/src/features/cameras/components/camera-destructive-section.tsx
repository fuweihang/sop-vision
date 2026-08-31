import { Delete02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function CameraDestructiveSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>删除摄像头</h2>
        </CardTitle>
        <CardDescription>删除后不可恢复；删除功能暂未实现。</CardDescription>
        <CardAction className="self-center">
          <Button type="button" variant="destructive" disabled>
            <HugeiconsIcon
              icon={Delete02Icon}
              strokeWidth={2}
              data-icon="inline-start"
            />
            删除摄像头
          </Button>
        </CardAction>
      </CardHeader>
    </Card>
  );
}
