import {
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

const PLAYBACK_ERROR_MESSAGE = "浏览器阻止了自动播放，请手动继续。";

interface UseVideoPlaybackOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  videoElement: HTMLVideoElement | null;
  stream: MediaStream | null;
}

/**
 * 管理当前 video 消费者的播放意图、音量和 srcObject。这里不会停止 Track，因为 Track 属于共享
 * Session；组件卸载或换流时只解除当前 video 的绑定。
 */
export function useVideoPlayback({
  videoRef,
  videoElement,
  stream,
}: UseVideoPlaybackOptions) {
  const [paused, setPaused] = useState(true);
  const pausedRef = useRef(true);
  const playbackIntentRef = useRef<"playing" | "paused">("playing");
  const [muted, setMutedState] = useState(true);
  const [volume, setVolumeState] = useState(0);
  const [playbackFailure, setPlaybackFailure] = useState<{
    stream: MediaStream;
    message: string;
  } | null>(null);

  const play = useCallback(async () => {
    playbackIntentRef.current = "playing";
    pausedRef.current = false;
    setPaused(false);
    const currentVideo = videoRef.current;
    if (currentVideo === null || stream === null) {
      return;
    }

    try {
      await currentVideo.play();
      setPlaybackFailure(null);
    } catch {
      // 旧 Stream 的 play Promise 可能在重连后才失败，不能覆盖新 Stream 的播放状态。
      if (currentVideo.srcObject !== stream) {
        return;
      }
      pausedRef.current = true;
      setPaused(true);
      setPlaybackFailure({ stream, message: PLAYBACK_ERROR_MESSAGE });
    }
  }, [stream, videoRef]);

  const pause = useCallback(() => {
    playbackIntentRef.current = "paused";
    pausedRef.current = true;
    setPaused(true);
    videoRef.current?.pause();
  }, [videoRef]);

  const togglePlayback = useCallback(async () => {
    // pausedRef 随原生媒体事件同步，避免快速点击时读取上一次 React render 的状态。
    if (pausedRef.current) {
      await play();
    } else {
      pause();
    }
  }, [pause, play]);

  const setMuted = useCallback(
    (nextMuted: boolean) => {
      if (videoRef.current !== null) {
        videoRef.current.muted = nextMuted;
      }
    },
    [videoRef],
  );

  const setVolume = useCallback(
    (nextVolume: number) => {
      if (videoRef.current !== null) {
        // HTMLMediaElement 只接受 0–1；在 Context 边界截断异常值，避免浏览器抛错。
        videoRef.current.volume = Math.min(1, Math.max(0, nextVolume));
      }
    },
    [videoRef],
  );

  useEffect(() => {
    if (videoElement === null) {
      return;
    }

    const updatePaused = (nextPaused: boolean) => {
      pausedRef.current = nextPaused;
      setPaused(nextPaused);
    };
    const handlePlaying = () => {
      if (playbackIntentRef.current === "playing") {
        updatePaused(false);
      } else {
        // paused 意图跨 Stream 保留；若 autoPlay 在新流就绪后触发，立即阻止它覆盖用户暂停。
        videoElement.pause();
      }
    };
    const handlePaused = () => {
      // 重连清空 srcObject 时浏览器也可能发出 pause/emptied。它不是用户暂停，不能改变播放意图。
      if (stream !== null && playbackIntentRef.current === "paused") {
        updatePaused(true);
      }
    };
    const handleVolumeChange = () => {
      setMutedState(videoElement.muted);
      setVolumeState(videoElement.volume);
    };

    videoElement.addEventListener("play", handlePlaying);
    videoElement.addEventListener("playing", handlePlaying);
    videoElement.addEventListener("pause", handlePaused);
    videoElement.addEventListener("ended", handlePaused);
    videoElement.addEventListener("emptied", handlePaused);
    videoElement.addEventListener("volumechange", handleVolumeChange);
    handleVolumeChange();

    return () => {
      videoElement.removeEventListener("play", handlePlaying);
      videoElement.removeEventListener("playing", handlePlaying);
      videoElement.removeEventListener("pause", handlePaused);
      videoElement.removeEventListener("ended", handlePaused);
      videoElement.removeEventListener("emptied", handlePaused);
      videoElement.removeEventListener("volumechange", handleVolumeChange);
    };
  }, [stream, videoElement]);

  useEffect(() => {
    const currentVideo = videoRef.current;
    if (currentVideo === null || currentVideo !== videoElement) {
      return;
    }

    currentVideo.srcObject = stream;
    if (stream !== null) {
      if (playbackIntentRef.current === "playing") {
        void play();
      } else {
        // video 保留 autoPlay 以支持初次连接；刷新前已暂停时需显式暂停，防止新流自动开始。
        currentVideo.pause();
      }
    }

    return () => {
      // 新 Stream 已绑定时，旧 effect 的 cleanup 不能把新绑定覆盖为空。
      if (currentVideo.srcObject === stream) {
        currentVideo.srcObject = null;
      }
    };
  }, [play, stream, videoElement, videoRef]);

  return {
    state: {
      paused,
      muted,
      volume,
      playbackError:
        stream !== null && playbackFailure?.stream === stream
          ? playbackFailure.message
          : null,
    },
    actions: { play, pause, togglePlayback, setMuted, setVolume },
  };
}
