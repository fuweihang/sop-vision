import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { CameraDetailActions } from "@/features/cameras/components/camera-detail-actions";
import { apiClient } from "@/lib/api-client";
import { buildCameraDetail } from "@/mocks/cameras/fixtures";

test("开始/停止预览只更新用户意图，编辑入口保持可用", async () => {
  const user = userEvent.setup();
  const onPreviewRequestedChange = vi.fn();
  const rendered = render(
    <CameraDetailActions
      camera={buildCameraDetail()}
      apiClient={apiClient}
      available
      previewRequested
      onPreviewRequestedChange={onPreviewRequestedChange}
    />,
  );

  await user.click(screen.getByRole("button", { name: "停止预览" }));
  expect(onPreviewRequestedChange).toHaveBeenCalledWith(false);
  expect(screen.getByRole("button", { name: "编辑摄像头" })).toBeEnabled();

  rendered.rerender(
    <CameraDetailActions
      camera={buildCameraDetail()}
      apiClient={apiClient}
      available={false}
      previewRequested={false}
      onPreviewRequestedChange={onPreviewRequestedChange}
    />,
  );
  expect(screen.getByRole("button", { name: "开始预览" })).toBeDisabled();
});
