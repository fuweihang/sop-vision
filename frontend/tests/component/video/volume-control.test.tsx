import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { VideoControlsRoot } from "@/features/video/components/video-controls/controls-visibility";
import { VolumeControl } from "@/features/video/components/video-controls/volume-control";
import { VideoSurface } from "@/features/video/components/video-surface";
import { installMediaElementMocks } from "../../support/media-browser-mocks";

function createPlaybackStream() {
  const audioTrack = {
    id: "volume-audio-1",
    kind: "audio",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  const videoTrack = {
    id: "volume-video-1",
    kind: "video",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  return {
    getTracks: () => [audioTrack, videoTrack],
    getAudioTracks: () => [audioTrack],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
}

/** VolumeControl 依赖 VideoSurface 和操作栏显隐上下文，测试只装配这两个真实边界。 */
function renderVolumeControl() {
  return render(
    <TooltipProvider>
      <VideoSurface stream={createPlaybackStream()} objectFit="contain">
        <VideoControlsRoot>
          <VolumeControl />
        </VideoControlsRoot>
      </VideoSurface>
    </TooltipProvider>,
  );
}

test("点击静音恢复静音前音量，Slider 归零后恢复默认 70%", async () => {
  const user = userEvent.setup();
  installMediaElementMocks();
  renderVolumeControl();

  const video = screen.getByLabelText<HTMLVideoElement>("实时视频");
  const volumeButton = screen.getByRole("button", { name: "取消静音" });
  fireEvent.mouseEnter(volumeButton);
  const volumeSlider = await screen.findByRole("group", { name: "音量" });
  const volumeSliderInput = volumeSlider.querySelector<HTMLInputElement>(
    'input[type="range"]',
  );
  expect(volumeSliderInput).not.toBeNull();
  if (volumeSliderInput === null) {
    throw new Error("音量 Slider 缺少内部 range input。");
  }

  await user.click(volumeButton);
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.7);

  fireEvent.change(volumeSliderInput, { target: { value: "40" } });
  expect(video.volume).toBe(0.4);
  await user.click(screen.getByRole("button", { name: "静音" }));
  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  await user.click(screen.getByRole("button", { name: "取消静音" }));
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.4);

  fireEvent.change(volumeSliderInput, { target: { value: "0" } });
  expect(video.muted).toBe(true);
  expect(video.volume).toBe(0);
  await user.click(screen.getByRole("button", { name: "取消静音" }));
  expect(video.muted).toBe(false);
  expect(video.volume).toBe(0.7);
});
