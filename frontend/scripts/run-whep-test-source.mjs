import { spawn } from "node:child_process";

import ffmpegPath from "ffmpeg-static";

if (ffmpegPath === null) {
  throw new Error(
    `ffmpeg-static 不支持当前平台：${process.platform}/${process.arch}。`,
  );
}

function outputArgs(videoInput, audioInput, path) {
  return [
    "-map",
    `${videoInput}:v:0`,
    "-map",
    `${audioInput}:a:0`,
    "-c:v",
    "libx264",
    "-profile:v",
    "baseline",
    "-level:v",
    "3.1",
    "-preset",
    "veryfast",
    "-tune",
    "zerolatency",
    "-pix_fmt",
    "yuv420p",
    "-g",
    "30",
    "-keyint_min",
    "30",
    "-sc_threshold",
    "0",
    "-bf",
    "0",
    "-c:a",
    "pcm_mulaw",
    "-ar",
    "8000",
    "-ac",
    "1",
    "-f",
    "rtsp",
    "-rtsp_transport",
    "tcp",
    `rtsp://127.0.0.1:8554/${path}`,
  ];
}

const args = [
  "-hide_banner",
  "-loglevel",
  "info",
  "-re",
  "-f",
  "lavfi",
  "-i",
  "testsrc2=size=1280x720:rate=30",
  "-re",
  "-f",
  "lavfi",
  "-i",
  "sine=frequency=1000:sample_rate=8000",
  "-re",
  "-f",
  "lavfi",
  "-i",
  "smptebars=size=1280x720:rate=30",
  "-re",
  "-f",
  "lavfi",
  "-i",
  "sine=frequency=600:sample_rate=8000",
  ...outputArgs(0, 1, "whep-test-primary"),
  ...outputArgs(2, 3, "whep-test-secondary"),
];

// 参数数组直接传给 spawn，不经过 shell；固定地址不接受用户输入，也不会意外执行 shell 字符。
const child = spawn(ffmpegPath, args, { stdio: "inherit" });
let requestedSignal = null;

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => {
    requestedSignal = signal;
    child.kill(signal);
  });
}

const childExit = await new Promise((resolve, reject) => {
  child.once("error", reject);
  child.once("exit", (code, signal) => {
    resolve({ code, signal });
  });
});

// FFmpeg 收到信号后可能返回自己的非零 code；人工中断仍统一使用常见 shell 信号退出码。
process.exitCode =
  requestedSignal === "SIGINT"
    ? 130
    : requestedSignal === "SIGTERM"
      ? 143
      : (childExit.code ?? (childExit.signal === "SIGINT" ? 130 : 143));
