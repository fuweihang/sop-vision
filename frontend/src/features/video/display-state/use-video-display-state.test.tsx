import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { VideoSurface } from "@/features/video/components/video-surface";
import { useVideoSurface } from "@/features/video/components/video-surface";
import { useVideoDisplayState } from "@/features/video/display-state";
import { installPlayingMediaElementMocks } from "@/test/media-browser-mocks";

function createPlaybackStream() {
  const videoTrack = {
    id: "display-state-video-1",
    kind: "video",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  return {
    getTracks: () => [videoTrack],
    getAudioTracks: () => [],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
}

/** 测试探针只暴露 Hook 结果和暂停动作，不复制生产展示组件。 */
function DisplayStateProbe() {
  const displayState = useVideoDisplayState({
    previewActive: true,
    sessionStatus: "playing",
  });
  const {
    actions: { pause },
  } = useVideoSurface();

  return (
    <>
      <output data-testid="display-state" data-status={displayState.status}>
        {displayState.label}
      </output>
      <button type="button" onClick={pause}>
        测试暂停
      </button>
    </>
  );
}

test("统一读取当前 VideoSurface 的暂停和首帧状态", async () => {
  installPlayingMediaElementMocks();
  render(
    <VideoSurface stream={createPlaybackStream()} objectFit="contain">
      <DisplayStateProbe />
    </VideoSurface>,
  );

  await waitFor(() =>
    expect(screen.getByTestId("display-state")).toHaveTextContent("正在加载"),
  );
  fireEvent.click(screen.getByRole("button", { name: "测试暂停" }));
  expect(screen.getByTestId("display-state")).toHaveTextContent("等待画面");

  fireEvent.loadedData(screen.getByLabelText("实时视频"));
  expect(screen.getByTestId("display-state")).toHaveTextContent("LIVE");
});
