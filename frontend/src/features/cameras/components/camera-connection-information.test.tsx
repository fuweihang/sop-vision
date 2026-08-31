import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { CameraConnectionInformation } from "@/features/cameras/components/camera-connection-information";
import {
  buildCameraDetail,
  CAMERA_FIXTURE_SECRET,
  CAMERA_FIXTURE_TIMES,
} from "@/mocks/cameras/fixtures";

test("展示连接字段、Camera 状态和最近检查时间", () => {
  const camera = buildCameraDetail();
  const defaultSource = camera.sources[0];
  if (defaultSource === undefined) {
    throw new Error("Camera Fixture 缺少默认 Source。");
  }
  const { container } = render(
    <CameraConnectionInformation
      camera={camera}
      defaultSource={defaultSource}
    />,
  );

  expect(screen.getByText(camera.ip_address)).toBeVisible();
  expect(screen.getByText(String(camera.rtsp_port))).toBeVisible();
  expect(screen.getByText(camera.username)).toBeVisible();
  expect(
    container.querySelector(
      `time[datetime="${CAMERA_FIXTURE_TIMES.checkedAt}"]`,
    ),
  ).toBeVisible();
  expect(container.querySelector("[data-camera-status]")).toHaveClass(
    "bg-status-degraded",
    "text-status-degraded-foreground",
  );
  expect(
    container.querySelector("[data-camera-status] [data-status-dot]"),
  ).toHaveClass("bg-status-degraded-dot");
});

test("密码默认隐藏，并允许用户显式显示和再次隐藏", async () => {
  const user = userEvent.setup();
  const camera = buildCameraDetail();
  const defaultSource = camera.sources[0];
  if (defaultSource === undefined) {
    throw new Error("Camera Fixture 缺少默认 Source。");
  }
  render(
    <CameraConnectionInformation
      camera={camera}
      defaultSource={defaultSource}
    />,
  );

  expect(screen.getByText("********")).toBeVisible();
  expect(screen.queryByText(CAMERA_FIXTURE_SECRET)).toBeNull();
  await user.click(screen.getByRole("button", { name: "显示密码" }));
  expect(screen.getByText(CAMERA_FIXTURE_SECRET)).toBeVisible();
  expect(screen.getByRole("button", { name: "隐藏密码" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "隐藏密码" }));
  expect(screen.queryByText(CAMERA_FIXTURE_SECRET)).toBeNull();
  expect(screen.getByText("********")).toBeVisible();
});
